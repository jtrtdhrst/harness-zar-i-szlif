#!/usr/bin/env python3
"""Kernel Landlock canary: no reading model credentials, only OPEN/CLOSE."""
import argparse
import errno
import json
import os
from pathlib import Path
import runpy

ROOT = Path("/srv/multica-zar/.hermes")
CODEX = set()
OPENCODE = {"ceo", "cho", "cmo", "coo", "cpo", "cto",
            "designer", "email-creative", "engineer", "harness-engineer",
            "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa"}


def probe(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    except OSError as exc:
        return exc.errno
    os.close(fd)
    return 0


def allowed(path):
    return probe(path) == 0


def denied(path):
    return probe(path) == errno.EACCES


def main():
    p = argparse.ArgumentParser()
    for field in ("workdir", "session-home", "agent-id", "own-role", "foreign-role", "policy"):
        p.add_argument("--" + field, required=True)
    p.add_argument("--require-projected-env", action="store_true")
    a = p.parse_args()
    if os.geteuid() == 0:
        raise SystemExit("must run as unprivileged role principal")
    if a.own_role not in CODEX | OPENCODE or a.foreign_role not in CODEX | OPENCODE:
        raise SystemExit("unrecognized role")
    os.environ["MULTICA_AGENT_NAME"] = a.own_role.replace("-", " ").upper()
    os.environ["MULTICA_AGENT_ID"] = a.agent_id
    os.environ["HERMES_HOME"] = a.session_home
    os.environ["TMPDIR"] = a.workdir
    work = Path(a.workdir)
    os.chdir(work)
    policy = runpy.run_path(a.policy)
    policy["restrict"](work.parent, work)
    result = {
        "own_SOUL": allowed(ROOT / "profiles" / a.own_role / "SOUL.md"),
        "foreign_SOUL_denied": denied(ROOT / "profiles" / a.foreign_role / "SOUL.md"),
        "global_env_denied": denied(ROOT / ".env"),
        "foreign_env_denied": denied(ROOT / "profiles" / a.foreign_role / ".env"),
    }
    # Every role is OpenCode-only. Both the global target and this role's
    # auth.json symlink must fail to open under the task kernel policy.
    result["global_codex_auth_denied"] = denied(ROOT / "auth.json")
    result["own_codex_auth_denied"] = denied(ROOT / "profiles" / a.own_role / "auth.json")
    if a.require_projected_env:
        result["own_role_env"] = allowed(ROOT / "profiles" / a.own_role / ".env")
    print(json.dumps({"checks": result, "passed": all(result.values())}, sort_keys=True))
    if not all(result.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
