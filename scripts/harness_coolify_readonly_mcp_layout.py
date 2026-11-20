#!/usr/bin/env python3
"""Fail-closed read-only preflight for the Harness Engineer Coolify MCP socket broker.

This verifies the reviewed installed module, root-owned wrapper, systemd
sandbox/credential wiring and agent-scoped Unix socket. No secret is opened,
no Coolify API write is performed and this does not authorize deployment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

ROOT = Path("/opt/multica-tools/coolify-harness-ro")
ENTRY = Path("node_modules/@masonator/coolify-mcp/dist/index.js")
ENTRY_SHA256 = "6dc1c71c03a5b6160647d6063750bfc4072923fc47f10d8cf3f5ea15a06de2bf"
# Pinned exact root-owned installed objects. Any modification requires new review.
WRAPPER_SHA256 = "a912d95cdaa55ec3d92eecf6fe528d3beb2b36a15ee2b1ed9bc7fd3e126a66e8"
UNIT_SHA256 = "15088adae4d66d5022c29ce4e184c9d0020675771d324a9c84ec777890a05cc3"
WRAPPER = Path("/usr/local/libexec/coolify-harness-readonly-mcp.sh")
UNIT = Path("/etc/systemd/system/coolify-harness-readonly-mcp.service")
SOCKET = Path("/srv/multica-zar/.hermes/profiles/harness-engineer/coolify-mcp-readonly.sock")

class LayoutError(Exception):
    pass

def insist(condition, reason):
    if not condition:
        raise LayoutError(reason)

def regular(path, owner, *, exact_mode=None):
    st = path.lstat()
    insist(stat.S_ISREG(st.st_mode) and st.st_uid == owner, "untrusted_file_identity")
    mode = stat.S_IMODE(st.st_mode)
    insist(not mode & 0o022, "writable_by_other_actor")
    if exact_mode is not None:
        insist(mode == exact_mode, "file_mode_mismatch")

def verify_layout(root=ROOT, wrapper=WRAPPER, unit=UNIT, socket_path=SOCKET,
                  expected_sha=ENTRY_SHA256, owner=0, socket_owner=None,
                  expected_wrapper_sha=WRAPPER_SHA256, expected_unit_sha=UNIT_SHA256):
    if socket_owner is None:
        socket_owner = pwd.getpwnam("multica-zar").pw_uid
    root, wrapper, unit, socket_path = map(Path, (root, wrapper, unit, socket_path))
    st = root.lstat()
    insist(stat.S_ISDIR(st.st_mode) and st.st_uid == owner, "untrusted_package_root")
    insist(not stat.S_IMODE(st.st_mode) & 0o022, "writable_package_root")
    for base, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(base) / name
            st = path.lstat()
            insist(st.st_uid == owner, "untrusted_package_member_owner")
            if path.is_symlink():
                insist(path.resolve().is_relative_to(root.resolve()),
                       "package_symlink_escape")
                continue
            insist(not stat.S_IMODE(st.st_mode) & 0o022, "writable_package_member")
            insist(stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode),
                   "untrusted_package_member_type")
    entry = root / ENTRY
    regular(entry, owner)
    insist(hashlib.sha256(entry.read_bytes()).hexdigest() == expected_sha,
           "package_entry_digest_drift")
    regular(wrapper, owner, exact_mode=0o755)
    insist(hashlib.sha256(wrapper.read_bytes()).hexdigest() == expected_wrapper_sha,
           "wrapper_digest_drift")
    body = wrapper.read_text()
    insist(body.count(f"exec /usr/bin/node {entry}") == 1,
           "wrapper_executable_drift")
    insist("COOLIFY_MCP_REQUIRE_HUMAN='on'" in body,
           "human_approval_guard_missing")
    match = re.search(r'(?m)^TOKEN_FILE="\$CREDENTIALS_DIRECTORY/([A-Za-z0-9_.-]+)"$', body)
    insist(match is not None, "token_not_loaded_via_systemd_credential")
    cred_name = match.group(1)
    regular(unit, owner)
    insist(hashlib.sha256(unit.read_bytes()).hexdigest() == expected_unit_sha,
           "unit_digest_drift")
    # Reject local drop-ins even before systemctl readback; a .conf can override
    # security directives without modifying the reviewed fragment.
    dropins = Path(str(unit) + ".d")
    insist(not (dropins.is_dir() and any(dropins.glob("*.conf"))),
           "systemd_dropin_unreviewed")
    config = unit.read_text()
    requirements = [
        "User=multica-zar", "Group=multica-zar",
        "NoNewPrivileges=yes", "ProtectSystem=strict",
        "CapabilityBoundingSet=", "UMask=0077",
        f"LoadCredential={cred_name}:",
        f"UNIX-LISTEN:{socket_path},fork,unlink-early,mode=0600",
        f"EXEC:{wrapper}",
    ]
    for requirement in requirements:
        insist(requirement in config, "systemd_socket_or_sandbox_wiring_drift")
    st = socket_path.lstat()
    insist(stat.S_ISSOCK(st.st_mode) and st.st_uid == socket_owner,
           "unsafe_agent_socket_identity")
    insist(stat.S_IMODE(st.st_mode) == 0o600, "unsafe_agent_socket_mode")
    return {"status": "PASS", "package_entry_sha256": expected_sha,
            "transport": "agent_scoped_unix_socket", "api_access": "read_only"}

def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        result = verify_layout()
        service = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "coolify-harness-readonly-mcp.service"],
            capture_output=True, text=True, timeout=8)
        insist(service.returncode == 0 and service.stdout.strip() == "active",
               "socket_broker_service_inactive")
        # systemd can overlay /run or /usr drop-ins not visible beside the
        # root-owned fragment. Reject any effective alternate fragment/drop-in.
        effective = subprocess.run(
            ["/usr/bin/systemctl", "show", "coolify-harness-readonly-mcp.service",
             "-p", "FragmentPath", "-p", "DropInPaths"],
            capture_output=True, text=True, timeout=8)
        insist(effective.returncode == 0, "systemd_effective_config_unavailable")
        lines = dict(line.split("=", 1) for line in effective.stdout.splitlines()
                     if "=" in line)
        insist(lines.get("FragmentPath") == str(UNIT)
               and lines.get("DropInPaths") == "", "systemd_effective_unit_drift")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, LayoutError, subprocess.TimeoutExpired, KeyError) as exc:
        reason = str(exc) if isinstance(exc, LayoutError) else "layout_io_unavailable"
        print(json.dumps({"status": "DENIED", "reason": reason}))
        return 1

if __name__ == "__main__":
    sys.exit(main())

