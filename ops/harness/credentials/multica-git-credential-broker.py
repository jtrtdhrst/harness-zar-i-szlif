#!/usr/bin/env python3
"""Root broker for role-scoped Multica GitHub credentials.

Agents share one Unix account, so a token file readable by that account is
readable by every agent. This broker never writes tokens where the agent
account can read them. It identifies the caller from the process tree: the
task process must be a direct child of the systemd-managed Multica daemon and
carry the daemon-set (unspoofable, MULTICA_* blocklisted) MULTICA_AGENT_ID.
"""
import argparse
import datetime
import json
import logging
import os
import re
import socket
import socketserver
import struct
import subprocess
import sys
from pathlib import Path

ALLOWED_REPOS = {
    "miloszspyrka-code/zar-i-szlif",
    "miloszspyrka-code/harness-zar-i-szlif",
}
EXPECTED_WORKSPACE = "28378cc8-2c3a-4f8e-af1c-63e308407b17"
RUNTIME_UID = 997
RUNTIME_GID = 981
REFRESH = "/usr/local/libexec/multica-zar-github-app-refresh.py"
AGENT_ROLES = {"implementer", "reviewer", "release"}
DEFAULT_ROOT = "/etc/multica-git-credential"
DAEMON_UNIT = "multica-zar-daemon.service"

log = logging.getLogger("multica-git-credential-broker")


def proc_status(pid):
    values = {}
    for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key] = value.strip()
    return values


def proc_environ(pid):
    env = {}
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return env
    for item in raw.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            env[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return env


def daemon_pid(unit, pidfile=None, allow_any_daemon=False):
    if allow_any_daemon and pidfile is not None:
        pid = int(pidfile.read_text(encoding="utf-8").strip())
    else:
        result = subprocess.run(
            ["systemctl", "show", "-p", "MainPID", "--value", unit],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            raise ValueError("multica daemon MainPID unavailable")
        pid = int(result.stdout.strip())
    if pid <= 1:
        raise ValueError("multica daemon MainPID invalid")
    status = proc_status(pid)
    if int(status.get("Uid", "-1").split()[0]) != RUNTIME_UID:
        raise ValueError("multica daemon uid mismatch")
    cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    if "multica" not in cmdline or "daemon" not in cmdline:
        raise ValueError("multica daemon cmdline mismatch")
    return pid


def task_agent(pid, unit, pidfile=None, allow_any_daemon=False):
    """Return (agent_id, task_id) only for a real daemon-spawned task child."""
    parent = daemon_pid(unit, pidfile, allow_any_daemon)
    current = pid
    for _ in range(64):
        ppid = int(proc_status(current).get("PPid", "0"))
        if ppid == parent:
            env = proc_environ(current)
            agent = env.get("MULTICA_AGENT_ID", "").strip()
            task = env.get("MULTICA_TASK_ID", "").strip()
            workspace = env.get("MULTICA_WORKSPACE_ID", "").strip()
            if not agent or not task:
                return None
            if workspace != EXPECTED_WORKSPACE:
                return None
            return agent, task
        if ppid <= 1:
            return None
        current = ppid
    return None


def _cache_proc_executable(pid, kind):
    """Use /proc executable identity; argv[0] is caller-controlled."""
    approved = {
        "python": {"/usr/bin/python3", "/usr/bin/python3.11",
                   "/usr/bin/python3.12", "/usr/bin/python3.13",
                   "/usr/bin/python3.14", "/usr/bin/python3.15"},
        "git": {"/usr/bin/git", "/usr/lib/git-core/git"},
        "remote": {"/usr/lib/git-core/git-remote-https",
                   "/usr/lib/git-core/git-remote-http"},
        "shell": {"/bin/sh", "/bin/dash", "/usr/bin/dash"},
    }
    try:
        actual = os.path.realpath(os.readlink(f"/proc/{pid}/exe"))
        return actual in {os.path.realpath(path) for path in approved[kind]}
    except (OSError, KeyError):
        return False


def _trusted_cache_git_args(argv):
    """Find an actual Git subcommand, not an arbitrary argument containing fetch."""
    if not argv or Path(argv[0]).name != "git":
        return False
    args = argv[1:]
    index = 0
    # Restrict daemon-cache Git to the simple documented -C PATH form.
    # In particular, never allow arbitrary -c credential-helper overrides.
    while index < len(args) and args[index] == "-C":
        if index + 1 >= len(args) or not args[index + 1].startswith("/"):
            return False
        index += 2
    return index < len(args) and args[index] in {"fetch", "clone", "ls-remote"}


def is_authorized_daemon_cache_fetch(pid, unit, pidfile=None, allow_any_daemon=False):
    """Accept only helper -> HTTPS transport -> daemon Git read-only ancestry.

    Fail closed for shells, argument stuffing, reordered ancestry, foreign
    executables and arbitrary daemon descendants.
    """
    daemon = daemon_pid(unit, pidfile, allow_any_daemon)
    chain = []
    current = pid
    for _ in range(4):
        try:
            status = proc_status(current)
            parent = int(status.get("PPid", "0"))
            uid = int(status.get("Uid", "-1").split()[0])
            argv = [part.decode("utf-8", "replace") for part in
                    Path(f"/proc/{current}/cmdline").read_bytes().split(b"\0") if part]
        except (ValueError, OSError, IndexError):
            return False
        if uid != RUNTIME_UID or not argv:
            return False
        chain.append((current, parent, argv))
        if parent == daemon:
            break
        if parent <= 1:
            return False
        current = parent

    # Git executes credential helpers through "sh -c"; this exact, trusted
    # intermediary is present in the real process tree. Do not accept a
    # generic shell, arbitrary command, or an extra process ancestor.
    helper = "/usr/local/libexec/multica-zar-git-credential"
    if len(chain) == 3 and chain[2][1] == daemon:
        helper_pid, helper_parent, helper_argv = chain[0]
        remote_pid, remote_parent, remote_argv = chain[1]
        git_pid, _, git_argv = chain[2]
        if helper_parent != remote_pid or remote_parent != git_pid:
            return False
    elif len(chain) == 4 and chain[3][1] == daemon:
        helper_pid, helper_parent, helper_argv = chain[0]
        shell_pid, shell_parent, shell_argv = chain[1]
        remote_pid, remote_parent, remote_argv = chain[2]
        git_pid, _, git_argv = chain[3]
        exact = helper + " get"
        if (helper_parent != shell_pid or shell_parent != remote_pid or
            remote_parent != git_pid or
            shell_argv != ["/bin/sh", "-c", exact, exact] or
            not _cache_proc_executable(shell_pid, "shell")):
            return False
    else:
        return False
    helper = "/usr/local/libexec/multica-zar-git-credential"
    if (len(helper_argv) != 3 or
        Path(helper_argv[0]).name not in {"python3", "python3.11",
             "python3.12", "python3.13", "python3.14", "python3.15"} or
        helper_argv[1:] != [helper, "get"] or
        not _cache_proc_executable(helper_pid, "python")):
        return False
    if (Path(remote_argv[0]).name not in {"git-remote-http", "git-remote-https"} or
        not _cache_proc_executable(remote_pid, "remote")):
        return False
    if (not _trusted_cache_git_args(git_argv) or
        not _cache_proc_executable(git_pid, "git")):
        return False
    return True


def parse_expiry(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_role_token(tokens_dir, role):
    data = json.loads((tokens_dir / f"{role}.json").read_text(encoding="utf-8"))
    if not isinstance(data.get("token"), str) or not data["token"].startswith("ghs_"):
        raise ValueError("role token malformed")
    if set(data.get("repositories", [])) != ALLOWED_REPOS:
        raise ValueError("role token repository scope mismatch")
    if role == "cache-reader":
        if (data.get("role") != "cache-reader" or
            data.get("permissions") != {"contents": "read", "metadata": "read"}):
            raise ValueError("daemon cache token permissions mismatch")
    if parse_expiry(data["expires_at"]) <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=2):
        raise ValueError("role token stale")
    return data


def refresh_tokens():
    result = subprocess.run(
        [sys.executable, REFRESH],
        capture_output=True,
        text=True,
        timeout=110,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"token refresh failed: {result.stderr.strip()[:160]}")


def token_for_role(tokens_dir, role):
    try:
        return read_role_token(tokens_dir, role)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        refresh_tokens()
        return read_role_token(tokens_dir, role)


class Handler(socketserver.StreamRequestHandler):
    server_version = "multica-git-credential-broker/2"

    def handle(self):
        self.request.settimeout(130)
        try:
            raw = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            pid, uid, _gid = struct.unpack("3i", raw)
        except OSError:
            return
        if uid != RUNTIME_UID:
            self.reply({"ok": False, "error": "caller_not_multica_agent"})
            return
        try:
            line = self.rfile.readline(65536)
            request = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.reply({"ok": False, "error": "invalid_request"})
            return
        try:
            identity = task_agent(pid, self.server.daemon_unit, self.server.pidfile, self.server.allow_any_daemon)
            op = request.get("op")
            if identity is None:
                if op != "credential" or not is_authorized_daemon_cache_fetch(
                    pid, self.server.daemon_unit, self.server.pidfile, self.server.allow_any_daemon
                ):
                    self.reply({"ok": False, "error": "no_active_multica_task"})
                    return
                # Cache sync from the trusted daemon can only read repository
                # contents; never borrow an implementer/release token.
                role = "cache-reader"
                agent_id = "daemon-cache"
            else:
                agent_id, task_id = identity
                roles = json.loads(self.server.roles_file.read_text(encoding="utf-8"))
                role = roles.get(agent_id)
                if role not in AGENT_ROLES:
                    self.reply({"ok": False, "error": "agent_not_mapped"})
                    return
            if op == "credential":
                if request.get("protocol") != "https" or request.get("host") != "github.com":
                    self.reply({"ok": False, "error": "unsupported_transport"})
                    return
                repo = str(request.get("path", "")).removesuffix(".git").strip("/")
                if repo not in ALLOWED_REPOS:
                    self.reply({"ok": False, "error": "repository_not_allowed"})
                    return
                log.info("credential pid=%s agent=%s role=%s repo=%s", pid, agent_id, role, repo)
            elif op == "token":
                log.info("token pid=%s agent=%s role=%s", pid, agent_id, role)
            else:
                self.reply({"ok": False, "error": "unsupported_operation"})
                return
            data = token_for_role(self.server.tokens, role)
            self.reply({
                "ok": True,
                "username": "x-access-token",
                "token": data["token"],
                "role": role,
                "expires_at": data["expires_at"],
            })
        except Exception as error:  # fail closed, never echo token material
            log.warning("denied pid=%s error=%s", pid, str(error)[:160])
            self.reply({"ok": False, "error": "credential_unavailable"})

    def reply(self, payload):
        try:
            self.wfile.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
            self.wfile.flush()
        except OSError:
            pass


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/run/multica-git-credential/credential.sock")
    parser.add_argument("--daemon-unit", default=DAEMON_UNIT)
    parser.add_argument("--pidfile", default=None, help="test only")
    parser.add_argument("--roles", default=f"{DEFAULT_ROOT}/agent-roles.json")
    parser.add_argument("--tokens", default=f"{DEFAULT_ROOT}/roles")
    parser.add_argument("--allow-any-daemon", action="store_true", help="test only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    socket_path = Path(args.socket)
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if socket_path.exists():
        socket_path.unlink()
    server = Server(str(socket_path), Handler)
    os.chmod(socket_path, 0o660)
    os.chown(socket_path, 0, RUNTIME_GID)
    server.daemon_unit = args.daemon_unit
    server.pidfile = Path(args.pidfile) if args.pidfile else None
    server.roles_file = Path(args.roles)
    server.tokens = Path(args.tokens)
    server.allow_any_daemon = args.allow_any_daemon
    log.info("broker socket=%s unit=%s roles=%s", socket_path, server.daemon_unit, server.roles_file)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
