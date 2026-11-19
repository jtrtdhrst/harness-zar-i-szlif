#!/usr/bin/env python3
"""Read-only upstream, checkout and runtime parity gate for a Harness service.

No Docker/Coolify/git mutation, no release approval, no secret extraction.
A healthy old container is not successful delivery of merged source changes.
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
TAG = re.compile(r":([0-9a-f]{12,40})\Z")


class ParityFailure(Exception):
    pass


def command(argv, *, runner=subprocess.run):
    try:
        result = runner(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ParityFailure("proof_command_unavailable") from exc
    return result.returncode, result.stdout.strip()


def checked(argv, fail_code, *, runner=subprocess.run):
    rc, output = command(argv, runner=runner)
    if rc:
        raise ParityFailure(fail_code)
    return output


def check_source(repo, expected_sha, *, runner=subprocess.run):
    if not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha):
        raise ParityFailure("expected_sha_invalid")
    # Validate the expanded origin before trusting an upstream SHA. Never print
    # a URL: it can contain credentials, and a lookalike host is not GitHub.
    origin = checked(["git", "-C", str(repo), "remote", "get-url", "origin"],
                     "source_remote_unverifiable", runner=runner)
    trusted = (
        r"https://github\.com/miloszspyrka-code/harness-zar-i-szlif(?:\.git)?",
        r"git@github\.com:miloszspyrka-code/harness-zar-i-szlif(?:\.git)?",
        r"ssh://git@github\.com/miloszspyrka-code/harness-zar-i-szlif(?:\.git)?",
    )
    if not any(re.fullmatch(pattern, origin, flags=re.IGNORECASE) for pattern in trusted):
        raise ParityFailure("source_remote_untrusted")
    # Remote-tracking refs may be weeks old; query the verified real origin.
    # Fail closed on missing credentials without echoing stderr.
    head = checked(["git", "-C", str(repo), "ls-remote", "--exit-code",
                    "origin", "refs/heads/main"],
                   "upstream_main_unverifiable", runner=runner)
    lines = head.splitlines()
    if len(lines) != 1 or not re.fullmatch(r"[0-9a-f]{40}\trefs/heads/main", lines[0]):
        raise ParityFailure("upstream_main_unverifiable")
    upstream_sha = lines[0].split("\t", 1)[0]
    if upstream_sha != expected_sha:
        raise ParityFailure("source_range_stale")
    local_sha = checked(["git", "-C", str(repo), "rev-parse", "HEAD"],
                        "checkout_unverifiable", runner=runner)
    if local_sha != upstream_sha:
        raise ParityFailure("checkout_stale")

    return upstream_sha

def _check_runtime(repo, expected_sha, service, *, runner=subprocess.run):
    manifest = json.loads((Path(repo) / "ops/release-lanes.json").read_text())
    entries = manifest.get("lanes", []) + manifest.get("other_resources", [])
    matches = [entry for entry in entries
               if isinstance(entry, dict) and entry.get("id") == service]
    if len(matches) != 1:
        raise ParityFailure("service_manifest_missing_or_ambiguous")
    entry = matches[0]
    uuid = entry.get("coolify_uuid")
    if (entry.get("platform") not in (None, "coolify") or not isinstance(uuid, str)
            or not re.fullmatch(r"[a-z0-9]{10,40}", uuid)):
        raise ParityFailure("service_uuid_invalid")
    if not (Path(repo) / service).is_dir():
        raise ParityFailure("service_source_unavailable")

    ids = checked(["docker", "ps", "--filter",
                   f"label=coolify.serviceUuid={uuid}", "--format", "{{.ID}}"],
                  "runtime_unverifiable", runner=runner).splitlines()
    if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{12,64}", ids[0]):
        raise ParityFailure("runtime_missing_or_ambiguous")
    # Never request .Config as a whole: it includes container environment
    # secrets. Project only the two fields needed for runtime parity.
    raw = checked(["docker", "inspect", ids[0], "--format",
                   "{{json .Config.Labels}}" + "\n" + "{{json .Config.Image}}"],
                  "runtime_unverifiable", runner=runner)
    try:
        lines = raw.splitlines()
        if len(lines) != 2:
            raise ParityFailure("runtime_metadata_invalid")
        labels, image = (json.loads(lines[0]) or {}), json.loads(lines[1])
        if not isinstance(labels, dict) or not isinstance(image, str):
            raise ParityFailure("runtime_metadata_invalid")
        config = {"Labels": labels, "Image": image}
        if labels.get("coolify.serviceUuid") != uuid:
            raise ParityFailure("runtime_uuid_mismatch")
        revision = labels.get("org.opencontainers.image.revision")
        if revision is None:
            match = TAG.search(config.get("Image", ""))
            revision = match.group(1) if match else ""
        if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{12,40}", revision):
            raise ParityFailure("runtime_revision_missing")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ParityFailure("runtime_metadata_invalid") from exc
    full_revision = checked(["git", "-C", str(repo), "rev-parse", "--verify",
                             f"{revision}^{{commit}}"],
                            "runtime_revision_unverifiable", runner=runner)
    if not SHA.fullmatch(full_revision):
        raise ParityFailure("runtime_revision_unverifiable")

    # Compare only the service directory; unrelated merges do not imply the
    # running service is stale. Errors and absent Git history are NOT PASS.
    rc, _ = command(["git", "-C", str(repo), "diff", "--quiet", full_revision,
                     expected_sha, "--", service + "/"], runner=runner)
    if rc == 1:
        raise ParityFailure("service_changes_not_deployed")
    if rc:
        raise ParityFailure("service_diff_unverifiable")
    return {"result": "parity_ok", "service": service, "source_sha": expected_sha,
            "runtime_revision": full_revision, "coolify_uuid": uuid}



def check(repo, expected_sha, service="plasmic-mcp", *, runner=subprocess.run):
    check_source(repo, expected_sha, runner=runner)
    return _check_runtime(repo, expected_sha, service, runner=runner)


def check_services(repo, expected_sha, services, *, runner=subprocess.run):
    """Verify one real upstream SHA and every service before global no_change."""
    if not services or len(set(services)) != len(services):
        raise ParityFailure("managed_service_scope_missing_or_ambiguous")
    check_source(repo, expected_sha, runner=runner)
    verified = []
    for service in services:
        try:
            verified.append(_check_runtime(repo, expected_sha, service, runner=runner))
        except ParityFailure as exc:
            raise ParityFailure(f"{service}:{exc}") from exc
    return {"result": "parity_ok", "source_sha": expected_sha,
            "services": [item["service"] for item in verified]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="/var/lib/harness-image-delivery/checkout")
    parser.add_argument("--service", default="plasmic-mcp")
    parser.add_argument("--expected-sha", default=os.environ.get("HARNESS_SOURCE_SHA", ""))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(check(args.repo, args.expected_sha, args.service), sort_keys=True))
        return 0
    except (ParityFailure, ValueError, OSError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, ParityFailure) else "parity_input_unverifiable"
        print(json.dumps({"result": "blocked", "service": args.service,
                          "reason": reason}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
