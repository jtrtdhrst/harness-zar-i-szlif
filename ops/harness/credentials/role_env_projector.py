#!/usr/bin/python3
"""Role-scoped Hermes Codex broker configuration projection.

Runs as multica-zar. Reads only each role's private local broker bearer and
writes only that role's Hermes profile config/.env. It never reads shared
Codex OAuth or the global OpenCode key.
"""
import argparse
import os
import pathlib
import pwd
import re
import stat
import tempfile

ROOT = pathlib.Path("/srv/multica-zar/.hermes")
KEY_ROOT = pathlib.Path("/srv/multica-zar/.config/hermes")
ROLE_PROVIDER = {
    "ceo": "custom:rolebroker",
    "cho": "custom:rolebroker",
    "cmo": "custom:rolebroker",
    "coo": "custom:rolebroker",
    "cpo": "custom:rolebroker",
    "cto": "custom:rolebroker",
    "designer": "custom:rolebroker",
    "email-creative": "custom:rolebroker",
    "engineer": "custom:rolebroker",
    "harness-engineer": "custom:rolebroker",
    "lifecycle-ops": "custom:rolebroker",
    "mascot-designer": "custom:rolebroker",
    "mcp-engineer": "custom:rolebroker",
    "ui-qa": "custom:rolebroker",
}
MARKER = "# multica-provider-env-projection-v1"
BROKER = "rolebroker"
BROKER_PORT = 7468
MODEL = "gpt-6-luna"


def _read_role_key(role, uid, key_root=KEY_ROOT):
    role_dir = key_root / role
    directory = role_dir.lstat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != uid or stat.S_IMODE(directory.st_mode) != 0o700:
        raise RuntimeError(f"role key directory invalid: {role}")
    path = role_dir / "api-key"
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != uid or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1:
            raise RuntimeError(f"role broker key is not private: {role}")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            value = handle.read()
    finally:
        if fd != -1:
            os.close(fd)
    value = value.strip()
    if len(value) < 32 or len(value) > 256 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise RuntimeError(f"role broker key format invalid: {role}")
    return value


def _read_private(path, uid):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != uid or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1:
            raise RuntimeError(f"untrusted role config: {path.name}")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            return handle.read()
    finally:
        if fd != -1:
            os.close(fd)


def _configure(text, role):
    lines = text.splitlines()
    inside = False
    blocks = 0
    provider_idx = []
    for idx, line in enumerate(lines):
        if line.startswith("model:"):
            blocks += 1
            inside = True
        elif inside and line and not line[0].isspace() and not line.startswith("#"):
            inside = False
        elif inside:
            m = re.fullmatch(r"  provider:\\s*([a-z0-9-]+(?::[a-z0-9-]+)?)\\s*", line)
            if m:
                provider_idx.append(idx)
    if blocks != 1 or len(provider_idx) != 1:
        raise RuntimeError(f"role model provider is ambiguous: {role}")
    lines[provider_idx[0]] = "  provider: custom:rolebroker"
    block = [
        "providers:",
        "  rolebroker:",
        "    name: rolebroker",
        f"    base_url: http://127.0.0.1:{BROKER_PORT}/p/{role}/v1",
        "    key_env: ROLE_BROKER_API_KEY",
        "    api_mode: codex_responses",
        f"    default_model: {MODEL}",
    ]
    starts = [i for i, line in enumerate(lines) if line == "providers:"]
    if starts:
        i = starts[0]
        j = i + 1
        while j < len(lines) and (not lines[j] or lines[j][0].isspace() or lines[j].startswith("#")):
            j += 1
        if len(starts) != 1 or lines[i:j] != block:
            raise RuntimeError(f"unmanaged Hermes providers block: {role}")
        return "\\n".join(lines) + "\\n"
    while lines and not lines[-1]:
        lines.pop()
    return "\\n".join(lines + [""] + block) + "\\n"


def _atomic_replace(path, content):
    fd, temp = tempfile.mkstemp(prefix=".provider.project-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            fd = -1
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        temp = None
    finally:
        if fd != -1:
            os.close(fd)
        if temp is not None:
            os.unlink(temp)


def project(root=ROOT, key_root=KEY_ROOT, uid=None, gid=None, apply=False):
    if os.geteuid() == 0:
        raise PermissionError("root execution refused: run as multica-zar")
    root, key_root = pathlib.Path(root), pathlib.Path(key_root)
    if uid is None:
        account = pwd.getpwnam("multica-zar")
        uid, gid = account.pw_uid, account.pw_gid
    if os.geteuid() != uid:
        raise PermissionError("executor identity does not own role profiles")
    profiles = root / "profiles"
    if profiles.is_symlink() or not profiles.is_dir():
        raise RuntimeError("role profile directory invalid")
    prepared = []
    for role, expected_provider in ROLE_PROVIDER.items():
        directory = profiles / role
        d = directory.lstat()
        if not stat.S_ISDIR(d.st_mode) or d.st_uid != uid or stat.S_IMODE(d.st_mode) != 0o700:
            raise RuntimeError(f"role profile directory invalid: {role}")
        config_path = directory / "config.yaml"
        config_old = _read_private(config_path, uid)
        config_new = _configure(config_old, role)
        env_path = directory / ".env"
        if env_path.is_symlink():
            if env_path.readlink() != root / ".env":
                raise RuntimeError(f"unexpected role .env symlink: {role}")
            env_old = None
        else:
            env_old = _read_private(env_path, uid)
            if not env_old.startswith(MARKER + "\\n"):
                raise RuntimeError(f"refusing to overwrite unmanaged role .env: {role}")
        key = _read_role_key(role, uid, key_root)
        env_new = f"{MARKER}\\n# role={role}; provider={expected_provider}\\nROLE_BROKER_API_KEY={key}\\n"
        prepared.append((role, config_path, config_old, config_new, env_path, env_old, env_new))
    changed = [item for item in prepared if item[2] != item[3] or item[5] != item[6]]
    if not apply:
        return {"checked": len(prepared), "changes_needed": len(changed), "role_names": [r[0] for r in changed]}
    for role, config_path, _, config_new, env_path, env_old, env_new in changed:
        _atomic_replace(config_path, config_new)
        if env_old != env_new:
            _atomic_replace(env_path, env_new)
    return {"checked": len(prepared), "changed": len(changed), "role_names": [r[0] for r in changed]}


def main():
    if os.geteuid() == 0:
        raise SystemExit("root execution refused: run as multica-zar")
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(project(apply=args.apply))


if __name__ == "__main__":
    main()
