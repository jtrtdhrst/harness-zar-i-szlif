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
"""
import argparse
import base64
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from harness_delivery_controller import git_changed_paths, run_promotion
from harness_release_admission import Denied, evaluate_build, load_gate_file

REPO = "miloszspyrka-code/harness-zar-i-szlif"
REGISTRY = "127.0.0.1:5000"
COOLIFY = "http://127.0.0.1:8001/api/v1"
COOLIFY_TOKEN = Path("/root/coolify-secrets/coolify_api_token")
STATE_ROOT = Path("/var/lib/harness-image-delivery")
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


def patch_compose(host, uuid, service, spec, tag):
    """Point the service's image line at ``tag``; keep a restorable backup."""
    raw = compose_for(host, uuid)
    pattern = image_pattern(service, spec)
    patched, count = pattern.subn(lambda match: f"{match.group(1)}{match.group(2)}{tag}{match.group(2)}", raw)
    if count != 1:
        raise RuntimeError(f"expected exactly one {spec['image_prefix']} image line, found {count}")
    backup = STATE_ROOT / "backups" / f"{service}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.yml"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(raw)
    backup.chmod(0o600)
    status, _ = host.coolify("PATCH", f"/services/{uuid}",
                             {"docker_compose_raw": base64.b64encode(patched.encode()).decode()})
    if status not in (200, 201):
        raise RuntimeError(f"compose patch http {status}")
    return raw, backup


def deploy_service(host, uuid, service, spec, tag):
    raw, backup = patch_compose(host, uuid, service, spec, tag)
    try:
        status, body = host.coolify("POST", "/deploy", {"uuid": uuid})
        if status not in (200, 201):
            raise RuntimeError(f"deploy http {status}")
        deadline = time.time() + HEALTH_DEADLINE
        state = ""
        while time.time() < deadline:
            time.sleep(POLL_SECONDS)
            running = host.docker("ps", "--filter", f"ancestor={tag}", "--format", "{{.Status}}")
            _, current = host.coolify("GET", f"/services/{uuid}")
            state = str(current.get("status") or "")
            if "(healthy)" in running and state.startswith("running:healthy"):
                return raw, backup, body
        raise RuntimeError(f"{service} did not become healthy (status={state})")
    except Exception:
        host.coolify("PATCH", f"/services/{uuid}",
                     {"docker_compose_raw": base64.b64encode(raw.encode()).decode()})
        host.coolify("POST", "/deploy", {"uuid": uuid})
        raise


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

    def current(self, service, uuid):
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
        tag = image_tag(service, source_sha, self.registry)
        reference = self.host.docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", tag)
        if "@" not in reference:
            raise RuntimeError(f"{service}: prepared image has no repository digest")
        digest = reference.split("@", 1)[1]
        if running_revision(self.host, service, digest, self.registry) != source_sha:
            raise RuntimeError(f"{service}: prepared image is not labelled with {source_sha}")
        return digest

    def deploy(self, service, uuid, kind, digest):
        revision = running_revision(self.host, service, digest, self.registry)
        if not isinstance(revision, str) or len(revision) != 40:
            raise RuntimeError(f"{service}: prepared image carries no exact source revision")
        tag = image_tag(service, revision, self.registry)
        _, _, body = deploy_service(self.host, uuid, service, SERVICES[service], tag)
        return str(body.get("deployment_uuid") or body.get("uuid") or "deploy")

    def health(self, service, uuid):
        """Read back what is actually running: image digest, revision label, health."""
        _, service_state = self.host.coolify("GET", f"/services/{uuid}")
        raw = service_state.get("docker_compose_raw") or ""
        match = image_pattern(service, SERVICES[service], self.registry).search(raw)
        if not match:
            return {"status": "no_image", "digest": None, "source_sha": None}
        reference = match.group(0).split("image:", 1)[-1].strip().strip("'\"")
        image_id = self.host.docker("image", "inspect", "--format", "{{.Id}}", reference)
        running = self.host.docker("ps", "--filter", f"ancestor={image_id}", "--format", "{{.Status}}")
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
        backups = sorted((STATE_ROOT / "backups").glob(f"{service}-*.yml"))
        if not backups:
            raise RuntimeError(f"{service}: no compose backup to roll back to")
        raw = backups[-1].read_text(encoding="utf-8")
        self.host.coolify("PATCH", f"/services/{uuid}",
                          {"docker_compose_raw": base64.b64encode(raw.encode()).decode()})
        status, body = self.host.coolify("POST", "/deploy", {"uuid": uuid})
        if status not in (200, 201):
            raise RuntimeError(f"rollback deploy http {status}")
        return str(body.get("deployment_uuid") or body.get("uuid") or "rollback")


def prepare(host, repo, service, source_sha, registry=REGISTRY, log_dir=None):
    """Build and push one service at the exact source SHA, returning its digest."""
    spec = SERVICES[service]
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Admission-gated Harness image delivery")
    parser.add_argument("--mode", choices=("plan", "prepare", "deploy"), default="plan")
    parser.add_argument("--manifest", default="ops/release-lanes.json")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--artifact-dir")
    parser.add_argument("--attestation-key")
    parser.add_argument("--state-dir", default=str(STATE_ROOT / "delivery"))
    parser.add_argument("--now", help="ISO-8601 evaluation time (operator canaries)")
    args = parser.parse_args(argv)

    host = Host()
    try:
        manifest = load_gate_file(args.manifest, "manifest", require_root=False)
        paths = git_changed_paths(args.repo, args.base_sha, args.source_sha)
        attributed = {}
        for path in paths:
            for service, spec in SERVICES.items():
                if path == spec["folder"] or path.startswith(spec["folder"] + "/"):
                    attributed.setdefault(service, []).append(path)
        report: dict = {"mode": args.mode, "source_sha": args.source_sha,
                  "services": {service: {"changed_paths": sorted(changed)}
                               for service, changed in sorted(attributed.items())},
                  "admitted": [], "denied": {}, "prepared": {}, "deployed": None}
        if not attributed:
            report["result"] = "no_service_change"
            print(json.dumps(report, sort_keys=True))
            return 0
        entries = {entry.get("id"): entry
                   for entry in (manifest.get("lanes") or []) + (manifest.get("other_resources") or [])
                   if isinstance(entry, dict)}
        bundles = {}
        for service in sorted(attributed):
            spec = entries.get(service)
            if not spec:
                report["denied"][service] = "unknown_service"
                continue
            request = None
            if args.artifact_dir:
                try:
                    request = load_gate_file(Path(args.artifact_dir) / (service + "-request.json"),
                                             "request", require_root=True)
                    bundle = {"request": request}
                    for kind in ("grant", "attestation"):
                        try:
                            bundle[kind] = load_gate_file(Path(args.artifact_dir) / f"{service}-{kind}.json",
                                                          kind, require_root=True)
                        except Denied as exc:
                            if kind == "grant" and str(exc) == "grant_unavailable":
                                bundle[kind] = None
                                continue
                            raise
                    bundles[service] = bundle
                except Denied as exc:
                    report["denied"][service] = str(exc)
                    continue
            try:
                if args.mode == "prepare":
                    evaluate_build(manifest, request, grant=bundles.get(service, {}).get("grant"))
                    tag, digest = prepare(host, args.repo, service, args.source_sha)
                    report["prepared"][service] = {"tag": tag, "image_digest": digest}
                else:
                    report["admitted"].append(service)
            except Denied as exc:
                report["denied"][service] = str(exc)
        if args.mode == "deploy":
            if not bundles:
                raise Denied("gate_artifacts_missing")
            from harness_release_admission import parse_time

            report["deployed"] = run_promotion(
                manifest, paths, lambda service: bundles.get(service, {}), Transport(host),
                now=parse_time(args.now) if args.now else None,
                lock_path=str(Path(args.state_dir) / "delivery.lock"),
                state_path=str(Path(args.state_dir) / "delivery.json"))
        report["result"] = "ok" if not report["denied"] else "partially_denied"
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
