#!/usr/bin/python3
"""Root-operated, fail-closed projection of provider-scoped Hermes .env files.

Never logs credential content. This does not solve shared Codex OAuth token
isolation; that requires an independent model-credential broker.
"""
import argparse
import os
import pathlib
import pwd
import re
import stat
import tempfile

ROOT = pathlib.Path("/srv/multica-zar/.hermes")
ROLE_PROVIDER = {
    "ceo": "openai-codex", "cho": "openai-codex", "cmo": "openai-codex",
    "coo": "openai-codex", "cpo": "openai-codex", "cto": "openai-codex",
    "designer": "opencode-go", "email-creative": "opencode-go",
    "engineer": "opencode-go", "harness-engineer": "opencode-go",
    "lifecycle-ops": "opencode-go", "mascot-designer": "opencode-go",
    "mcp-engineer": "opencode-go", "ui-qa": "opencode-go",
}
MARKER = "# multica-provider-env-projection-v1"
LINE = re.compile(r"^OPENCODE_GO_API_KEY=([^\r\n]+)$")


def _source_key(source, uid):
    fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != uid or st.st_mode & 0o077:
            raise RuntimeError("unexpected source .env file ownership/type/permissions")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            data = handle.read()
    finally:
        if fd != -1:
            os.close(fd)
    lines = [line.strip() for line in data.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) != 1:
        raise RuntimeError("provider .env schema drift: expected exactly one key")
    m = LINE.fullmatch(lines[0])
    if not m or len(m.group(1)) < 8:
        raise RuntimeError("provider .env schema drift: expected OPENCODE_GO_API_KEY")
    return m.group(1)


def _provider(profile_dir):
    # No external YAML dependency in this tiny root-owned projector.
    # Parse only root-level 'model' and its indented 'provider' (require unique).
    lines = (profile_dir / "config.yaml").read_text(encoding="utf-8").splitlines()
    inside = False
    found = []
    for line in lines:
        if line.startswith("model:"):
            if inside:
                raise RuntimeError("duplicate model config block")
            inside = True
        elif inside and line and not line[0].isspace() and not line.startswith("#"):
            inside = False
        elif inside:
            match = re.fullmatch(r"  provider:\s*([a-z0-9-]+)\s*", line)
            if match:
                found.append(match.group(1))
    if len(found) != 1:
        raise RuntimeError("role config provider not unambiguous")
    return found[0]


def project(root=ROOT, uid=None, gid=None, apply=False):
    # Guard must execute before *any* credential read or profile mutation.
    if os.geteuid() == 0:
        raise PermissionError("root execution refused: run as multica-zar")
    root = pathlib.Path(root)
    if uid is None:
        account = pwd.getpwnam("multica-zar")
        uid, gid = account.pw_uid, account.pw_gid
    if os.geteuid() != uid:
        raise PermissionError("executor identity does not own role profiles")
    global_env = root / ".env"
    key = _source_key(global_env, uid)
    profiles = root / "profiles"
    if profiles.is_symlink() or not profiles.is_dir():
        raise RuntimeError("role profile directory invalid")
    prepared = []
    for role, expected_provider in ROLE_PROVIDER.items():
        directory = profiles / role
        st = directory.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid or st.st_mode & 0o077:
            raise RuntimeError(f"role directory invalid: {role}")
        if _provider(directory) != expected_provider:
            raise RuntimeError(f"role model provider drift: {role}")
        dest = directory / ".env"
        if dest.is_symlink():
            if dest.readlink() != global_env:
                raise RuntimeError(f"unexpected role .env symlink: {role}")
        elif dest.exists():
            st = dest.lstat()
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != uid
                    or st.st_mode & 0o077):
                raise RuntimeError(f"role .env not owned/private: {role}")
            with dest.open(encoding="utf-8") as handle:
                first = handle.readline().rstrip("\n")
            if first != MARKER:
                raise RuntimeError(f"refusing to overwrite unmanaged role .env: {role}")
        else:
            raise RuntimeError(f"missing role .env: {role}")
        expected = (MARKER + "\n" + "# role=" + role + "; provider=" + expected_provider + "\n")
        if expected_provider == "opencode-go":
            expected += "OPENCODE_GO_API_KEY=" + key + "\n"
        current = None if dest.is_symlink() else dest.read_text(encoding="utf-8")
        prepared.append((role, directory, dest, expected, current))
    changed = [r for r in prepared if r[4] != r[3]]
    if not apply:
        return {"checked": len(prepared), "changes_needed": len(changed),
                "role_names": [r[0] for r in changed]}
    for role, directory, dest, expected, current in changed:
        fd, temp = tempfile.mkstemp(prefix=".env.project-", dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                fd = -1
                out.write(expected)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, dest)
            temp = None
        finally:
            if fd != -1:
                os.close(fd)
            if temp is not None:
                os.unlink(temp)
    return {"checked": len(prepared), "changed": len(changed),
            "role_names": [r[0] for r in changed]}


def main():
    if os.geteuid() == 0:
        raise SystemExit("root execution refused: run as multica-zar")
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    # Secret values never enter stdout/logs.
    print(project(apply=args.apply))


if __name__ == "__main__":
    main()
