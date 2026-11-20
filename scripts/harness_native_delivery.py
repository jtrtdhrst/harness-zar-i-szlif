#!/usr/bin/env python3
"""Reviewed replacement for the root-owned Harness image delivery controller.

Mirrors the transport of the audited installed controller
(``/usr/local/libexec/harness_image_delivery.py``, sha256
``3bc7234cd05139d9c3654b8976264eaf123de855a57e485435160d6745336ef5``) - docker
build/push to the loopback registry, Coolify compose image-line patch with a
compose backup, deploy, health/stability polling and compose rollback - and adds
the step the installed controller is missing: **mandatory admission before any
mutation**.

Two admitted stages, never one without the other:

* ``--mode prepare`` builds and pushes the exact source SHA. It requires
  :func:`harness_release_admission.evaluate_build`: the service must be in the
  reviewed manifest (``ops/release-lanes.json``), the Coolify UUID/kind must
  match, the merge must be an authorized ``main`` squash of the reviewed PR
  head, the lane hold must be answered by a live per-UUID grant, and the review
  must be independent and bound to that head. Only then does docker run.
* ``--mode deploy`` promotes the already-built immutable image and requires the
  full :func:`harness_release_admission.evaluate` via
  :func:`harness_delivery_controller.run_promotion`, including the root-owned
  local-CI attestation and the exact image digest. Its transport ``build`` only
  resolves the existing digest and never rebuilds, so a deploy can never ship
  source the attester did not see.

No secret is read at import time. The Coolify token and git credential are read
only inside the live transport, by the same ``O_NOFOLLOW``/``fstat`` reader the
gate uses, from root-only paths. Nothing here installs, starts, stops or
reconfigures a host service; installation is the operator step in
``ops/harness/INSTALL-RUNBOOK.md``.

Two invocation modes and one runtime CLI (``build_parser``). The root install
preflight validates the exact reviewed unattended ``ExecStart`` tuple **without
importing this adapter from the host**:

* explicit - the operator passes ``--base-sha`` and ``--source-sha``;
* ``--auto`` - the mode the installed 120-second timer uses, because a unit
  cannot know a merge SHA in advance. It takes the exact pair from the unit's
  ``EnvironmentFile`` (``HARNESS_BASE_SHA`` / ``HARNESS_SOURCE_SHA``), which the
  operator writes when the checkout advances. There is no SHA reconstruction and
  no delivery baseline: an absent or malformed range is denied
  (``auto_source_range_missing``), because inventing which tree to promote is
  precisely what this adapter must not do. Auto mode chooses *which* range to
  look at; it never weakens admission, since each service still needs its own
  request, per-UUID grant, independent exact-SHA review and HMAC-verified
  attestation bound to that same SHA.

The attestation is loaded through
:func:`harness_delivery_controller.load_artifacts`, which verifies the HMAC with
the root-owned key before admission. No value from an artifact or from a JSON
field is ever executed: the only commands this module runs are its own fixed
``docker``/``curl``/``git`` invocations.
"""
import argparse
import base64
import hashlib
import json
import os
import stat
import re
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from harness_delivery_controller import git_changed_paths, load_artifacts, run_promotion
from harness_release_admission import SHA, Denied, evaluate, evaluate_build, load_gate_file
from harness_release_parity import ParityFailure, check_source as check_upstream_source

REPO = "miloszspyrka-code/harness-zar-i-szlif"
REGISTRY = "127.0.0.1:5000"
# Trusted-main GHCR publishing is owned by mcp-images-ghcr.yml (PR #186).
# AUTO deployment consumes that immutable digest, NEVER builds a second image.
GHCR = "ghcr.io/miloszspyrka-code"
GHCR_SOURCE_SERVICES = frozenset({
    "emailens-mcp", "mantic-mcp", "plasmic-mcp",
    "playwright-mcp", "supabase-mcp", "ubuntu-mcp",
})
COOLIFY = "http://127.0.0.1:8001/api/v1"
COOLIFY_TOKEN = Path("/root/coolify-secrets/coolify_api_token")
STATE_ROOT = Path("/var/lib/harness-image-delivery")
# The reviewed unit's EnvironmentFile carries the exact pair; nothing is derived.
AUTO_BASE_ENV = "HARNESS_BASE_SHA"
AUTO_SOURCE_ENV = "HARNESS_SOURCE_SHA"
REVISION_LABEL = "org.opencontainers.image.revision"
POLL_SECONDS = 6
HEALTH_DEADLINE = 240

# Transport spec mirrored from the audited installed controller. The Coolify
# UUID and kind are deliberately absent: they come from the reviewed manifest,
# which is the single allowlist for what may be touched.
SERVICES = {
    "mantic-mcp": {"folder": "mantic-mcp", "dockerfile": "Dockerfile.http",
                   "image_prefix": "local/mantic-mcp", "health_url": None},
    "playwright-mcp": {"folder": "playwright-mcp", "dockerfile": "Dockerfile",
                       "image_prefix": "local/playwright-mcp",
                       "health_url": "http://127.0.0.1:18932/mcp"},
    "emailens-mcp": {"folder": "emailens-mcp", "dockerfile": "Dockerfile",
                     "image_prefix": "z7ld1nac6jtmtm653dloefrg_emailens", "health_url": None},
    "plasmic-mcp": {"folder": "plasmic-mcp", "dockerfile": "Dockerfile",
                    "image_prefix": "local/plasmic-mcp", "health_url": None},
    "qdrant-mcp": {"folder": "qdrant-mcp", "dockerfile": "Dockerfile",
                   "image_prefix": "127.0.0.1:5000/mcp-qdrant-staging", "health_url": None},
    "supabase-mcp": {"folder": "supabase-mcp", "dockerfile": "Dockerfile",
                     "image_prefix": "selfhosted-supabase-mcp", "health_url": None},
    "opik-run-enricher": {"folder": "opik-run-enricher", "dockerfile": "Dockerfile",
                          "image_prefix": "local/opik-run-enricher", "health_url": None},
    "paperclip-mcp": {"folder": "paperclip-mcp", "dockerfile": "Dockerfile",
                      "image_prefix": "paperclip-mcp", "health_url": None},
    "ubuntu-mcp": {"folder": "ubuntu-mcp", "dockerfile": "Dockerfile",
                   "image_prefix": "local/ubuntu-mcp-bridge", "health_url": None},
}


def image_tag(service, source_sha, registry=REGISTRY):
    return f"{registry}/harness-{service}:{source_sha[:12]}"


def image_reference(service, digest, registry=REGISTRY):
    return f"{registry}/harness-{service}@{digest}"


class Host:
    """The only object that performs side effects. Tests replace it wholesale."""

    def __init__(self, coolify_base=COOLIFY, coolify_token=COOLIFY_TOKEN):
        self.coolify_base = coolify_base
        self.coolify_token = coolify_token

    def docker(self, *args, timeout=3600):
        completed = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            raise RuntimeError("docker " + args[0] + " failed: " + (completed.stderr or "").strip()[:200])
        return completed.stdout.strip()

    def docker_build(self, argv, log_path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "wb") as log:
            completed = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"build failed; see {log_path}")

    def coolify(self, method, path, body=None):
        from harness_release_admission import read_trusted_bytes

        token = read_trusted_bytes(self.coolify_token, "coolify_token", require_root=True).decode().strip()
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.coolify_base + path, data=data, method=method,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                     "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})

    def probe(self, url):
        completed = subprocess.run(
            ["curl", "-s", "-m", "10", "-o", "/dev/null", "-w", "%{http_code}",
             "-X", "POST", url, "-H", "content-type: application/json",
             "-H", "accept: application/json, text/event-stream",
             "-d", '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
                   '{"protocolVersion":"2025-03-26","capabilities":{},'
                   '"clientInfo":{"name":"delivery","version":"1"}}}'],
            capture_output=True, text=True, timeout=30)
        return completed.stdout.strip()


def verify_source(repo, source_sha):
    """The build must run on the reviewed tree: exact SHA, clean worktree.

    A build from an unchecked working tree could ship code that no reviewer and
    no attester ever saw, so this refuses before docker is invoked at all.
    """
    try:
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=60)
        # Build context can contain untracked files; ignoring them lets Docker
        # ship bytes that the reviewed commit and CI attestation never saw.
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                                 "--untracked-files=all", "--ignored"],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("source_check_unavailable") from None
    if head.returncode != 0 or status.returncode != 0:
        raise Denied("source_unreadable")
    if head.stdout.strip() != source_sha:
        raise Denied("source_not_at_approved_sha")
    if status.stdout.strip():
        raise Denied("source_worktree_dirty")
    return True


def image_pattern(service, spec, registry=REGISTRY):
    """Match the previously pinned image or this registry's image already deployed."""
    current = f"{registry}/harness-{service}"
    prefixes = sorted({
        spec["image_prefix"], current,
        f"{REGISTRY}/harness-{service}",
        f"{GHCR}/harness-{service}",
    }, key=len, reverse=True)
    alternation = "|".join(re.escape(prefix) for prefix in prefixes)
    return re.compile(r"(?m)^(\s*image:\s*)(['\"]?)(?:" + alternation + r")[^'\"\s]*\2")


def compose_for(host, uuid):
    _, service = host.coolify("GET", f"/services/{uuid}")
    raw = service.get("docker_compose_raw") or ""
    if not raw:
        raise RuntimeError("service has no docker_compose_raw")
    return raw


def patch_compose(host, uuid, service, spec, tag, *, on_backup=None):
    """Patch one image and persist a unique, private snapshot for this attempt."""
    raw = compose_for(host, uuid)
    pattern = image_pattern(service, spec)
    patched, count = pattern.subn(lambda match: f"{match.group(1)}{match.group(2)}{tag}{match.group(2)}", raw)
    if count != 1:
        raise RuntimeError(f"expected exactly one {spec['image_prefix']} image line, found {count}")
    # A second promotion in the same second must never overwrite the first
    # snapshot. The controller is privileged; the raw compose may contain
    # secrets, so no world-readable file may exist even during the write.
    backup = STATE_ROOT / "backups" / f"{service}-{time.time_ns()}-{secrets.token_hex(8)}.yml"
    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(backup, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    # Register the snapshot BEFORE the first provider mutation. If PATCH
    # succeeds but POST fails, rollback must target this exact attempt.
    if on_backup is not None:
        on_backup(backup)
    status, _ = host.coolify("PATCH", f"/services/{uuid}",
                             {"docker_compose_raw": base64.b64encode(patched.encode()).decode()})
    if status not in (200, 201):
        raise RuntimeError(f"compose patch http {status}")
    return raw, backup


def deploy_service(host, uuid, service, spec, tag, *, on_backup=None):
    raw, backup = patch_compose(host, uuid, service, spec, tag, on_backup=on_backup)
    # No internal rollback here: the release controller owns the ONE restore
    # attempt and records its result in the audit log. A nested restore would
    # apply twice and could silently select a snapshot from a different run.
    status, body = host.coolify("POST", "/deploy", {"uuid": uuid})
    if status not in (200, 201):
        raise RuntimeError(f"deploy http {status}")
    deadline = time.time() + HEALTH_DEADLINE
    state = ""
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        running = host.docker("ps", "--filter", f"ancestor={tag}",
                              "--filter", f"label=coolify.serviceUuid={uuid}",
                              "--format", "{{.Status}}")
        _, current = host.coolify("GET", f"/services/{uuid}")
        state = str(current.get("status") or "")
        if "(healthy)" in running and state.startswith("running:healthy"):
            return raw, backup, body
    raise RuntimeError(f"{service} did not become healthy (status={state})")


def running_revision(host, service, digest, registry=REGISTRY):
    return host.docker("image", "inspect", "--format",
                       '{{index .Config.Labels "' + REVISION_LABEL + '"}}',
                       image_reference(service, digest, registry))


class Transport:
    """``harness_delivery_controller`` transport backed by the real host.

    ``build`` resolves an already-prepared immutable digest and refuses to build:
    a deploy must ship exactly the image the root attester observed.
    """

    def __init__(self, host, registry=REGISTRY, expected_digests=None):
        self.host = host
        self.registry = registry
        # Approved digest comes from independently reviewed root-owned request;
        # never infer a release identity from mutable GHCR SHA-looking tags.
        self.expected_digests = dict(expected_digests or {})
        # Transaction-scoped snapshots: never guess using the newest glob on
        # disk, which can belong to another release or Coolify service UUID.
        self._rollback_snapshots = {}

    def _known(self, service):
        if service not in SERVICES:
            raise RuntimeError(f"{service}: not in the reviewed transport map")

    def current(self, service, uuid):
        self._known(service)
        try:
            raw = compose_for(self.host, uuid)
        except Exception:
            return None
        spec = SERVICES.get(service) or {"image_prefix": f"{self.registry}/harness-{service}"}
        match = image_pattern(service, spec, self.registry).search(raw)
        if not match:
            return None
        reference = match.group(0).split("image:", 1)[-1].strip().strip("'\"")
        try:
            out = self.host.docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", reference)
        except Exception:
            return None
        return out.split("@", 1)[1] if "@" in out else None

    def build(self, service, source_sha):
        self._known(service)
        if self.registry == GHCR:
            if service not in GHCR_SOURCE_SERVICES:
                raise RuntimeError("auto_ghcr_source_unavailable")
            expected = self.expected_digests.get(service)
            if not isinstance(expected, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
                raise RuntimeError("auto_ghcr_digest_unavailable")
            pinned = image_reference(service, expected, self.registry)
            # Pull only the operator-approved digest. A retargeted mutable tag
            # can never change which image the controller promotes.
            self.host.docker("pull", pinned)
            reference = self.host.docker(
                "image", "inspect", "--format", "{{index .RepoDigests 0}}", pinned)
            if reference != pinned:
                raise RuntimeError("auto_ghcr_repo_digest_mismatch")
            if running_revision(self.host, service, expected, self.registry) != source_sha:
                raise RuntimeError("auto_ghcr_source_revision_mismatch")
            return expected
        tag = image_tag(service, source_sha, self.registry)
        reference = self.host.docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", tag)
        if "@" not in reference:
            raise RuntimeError(f"{service}: prepared image has no repository digest")
        digest = reference.split("@", 1)[1]
        if running_revision(self.host, service, digest, self.registry) != source_sha:
            raise RuntimeError(f"{service}: prepared image is not labelled with {source_sha}")
        return digest

    def deploy(self, service, uuid, kind, digest):
        self._known(service)
        # The attested SHA-256 digest, not the mutable :sha12 tag, is the
        # deployment identity. A tag can be retargeted after attestation.
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise RuntimeError(f"{service}: invalid immutable image digest")
        revision = running_revision(self.host, service, digest, self.registry)
        if not isinstance(revision, str) or not SHA.fullmatch(revision):
            raise RuntimeError(f"{service}: prepared image carries no exact source revision")
        pinned_ref = image_reference(service, digest, self.registry)
        key = (service, uuid)
        # Capture pre-deployment identity while the UUID-qualified runtime
        # is still healthy; a mutable tag alone cannot prove rollback identity.
        previous = self.health(service, uuid)
        previous_digest = previous.get("digest")
        if (previous.get("status") != "ok" or not isinstance(previous_digest, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", previous_digest)):
            raise RuntimeError(f"{service}: previous running image digest unverified")
        self._rollback_snapshots.pop(key, None)
        def record_snapshot(path):
            self._rollback_snapshots[key] = (path, previous_digest)
        _, _, body = deploy_service(self.host, uuid, service, SERVICES[service], pinned_ref,
                                    on_backup=record_snapshot)
        return str(body.get("deployment_uuid") or body.get("uuid") or "deploy")

    def health(self, service, uuid):
        """Read back what is actually running: image digest, revision label, health."""
        self._known(service)
        _, service_state = self.host.coolify("GET", f"/services/{uuid}")
        raw = service_state.get("docker_compose_raw") or ""
        match = image_pattern(service, SERVICES[service], self.registry).search(raw)
        if not match:
            return {"status": "no_image", "digest": None, "source_sha": None}
        reference = match.group(0).split("image:", 1)[-1].strip().strip("'\"")
        image_id = self.host.docker("image", "inspect", "--format", "{{.Id}}", reference)
        # Do not count an unrelated healthy container using the same image.
        # Coolify's own resource identity is carried in coolify.serviceUuid.
        # Missing legacy labels fail closed until a verified redeployment.
        running = self.host.docker("ps", "--filter", f"ancestor={image_id}",
                                   "--filter", f"label=coolify.serviceUuid={uuid}",
                                   "--format", "{{.Status}}")
        repo_digests = self.host.docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", reference)
        revision = self.host.docker("image", "inspect", "--format",
                                    '{{index .Config.Labels "' + REVISION_LABEL + '"}}', reference)
        health_url = SERVICES[service].get("health_url")
        probe_ok = True if not health_url else self.host.probe(health_url) == "200"
        statuses = [line.strip() for line in running.splitlines() if line.strip()]
        healthy = (len(statuses) == 1 and statuses[0].startswith("Up ")
                   and "(healthy)" in statuses[0]
                   and str(service_state.get("status") or "").startswith("running:healthy"))
        return {"status": "ok" if healthy and probe_ok else "unhealthy",
                "digest": repo_digests.split("@", 1)[1] if "@" in repo_digests else None,
                "source_sha": revision or None}

    def rollback(self, service, uuid):
        self._known(service)
        snapshot = self._rollback_snapshots.pop((service, uuid), None)
        if snapshot is None:
            raise RuntimeError(f"{service}: no snapshot from this deployment attempt")
        if (not isinstance(snapshot, tuple) or len(snapshot) != 2
                or not isinstance(snapshot[1], str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot[1])):
            raise RuntimeError(f"{service}: previous image digest not captured")
        backup, previous_digest = snapshot
        raw = backup.read_text(encoding="utf-8")
        self.host.coolify("PATCH", f"/services/{uuid}",
                          {"docker_compose_raw": base64.b64encode(raw.encode()).decode()})
        status, body = self.host.coolify("POST", "/deploy", {"uuid": uuid})
        if status not in (200, 201):
            raise RuntimeError(f"rollback deploy http {status}")
        # A 200/201 only proves Coolify accepted the request. It does NOT prove
        # the old service came back. Read back exact Compose and live health;
        # failed restoration remains rollback_failed in the controller audit.
        deadline = time.monotonic() + HEALTH_DEADLINE
        while time.monotonic() < deadline:
            try:
                current_compose = compose_for(self.host, uuid)
                observed = self.health(service, uuid)
                if (current_compose == raw and observed.get("status") == "ok"
                        and observed.get("digest") == previous_digest):
                    return str(body.get("deployment_uuid") or body.get("uuid") or "rollback")
            except (OSError, RuntimeError, ValueError):
                pass
            time.sleep(POLL_SECONDS)
        raise RuntimeError(f"{service}: rollback compose or live health not verified")


def prepare(host, repo, service, source_sha, registry=REGISTRY, log_dir=None):
    """Build and push one service at the exact source SHA, returning its digest."""
    spec = SERVICES[service]
    verify_source(repo, source_sha)
    folder = Path(repo) / spec["folder"]
    if not folder.is_dir():
        raise RuntimeError(f"{service}: source folder missing in {repo}")
    tag = image_tag(service, source_sha, registry)
    log = Path(log_dir or STATE_ROOT) / f"build-{service}-{source_sha[:12]}.log"
    host.docker_build([
        "docker", "build", "-f", str(folder / spec["dockerfile"]),
        "--label", f"{REVISION_LABEL}={source_sha}",
        "--label", "org.opencontainers.image.source=" + f"https://github.com/{REPO}",
        "-t", tag, str(folder)], log)
    host.docker("push", tag)
    reference = host.docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", tag)
    if "@" not in reference:
        raise RuntimeError(f"{service}: pushed image has no repository digest")
    return tag, reference.split("@", 1)[1]


def auto_ci_policy(service, repo, attestation_key):
    """Reject missing or wrong root-owned CI policy before any Docker build."""
    import harness_local_ci_attest as ci

    if os.geteuid() != 0:
        raise Denied("auto_ci_requires_root")
    if not attestation_key:
        raise Denied("attestation_key_missing")
    raw = ci.read_trusted_file(ci.DEFAULT_POLICY, "policy", require_root=True)
    policy = ci.validate_policy(json.loads(raw))
    if service not in GHCR_SOURCE_SERVICES:
        raise Denied("auto_ghcr_source_unavailable")
    ci.policy_commands(policy, service)
    if Path(policy["repo_root"]).resolve() != Path(repo).resolve():
        raise Denied("auto_ci_repo_mismatch")
    if Path(policy["key_file"]).resolve() != Path(attestation_key).resolve():
        raise Denied("auto_ci_key_mismatch")
    # Preflight the root-owned private signing key BEFORE GHCR Docker pull,
    # even when the current request has no attestation artifact yet.
    key = ci.read_trusted_file(attestation_key, "signing_key", require_root=True)
    if len(key) < 32:
        raise Denied("signing_key_weak")
    # Existing signed attestations must match the CURRENT root-owned policy;
    # an older valid HMAC does not authorize a service after policy revocation.
    policy["_verified_digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    return policy


def auto_prepare_and_attest(host, repo, base_sha, source_sha, service,
                            bundle, attestation_key, *, policy):
    """Pull the GHCR-published immutable image and sign local CI; never rebuild."""
    import harness_local_ci_attest as ci
    from harness_release_admission import read_trusted_bytes, verified_attestation

    verify_source(repo, source_sha)
    digest = bundle["request"].get("image_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise Denied("auto_ghcr_digest_missing")
    pinned = image_reference(service, digest, GHCR)
    host.docker("pull", pinned)
    actual = host.docker("image", "inspect", "--format",
                         "{{index .RepoDigests 0}}", pinned)
    if actual != pinned:
        raise Denied("auto_ghcr_repo_digest_mismatch")
    if running_revision(host, service, digest, GHCR) != source_sha:
        raise Denied("auto_ghcr_source_revision_mismatch")
    code = ci.main(["--service", service, "--base-sha", base_sha,
                    "--source-sha", source_sha, "--image-digest", digest])
    if code != 0:
        raise Denied("auto_ci_tests_failed")
    artifact_path = ci.attestation_path(policy["out_dir"], service, source_sha)
    artifact = load_gate_file(artifact_path, "attestation", require_root=True)
    key = read_trusted_bytes(attestation_key, "attestation_key", require_root=True)
    return verified_attestation(artifact, key), digest


def resolve_source_range(args, environ=None):
    """Return ``(base_sha, source_sha)`` - supplied, never reconstructed.

    The installed 120-second timer cannot know a merge SHA in advance, so the
    reviewed unit passes the exact pair through systemd's ``EnvironmentFile``
    (``HARNESS_BASE_SHA`` / ``HARNESS_SOURCE_SHA``), written by the operator when
    the checkout advances. When that range is absent or malformed the cycle
    fails closed with ``auto_source_range_missing`` instead of inventing a range
    from host state: guessing which tree to promote is exactly what this gate
    must never do. Explicit ``--base-sha``/``--source-sha`` always win, and the
    range is only *which* commits to consider - each service still needs its own
    request, grant, review and verified attestation bound to that exact SHA.
    """
    environ = os.environ if environ is None else environ
    if args.auto:
        base_sha = args.base_sha or environ.get(AUTO_BASE_ENV)
        source_sha = args.source_sha or environ.get(AUTO_SOURCE_ENV)
        if not (base_sha and source_sha):
            raise Denied("auto_source_range_missing")
    else:
        base_sha, source_sha = args.base_sha, args.source_sha
        if not (base_sha and source_sha):
            raise Denied("sha_arguments_required")
    if not isinstance(base_sha, str) or not SHA.fullmatch(base_sha):
        raise Denied("invalid_base_sha")
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise Denied("invalid_source_sha")
    return base_sha, source_sha




# This value is never sourced from environment, a request, or the CLI. Tests
# substitute their own non-root fixture UID only through unittest.mock.patch.
DELIVERY_LEDGER_OWNER_UID = 0


def read_private_delivery_ledger(state_dir):
    """Load the existing release ledger with root-owned no-follow descriptors.

    The ledger can suppress a release, so treating user-writable or symlinked
    state as trustworthy would be a fail-open deployment control. Hold the
    private directory fd while opening its entry via dir_fd: no path-based
    lstat/open race is possible. The actual descriptors are checked before
    and after reading. Missing file is allowed *only inside* a trusted dir.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise Denied("delivery_ledger_no_secure_open")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        directory_fd = os.open(str(state_dir), directory_flags)
    except OSError:
        raise Denied("delivery_ledger_directory_untrusted") from None
    try:
        directory = os.fstat(directory_fd)
        if (not stat.S_ISDIR(directory.st_mode)
                or directory.st_uid != DELIVERY_LEDGER_OWNER_UID
                or directory.st_mode & 0o077):
            raise Denied("delivery_ledger_directory_untrusted")
        try:
            file_fd = os.open("delivery.json",
                              os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                              dir_fd=directory_fd)
        except FileNotFoundError:
            return {}
        except OSError:
            raise Denied("delivery_ledger_file_untrusted") from None
        try:
            original = os.fstat(file_fd)
            if (not stat.S_ISREG(original.st_mode)
                    or original.st_uid != DELIVERY_LEDGER_OWNER_UID
                    or original.st_mode & 0o077
                    or original.st_nlink != 1
                    or original.st_size <= 0 or original.st_size > 262144):
                raise Denied("delivery_ledger_file_untrusted")
            try:
                raw = bytearray()
                while len(raw) <= 262144:
                    chunk = os.read(file_fd, min(65536, 262145 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
            except OSError:
                raise Denied("delivery_ledger_unreadable") from None
            after = os.fstat(file_fd)
            if (len(raw) != original.st_size or
                    (original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise Denied("delivery_ledger_changed_during_read")
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)
    try:
        ledger = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Denied("delivery_ledger_invalid") from None
    if not isinstance(ledger, dict):
        raise Denied("delivery_ledger_invalid")
    return ledger


def pending_per_service_source_paths(repo, source_sha, state_dir, manifest):
    """Reconcile against the *existing* digest-verified delivery ledger.

    The global operator source range is not a release cursor. A moved
    HARNESS_BASE_SHA must not erase a service's unmet production delivery.
    No state is written here. An unknown baseline is eligible for *admission*
    but never asserted to be deployed; it still needs exact-SHA review,
    a per-UUID release grant and signed CI before build or deployment.
    """
    ledger = read_private_delivery_ledger(state_dir)

    entries = {entry.get("id"): entry
               for entry in (manifest.get("lanes") or []) +
                            (manifest.get("other_resources") or [])
               if isinstance(entry, dict)}
    pending = set()
    unknown_baselines = []
    diff_cache = {}
    for service, spec in sorted(SERVICES.items()):
        route = entries.get(service)
        if not route or route.get("coolify_kind") != "service" or not route.get("coolify_uuid"):
            # Not an approved live route; a source folder alone cannot
            # authorize a production deployment (for example, orphan adapters).
            continue
        folder = spec["folder"]
        source_dir = Path(repo) / folder
        if not source_dir.is_dir():
            # Removed source remains governed by the existing retired-source
            # policy and its explicit/manual release lane, not a phantom build.
            continue
        entry = ledger.get(service)
        if entry is None:
            previous = None
        elif isinstance(entry, dict):
            previous = entry.get("source_sha")
        else:
            raise Denied("delivery_ledger_invalid:" + service)
        if previous is None:
            unknown_baselines.append(service)
            # The tracked Dockerfile is an admission sentinel, NOT proof of a
            # changed file or proof that the running image is current. No
            # deployment can occur without the original strict gates.
            sentinel = source_dir / spec["dockerfile"]
            if sentinel.is_file():
                pending.add(f"{folder}/{spec['dockerfile']}")
            else:
                raise Denied("missing_build_context:" + service)
            continue
        if not isinstance(previous, str) or not SHA.fullmatch(previous):
            raise Denied("delivery_ledger_invalid_sha:" + service)
        if previous == source_sha:
            continue
        if previous not in diff_cache:
            ancestry = subprocess.run(
                ["git", "-C", str(repo), "merge-base", "--is-ancestor",
                 previous, source_sha], capture_output=True, timeout=30)
            if ancestry.returncode != 0:
                raise Denied("delivery_ledger_not_ancestor:" + service)
            diff_cache[previous] = git_changed_paths(repo, previous, source_sha)
        pending.update(path for path in diff_cache[previous]
                       if path == folder or path.startswith(folder + "/"))
    return sorted(pending), sorted(unknown_baselines)


def resolve_verified_checkout_tip(repo, pinned_sha, base_sha):
    """Use a fast-forward checkout tip in AUTO; never change the source tree.

    A timer can observe a newer, externally advanced main checkout after its
    root-owned EnvironmentFile was pinned. This read-only bridge eliminates a
    stale pin without making a release decision. The caller still independently
    verifies that the tip is CURRENT GitHub main, and the ordinary signed,
    per-UUID admission gate remains mandatory before any Docker/Coolify write.
    Neither the pinned baseline nor release-state evidence is updated here.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("auto_checkout_unverifiable") from None
    tip = result.stdout.strip()
    if result.returncode != 0 or not SHA.fullmatch(tip):
        raise Denied("auto_checkout_unverifiable")
    try:
        worktree = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain",
             "--untracked-files=all"],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("auto_checkout_unverifiable") from None
    if worktree.returncode != 0:
        raise Denied("auto_checkout_unverifiable")
    if worktree.stdout.strip():
        raise Denied("auto_checkout_dirty")
    for ancestor in (pinned_sha, base_sha):
        if ancestor == tip:
            continue
        try:
            probe = subprocess.run(
                ["git", "-C", str(repo), "merge-base", "--is-ancestor",
                 ancestor, tip], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise Denied("auto_source_not_fast_forward") from None
        if probe.returncode != 0:
            raise Denied("auto_source_not_fast_forward")
    return tip


TRUSTED_ORIGINS = (
    r"https://github\.com/miloszspyrka-code/harness-zar-i-szlif(?:\.git)?",
    r"git@github\.com:miloszspyrka-code/harness-zar-i-szlif(?:\.git)?",
    r"ssh://git@github\.com/miloszspyrka-code/harness-zar-i-szlif(?:\.git)?",
)


def _git(repo, *args, timeout=120):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=timeout)


def sync_checkout_to_main(repo):
    """Fast-forward the delivery checkout to the real GitHub main tip.

    This replaces the operator-written EnvironmentFile pin. It only advances a
    clean checkout by fast-forward; a dirty tree, divergent history or
    unverifiable origin fails closed before any build.
    """
    try:
        origin = _git(repo, "remote", "get-url", "origin")
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("source_remote_unverifiable") from None
    if origin.returncode != 0 or not any(
            re.fullmatch(pattern, origin.stdout.strip(), flags=re.IGNORECASE)
            for pattern in TRUSTED_ORIGINS):
        raise Denied("source_remote_untrusted")
    try:
        ls = _git(repo, "ls-remote", "--exit-code", "origin", "refs/heads/main")
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("upstream_main_unverifiable") from None
    lines = ls.stdout.splitlines()
    if (ls.returncode != 0 or len(lines) != 1
            or not re.fullmatch(r"[0-9a-f]{40}\trefs/heads/main", lines[0])):
        raise Denied("upstream_main_unverifiable")
    source_sha = lines[0].split("\t", 1)[0]
    try:
        # A shallow operator checkout cannot diff an older deployed baseline.
        # Unshallow once; this repo is small and full history is required for
        # exact per-service change detection.
        if _git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            unshallow = _git(repo, "fetch", "--quiet", "--unshallow", "origin", "main",
                             timeout=300)
            if unshallow.returncode != 0:
                raise Denied("checkout_unshallow_failed")
        fetch = _git(repo, "fetch", "--quiet", "origin", "main")
        status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("checkout_fetch_failed") from None
    if fetch.returncode != 0:
        raise Denied("checkout_fetch_failed")
    if status.returncode != 0:
        raise Denied("checkout_unverifiable")
    if status.stdout.strip():
        raise Denied("checkout_dirty")
    head = _git(repo, "rev-parse", "HEAD")
    if head.returncode != 0 or not SHA.fullmatch(head.stdout.strip()):
        raise Denied("checkout_unverifiable")
    if head.stdout.strip() != source_sha:
        probe = _git(repo, "merge-base", "--is-ancestor", head.stdout.strip(), source_sha)
        if probe.returncode != 0:
            raise Denied("checkout_not_fast_forward")
        checkout = _git(repo, "checkout", "--quiet", "--detach", source_sha)
        if checkout.returncode != 0:
            raise Denied("checkout_update_failed")
    if _git(repo, "rev-parse", "HEAD").stdout.strip() != source_sha:
        raise Denied("checkout_stale")
    return source_sha


def deployed_source_sha(host, transport, repo, service, uuid):
    """Resolve the source SHA actually running for one service.

    The release ledger wins when present. Otherwise the OCI revision label of
    the running image is used; a legacy 12-hex image tag is accepted only when
    git resolves it uniquely. An unknown baseline never guesses a deployment.
    """
    try:
        health = transport.health(service, uuid)
    except Exception:
        health = {}
    sha = health.get("source_sha") if isinstance(health, dict) else None
    if isinstance(sha, str) and SHA.fullmatch(sha):
        return sha, health
    try:
        raw = compose_for(host, uuid)
        match = image_pattern(service, SERVICES[service]).search(raw)
    except Exception:
        match = None
    if match:
        reference = match.group(0).split("image:", 1)[-1].strip().strip("'\"")
        tag = reference.rsplit(":", 1)[-1]
        if re.fullmatch(r"[0-9a-f]{12,40}", tag):
            probe = _git(repo, "rev-parse", "--verify", tag + "^{commit}")
            if probe.returncode == 0 and SHA.fullmatch(probe.stdout.strip()):
                return probe.stdout.strip(), health
    raise Denied("auto_baseline_unavailable:" + service)


def auto_main_cycle(args, manifest, host):
    """Build and promote every auto service whose source changed on main.

    The merge to trusted main is the release authorization for entries with
    ``auto_deploy_expected: true``. Exact source SHA, a locally built immutable
    digest, live health/source readback and one rollback remain mandatory.
    """
    source_sha = sync_checkout_to_main(args.repo)
    # The caller loaded the manifest before the checkout advanced. Reload it
    # from the exact tree this cycle is about to build, never from stale HEAD.
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = Path(args.repo) / manifest_path
    manifest = load_gate_file(str(manifest_path), "manifest", require_root=False)
    transport = Transport(host)
    ledger = read_private_delivery_ledger(args.state_dir)
    entries = {entry.get("id"): entry
               for entry in (manifest.get("lanes") or []) +
                            (manifest.get("other_resources") or [])
               if isinstance(entry, dict)}
    plan, pre, changed_paths = [], {}, []
    for service, spec in sorted(SERVICES.items()):
        entry = entries.get(service)
        if not entry or entry.get("auto_deploy_expected") is not True:
            continue
        if (entry.get("platform", "coolify") != "coolify"
                or entry.get("coolify_kind") != "service"):
            plan.append({"service": service, "decision": "unsupported_kind"})
            continue
        uuid = entry.get("coolify_uuid")
        if not isinstance(uuid, str) or not re.fullmatch(r"[a-z0-9]{10,40}", uuid):
            plan.append({"service": service, "decision": "invalid_uuid"})
            continue
        previous = None
        record = ledger.get(service)
        if isinstance(record, dict):
            previous = record.get("source_sha")
        if not (isinstance(previous, str) and SHA.fullmatch(previous)):
            try:
                previous, _ = deployed_source_sha(host, transport, args.repo, service, uuid)
            except Denied as exc:
                plan.append({"service": service, "decision": "denied",
                             "reason": str(exc)})
                continue
        if previous == source_sha:
            plan.append({"service": service, "decision": "current",
                         "source_sha": previous})
            continue
        bootstrap = False
        try:
            paths = [path for path in git_changed_paths(args.repo, previous, source_sha)
                     if path == spec["folder"] or path.startswith(spec["folder"] + "/")]
        except Exception as exc:
            # A legacy image label may name a commit that is not in this
            # repository (pre-history rewrite or foreign build). One bounded
            # bootstrap rebuild at exact main is allowed; the ledger then
            # records a verifiable baseline for every later diff.
            known = _git(args.repo, "cat-file", "-e", previous).returncode == 0
            if known:
                plan.append({"service": service, "decision": "denied",
                             "reason": "diff_failed:" + type(exc).__name__})
                continue
            paths = [f"{spec['folder']}/{spec['dockerfile']}"]
            bootstrap = True
        if not paths:
            plan.append({"service": service, "decision": "source_unchanged",
                         "source_sha": previous})
            continue
        item = {"service": service, "decision": "would_deploy",
                "baseline": previous, "changed_paths": sorted(paths)}
        if bootstrap:
            item["bootstrap"] = "unverifiable_baseline"
        plan.append(item)
        if args.mode == "plan":
            continue
        try:
            _, digest = prepare(host, args.repo, service, source_sha)
        except Exception as exc:
            item.update(decision="build_failed", reason=type(exc).__name__)
            continue
        pre[service] = {"service": service, "coolify_uuid": uuid,
                        "coolify_kind": "service", "source_sha": source_sha,
                        "image_digest": digest}
        changed_paths.extend(paths)
        item.update(decision="built", image_digest=digest)
    report = {"mode": args.mode, "source_sha": source_sha, "services": plan}
    if args.mode == "plan" or not pre:
        report["result"] = "plan" if args.mode == "plan" else "no_service_change"
        print(json.dumps(report, sort_keys=True))
        return 0
    promotion = run_promotion(
        manifest, changed_paths, lambda service: {}, transport,
        state_path=str(Path(args.state_dir) / "delivery.json"),
        lock_path=str(Path(args.state_dir) / "delivery.lock"),
        source_sha=source_sha, pre_admitted=pre)
    report["promotion"] = promotion
    good = {"promoted", "already_delivered"}
    decisions = promotion.get("decisions", [])
    ok = (len(decisions) == len(pre)
          and all(decision.get("decision") in good for decision in decisions)
          and promotion.get("result") != "denied")
    report["result"] = "ok" if ok else "denied"
    print(json.dumps(report, sort_keys=True))
    return 0 if ok else 1


def build_parser():
    """The adapter's only CLI surface.

    The root preflight checks a fixed, reviewed unattended ``ExecStart``
    interface and exact installed file hashes without importing this module.
    This parser governs runtime CLI processing, not privileged preflight.
    """
    parser = argparse.ArgumentParser(description="Admission-gated Harness image delivery")
    parser.add_argument("--mode", choices=("plan", "prepare", "deploy"), default="plan")
    parser.add_argument("--manifest", default="ops/release-lanes.json")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base-sha", help="previous delivered main SHA (required unless --auto)")
    parser.add_argument("--source-sha", help="exact SHA to build/deploy (required unless --auto)")
    parser.add_argument("--auto", action="store_true",
                        help="timer mode: take --base-sha/--source-sha from the unit's "
                             "EnvironmentFile (HARNESS_BASE_SHA/HARNESS_SOURCE_SHA); "
                             "absent or malformed = denied, never reconstructed")
    parser.add_argument("--auto-main", action="store_true",
                        help="trusted-main auto lane: verified main tip replaces the "
                             "operator pin; every changed auto service is built and "
                             "promoted with digest, health and rollback")
    parser.add_argument("--service", choices=sorted(SERVICES),
                        help="explicit operator-only lane: release one admitted service while"
                             " reporting other paths as pending; incompatible with --auto")
    parser.add_argument("--artifact-dir")
    parser.add_argument("--attestation-key")
    parser.add_argument("--state-dir", default=str(STATE_ROOT / "delivery"))
    parser.add_argument("--now", help="ISO-8601 evaluation time (operator canaries)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    host = Host()
    try:
        manifest = load_gate_file(args.manifest, "manifest", require_root=False)
        # One evaluation instant for the whole cycle, so an operator canary with
        # --now is reproducible across the build and release stages alike.
        from harness_release_admission import parse_time

        now = parse_time(args.now) if args.now else None
        if args.auto_main:
            if args.auto or args.service:
                raise Denied("auto_main_exclusive")
            return auto_main_cycle(args, manifest, host)
        base_sha, source_sha = resolve_source_range(args)
        if args.auto and not args.source_sha:
            # Explicit --source-sha is an operator pin and must never be
            # silently promoted to a newer checkout tip.
            # Source SHA may follow an already advanced, clean checkout; the
            # operator's last-delivered BASE must never be advanced on a tick.
            # check_upstream_source below verifies exact live GitHub main and
            # refuses a dirty or stale checkout before ANY build/deploy call.
            source_sha = resolve_verified_checkout_tip(args.repo, source_sha, base_sha)
        if args.service and args.auto:
            raise Denied("scoped_auto_not_allowed")
        if args.service and args.mode != "plan" and os.geteuid() != 0:
            raise Denied("scoped_operator_required")
        # Release admission checks only source freshness here. Runtime health,
        # per-service digest and rollback are verified when a specific service
        # is admitted, never globally as a precondition to an idle source tick.
        if args.auto:
            try:
                check_upstream_source(args.repo, source_sha)
            except ParityFailure as exc:
                raise Denied("source_parity:" + str(exc)) from exc
        global_paths = (git_changed_paths(args.repo, base_sha, source_sha)
                        if base_sha != source_sha else [])
        unknown_baselines = []
        if args.auto:
            # Compare every modeled service with its last *actually delivered*
            # source SHA; advancing an operator checkout never consumes its
            # pending release. No new cursor or state store is introduced.
            backlog, unknown_baselines = pending_per_service_source_paths(
                args.repo, source_sha, args.state_dir, manifest)
            owned = tuple(spec["folder"] + "/" for spec in SERVICES.values())
            global_paths = sorted({path for path in global_paths
                                   if not path.startswith(owned)} | set(backlog))
        if not global_paths:
            print(json.dumps({"mode": args.mode, "source_sha": source_sha,
                              "result": "source_range_unchanged",
                              "runtime_parity": "not_claimed",
                              "unverified_service_baselines": unknown_baselines,
                              "release_complete": False}, sort_keys=True))
            return 0
        # A scoped release is operator-explicit, never silently chosen by the
        # unattended timer. Every included service still needs the exact SHA,
        # independent review, per-UUID grant, and signed digest attestation.
        all_paths = global_paths
        if args.service:
            folder = SERVICES[args.service]["folder"]
            paths = [p for p in all_paths if p == folder or p.startswith(folder + "/")]
            if not paths:
                raise Denied("selected_service_unchanged")
        else:
            paths = all_paths
        entries = {entry.get("id"): entry
                   for entry in (manifest.get("lanes") or []) + (manifest.get("other_resources") or [])
                   if isinstance(entry, dict)}
        # A held resource without a reviewed transport must stay outside this
        # controller. Report it as pending; never pretend it was deployed.
        unmodelled = sorted(service for service in entries
                            if service not in SERVICES
                            and any(path == service or path.startswith(service + "/") for path in paths))
        held = [service for service in unmodelled
                if (entries[service].get("promotion_state") == "hold"
                    and entries[service].get("auto_deploy_expected") is False
                    and entries[service].get("review_required") is True)]
        unsupported = sorted(set(unmodelled) - set(held))
        if unsupported:
            raise Denied("service_not_in_transport:" + ",".join(unsupported))
        manual_paths = {p for p in paths for service in held
                        if p == service or p.startswith(service + "/")}
        paths = [p for p in paths if p not in manual_paths]
        pending_paths = sorted((set(all_paths) - set(paths)) if args.service
                               else manual_paths)
        attributed = {}
        for path in paths:
            for service, spec in SERVICES.items():
                if path == spec["folder"] or path.startswith(spec["folder"] + "/"):
                    attributed.setdefault(service, []).append(path)
        # A removed source directory cannot be built. Defer only explicitly
        # manual/reviewed retirements; otherwise refuse rather than silently
        # skipping a service that is expected to deploy.
        retired = []
        for service in sorted(attributed):
            if (Path(args.repo) / SERVICES[service]["folder"]).is_dir():
                continue
            entry = entries.get(service)
            if entry is None:
                # Unknown modeled services are denied by the existing admission
                # gate, not converted into a supposed retirement.
                continue
            if not (entry.get("auto_deploy_expected") is False
                    and entry.get("review_required") is True
                    and (entry.get("promotion_state") == "hold"
                         or entry.get("mode") == "manual_pinned")):
                raise Denied("missing_build_context:" + service)
            if args.service:
                raise Denied("selected_source_unavailable:" + service)
            pending_paths.extend(attributed.pop(service))
            retired.append(service)
        # A changed build definition outside the reviewed transport must never
        # be silently treated as shipped with an admitted MCP service.
        # Other unclassified paths remain pending, rather than being included
        # in an unscoped release_complete claim.
        accounted = {path for changed in attributed.values() for path in changed}
        unclassified_paths = sorted(set(paths) - accounted - set(pending_paths))
        unexpected_builds = sorted({path.split("/", 1)[0] for path in unclassified_paths
            if path.split("/", 1)[0] != "ops"
            and (Path(path).name.startswith("Dockerfile")
                 or Path(path).name in ("docker-compose.yml", "docker-compose.yaml",
                                       "compose.yml", "compose.yaml"))})
        if unexpected_builds:
            raise Denied("unclassified_build_source:" + ",".join(unexpected_builds))
        pending_paths = sorted(set(pending_paths) | set(unclassified_paths))
        report: dict = {"mode": args.mode, "source_sha": source_sha,
                  "scope": args.service or "all",
                  # Never report a scoped service release as delivery of the
                  # entire main range. This ledger is necessary for downstream
                  # Done/E2E checking and for the next per-lane release.
                  "pending_paths": pending_paths,
                  "held_outside_transport": held,
                  "retired_source_pending": retired,
                  "unverified_service_baselines": unknown_baselines,
                  "release_complete": False,
                  "services": {service: {"changed_paths": sorted(changed)}
                               for service, changed in sorted(attributed.items())},
                  "admitted": [], "denied": {}, "prepared": {}, "deployed": None}
        # Unattended releases are per-service: a held or unrequested service
        # remains visible as pending, but must not block a separate *approved*
        # service. Never make a blanket approval or trust a missing request.
        awaiting_evidence = []
        if args.auto and args.mode in ("prepare", "deploy"):
            for service in sorted(list(attributed)):
                request_path = Path(args.artifact_dir or "") / f"{service}-request.json"
                if not args.artifact_dir or not request_path.is_file():
                    awaiting_evidence.append(service)
                    pending_paths.extend(attributed.pop(service))
            report["pending_paths"] = sorted(set(pending_paths))
            report["services"] = {
                service: {"changed_paths": sorted(changed)}
                for service, changed in sorted(attributed.items())}
            report["awaiting_release_evidence"] = awaiting_evidence
        if not attributed:
            if awaiting_evidence:
                report["result"] = "pending_release_evidence"
            else:
                report["result"] = "held_manual_pending" if held or retired else "no_service_change"
            print(json.dumps(report, sort_keys=True))
            return 1 if awaiting_evidence or held or retired else 0
        # Phase 1: admit EVERY changed service before ANY preparation or
        # deployment. A partial set of valid grants must not cause a partial
        # production release. Plan mode checks the same real evidence as deploy
        # (including an HMAC-verified attestation), without touching the host.
        bundles = {}
        auto_missing = []
        policies = {}
        for service in sorted(attributed):
            if not entries.get(service):
                report["denied"][service] = "unknown_service"
                continue
            bundle = {}
            if args.artifact_dir:
                try:
                    bundle = load_artifacts(args.artifact_dir, service, args.attestation_key,
                                            allow_missing_attestation=(args.mode == "prepare" or
                                                (args.auto and args.mode == "deploy")))
                except Denied as exc:
                    report["denied"][service] = str(exc)
                    continue
            bundles[service] = bundle
            try:
                if args.mode == "prepare" or (args.auto and args.mode == "deploy"
                        and bundle.get("attestation") is None):
                    evaluate_build(manifest, bundle.get("request"), grant=bundle.get("grant"),
                                   now=now, expected_source_sha=source_sha)
                    if args.auto and args.mode == "deploy":
                        policies[service] = auto_ci_policy(
                            service, args.repo, args.attestation_key)
                        auto_missing.append(service)
                else:
                    evaluate(manifest, bundle.get("request"), grant=bundle.get("grant"),
                             attestation=bundle.get("attestation"), now=now,
                             expected_source_sha=source_sha)
                    if args.auto and args.mode == "deploy":
                        # The HMAC verifies integrity, not freshness of host CI
                        # policy. Fail closed before any Docker/Coolify call if
                        # a policy or key is revoked, absent, or changed.
                        policy = auto_ci_policy(service, args.repo, args.attestation_key)
                        policies[service] = policy
                        existing = bundle.get("attestation")
                        if (not isinstance(existing, dict)
                                or existing.get("policy_digest") != policy["_verified_digest"]):
                            raise Denied("auto_ci_policy_digest_mismatch")
                report["admitted"].append(service)
            except Denied as exc:
                report["denied"][service] = str(exc)

        if report["denied"] or len(report["admitted"]) != len(attributed):
            report["result"] = "denied"
            print(json.dumps(report, sort_keys=True))
            return 1

        # Phase 2: mutate only after complete admission. In particular, an
        # automation runner must never interpret an admission refusal as a
        # successful exit status (the old code returned 0 for held lanes).
        if args.mode == "deploy" and auto_missing:
            # Preflight ALL changed services first. Build only once every
            # review, exact-SHA grant, and CI policy has passed.
            for service in auto_missing:
                try:
                    attested, digest = auto_prepare_and_attest(
                        host, args.repo, base_sha, source_sha, service,
                        bundles[service], args.attestation_key,
                        policy=policies[service])
                    bundles[service]["attestation"] = attested
                    evaluate(manifest, bundles[service].get("request"),
                             grant=bundles[service].get("grant"),
                             attestation=attested, now=now,
                             expected_source_sha=source_sha)
                    report["prepared"][service] = {
                        "image_digest": digest, "signed_local_ci": True}
                except (Denied, OSError, RuntimeError, ValueError) as exc:
                    report["denied"][service] = (
                        str(exc) if isinstance(exc, Denied)
                        else "auto_ci_or_prepare_failed")
                    report["result"] = "denied"
                    print(json.dumps(report, sort_keys=True))
                    return 1

        if args.mode == "prepare":
            for service in report["admitted"]:
                tag, digest = prepare(host, args.repo, service, source_sha)
                report["prepared"][service] = {"tag": tag, "image_digest": digest}
        elif args.mode == "deploy":
            transport = (Transport(host, registry=GHCR,
                           expected_digests={
                               name: value["request"]["image_digest"]
                               for name, value in bundles.items()
                               if isinstance(value.get("request"), dict)
                           }) if args.auto else Transport(host))
            report["deployed"] = run_promotion(
                manifest,
                [path for changed in attributed.values() for path in changed],
                lambda service: bundles[service], transport,
                now=now,
                lock_path=str(Path(args.state_dir) / "delivery.lock"),
                state_path=str(Path(args.state_dir) / "delivery.json"),
                source_sha=source_sha)
            decisions = report["deployed"].get("decisions", [])
            good = {"promoted", "already_delivered"}
            if (len(decisions) != len(attributed)
                    or any(decision.get("decision") not in good for decision in decisions)
                    or report["deployed"].get("result") == "denied"):
                report["result"] = "denied"
                print(json.dumps(report, sort_keys=True))
                return 1

        # A successful per-lane release is NOT delivery of the complete main
        # range. Keep the global success marker exclusive to unscoped batches.
        report["result"] = ("ok_scoped" if args.service else
                            "partial_manual_pending" if held or retired else
                            "partial_release_pending" if pending_paths else "ok")
        # Positive plan/prepare is only release admission. Never mark a full
        # release without a real deployed digest/health readback and no pending
        # paths; scoped releases also cannot certify unrelated changes.
        report["release_complete"] = bool(args.mode == "deploy"
            and not args.service and not pending_paths and report.get("deployed")
            and report["deployed"].get("promoted"))
        print(json.dumps(report, sort_keys=True))
        return 0
    except Denied as exc:
        print(json.dumps({"result": "denied", "reason": str(exc),
                          "release_complete": False}), file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"result": "error", "reason": str(exc)[:300]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

