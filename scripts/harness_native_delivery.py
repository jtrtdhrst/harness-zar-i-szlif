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

Two invocation modes, one CLI (``build_parser``) shared with the install
preflight:

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
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from harness_delivery_controller import git_changed_paths, load_artifacts, run_promotion
from harness_release_admission import SHA, Denied, evaluate, evaluate_build, load_gate_file

REPO = "miloszspyrka-code/harness-zar-i-szlif"
REGISTRY = "127.0.0.1:5000"
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
    prefixes = sorted({spec["image_prefix"], current}, key=len, reverse=True)
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

    def __init__(self, host, registry=REGISTRY):
        self.host = host
        self.registry = registry
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
        self._rollback_snapshots.pop(key, None)
        def record_snapshot(path):
            self._rollback_snapshots[key] = path
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
        healthy = "(healthy)" in running and str(service_state.get("status") or "").startswith("running:healthy")
        return {"status": "ok" if healthy and probe_ok else "unhealthy",
                "digest": repo_digests.split("@", 1)[1] if "@" in repo_digests else None,
                "source_sha": revision or None}

    def rollback(self, service, uuid):
        self._known(service)
        backup = self._rollback_snapshots.pop((service, uuid), None)
        if backup is None:
            raise RuntimeError(f"{service}: no snapshot from this deployment attempt")
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
                if current_compose == raw and self.health(service, uuid).get("status") == "ok":
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


def build_parser():
    """The adapter's only CLI surface.

    ``harness_install_preflight`` parses the installed unit's ``ExecStart`` with
    exactly this parser, so an installed invocation and these arguments can never
    drift apart again.
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
        base_sha, source_sha = resolve_source_range(args)
        if base_sha == source_sha:
            # Nothing changed since the last processed main SHA: this is the
            # timer's steady state, and it touches neither docker nor Coolify.
            print(json.dumps({"mode": args.mode, "source_sha": source_sha,
                              "result": "no_change"}, sort_keys=True))
            return 0
        paths = git_changed_paths(args.repo, base_sha, source_sha)
        entries = {entry.get("id"): entry
                   for entry in (manifest.get("lanes") or []) + (manifest.get("other_resources") or [])
                   if isinstance(entry, dict)}
        # A manifest service this transport does not implement must stop the run
        # rather than be skipped: the changed source would be unreleasable and an
        # attempt to promote it must fail before any host call.
        unmodelled = sorted(service for service in entries
                            if service not in SERVICES
                            and any(path == service or path.startswith(service + "/") for path in paths))
        if unmodelled:
            raise Denied("service_not_in_transport:" + ",".join(unmodelled))
        attributed = {}
        for path in paths:
            for service, spec in SERVICES.items():
                if path == spec["folder"] or path.startswith(spec["folder"] + "/"):
                    attributed.setdefault(service, []).append(path)
        report: dict = {"mode": args.mode, "source_sha": source_sha,
                  "services": {service: {"changed_paths": sorted(changed)}
                               for service, changed in sorted(attributed.items())},
                  "admitted": [], "denied": {}, "prepared": {}, "deployed": None}
        if not attributed:
            report["result"] = "no_service_change"
            print(json.dumps(report, sort_keys=True))
            return 0
        # Phase 1: admit EVERY changed service before ANY preparation or
        # deployment. A partial set of valid grants must not cause a partial
        # production release. Plan mode checks the same real evidence as deploy
        # (including an HMAC-verified attestation), without touching the host.
        bundles = {}
        for service in sorted(attributed):
            if not entries.get(service):
                report["denied"][service] = "unknown_service"
                continue
            bundle = {}
            if args.artifact_dir:
                try:
                    bundle = load_artifacts(args.artifact_dir, service, args.attestation_key,
                                            allow_missing_attestation=args.mode == "prepare")
                except Denied as exc:
                    report["denied"][service] = str(exc)
                    continue
            bundles[service] = bundle
            try:
                if args.mode == "prepare":
                    evaluate_build(manifest, bundle.get("request"), grant=bundle.get("grant"),
                                   now=now, expected_source_sha=source_sha)
                else:
                    evaluate(manifest, bundle.get("request"), grant=bundle.get("grant"),
                             attestation=bundle.get("attestation"), now=now,
                             expected_source_sha=source_sha)
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
        if args.mode == "prepare":
            for service in report["admitted"]:
                tag, digest = prepare(host, args.repo, service, source_sha)
                report["prepared"][service] = {"tag": tag, "image_digest": digest}
        elif args.mode == "deploy":
            report["deployed"] = run_promotion(
                manifest, paths, lambda service: bundles[service], Transport(host),
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

        report["result"] = "ok"
        print(json.dumps(report, sort_keys=True))
        return 0
    except Denied as exc:
        print(json.dumps({"result": "denied", "reason": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"result": "error", "reason": str(exc)[:300]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
