#!/usr/bin/env python3
"""Non-root, no-inference Landlock role ACL regression canary (ZARI-213).

Usage: run against a real authorized task checkout/home as Unix user multica-zar.
This script never reads the bytes of any foreign role file or model credential.
"""
from __future__ import annotations
import argparse
import errno
import json
import os
from pathlib import Path
import re
import runpy

ROLE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHARED = Path("/srv/multica-zar/.hermes")
MIRRORS = Path("/srv/multica-zar/workspaces/.repos")
WORKSPACES = Path("/srv/multica-zar/workspaces")


def can_open(path: Path) -> bool:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        os.close(fd)
        return True
    except PermissionError:
        return False


def can_list(path: Path) -> bool:
    try:
        os.listdir(path)
        return True
    except PermissionError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--session-home", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--own-role", required=True)
    parser.add_argument("--foreign-role", required=True)
    parser.add_argument("--policy", default=str(Path(__file__).with_name("zari213-hermes-task-landlock.py")))
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit("FAIL: canary must not run as root")
    if not UUID.fullmatch(args.agent_id):
        raise SystemExit("FAIL: malformed agent identity")
    if (not ROLE.fullmatch(args.own_role) or not ROLE.fullmatch(args.foreign_role)
            or args.own_role == args.foreign_role or args.own_role == "default"):
        raise SystemExit("FAIL: invalid/distinct named role required")

    work = Path(args.workdir).resolve(strict=True)
    home = Path(args.session_home).resolve(strict=True)
    base = Path("/srv/multica-zar/.multica/profiles/zar-prod/hermes-sessions") / args.agent_id
    if not work.is_relative_to(WORKSPACES) or len(work.relative_to(WORKSPACES).parts) != 3:
        raise SystemExit("FAIL: expected a task workdir")
    if home.parent.name != args.own_role or home.parent.parent != base:
        raise SystemExit("FAIL: session home does not belong to agent+role")
    if not (work / ".git").exists() and not work.is_dir():
        raise SystemExit("FAIL: task workdir missing")

    os.environ["MULTICA_AGENT_ID"] = args.agent_id
    os.environ["HERMES_HOME"] = str(home)
    os.environ["TMPDIR"] = str(work)
    os.chdir(work)

    policy = runpy.run_path(str(Path(args.policy).resolve(strict=True)))
    policy["restrict"](work.parent, work)

    checks = {
        "own_profile_read": can_open(SHARED / "profiles" / args.own_role / "SOUL.md"),
        "foreign_profile_denied": not can_open(SHARED / "profiles" / args.foreign_role / "SOUL.md"),
        "global_state_denied": not can_open(SHARED / "state.db"),
        "bare_mirror_denied": not can_list(MIRRORS),
        "other_tasks_root_denied": not can_list(work.parent.parent),
        "own_session_list": can_list(home),
    }

    fixture = work / (".zari213-landlock-probe-" + str(os.getpid()))
    try:
        fd = os.open(fixture, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(b"ZARI-213 test fixture")
        checks["own_task_write_read"] = fixture.read_bytes() == b"ZARI-213 test fixture"
    finally:
        if fixture.exists():
            fixture.unlink()

    failed = [name for name, ok in checks.items() if not ok]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
