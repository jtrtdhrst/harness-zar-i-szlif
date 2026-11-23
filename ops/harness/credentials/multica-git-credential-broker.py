#!/usr/bin/env python3
"""Root broker for role-scoped Multica GitHub credentials.

Agents share one Unix account, so a token file readable by that account is
readable by every agent. This broker never writes tokens where the agent
account can read them. It identifies a caller only after verifying ancestry under the systemd-managed
Multica daemon, then verifies the nearest task identity against the live
token-bound project scope. The Hermes gateway may be an intermediary.
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
import urllib.request
import stat
from pathlib import Path

HARNESS_REPO = "jtrtdhrst/harness-zar-i-szlif"
PRODUCT_REPO = "jtrtdhrst/zar-i-szlif"
ALLOWED_REPOS = {PRODUCT_REPO, HARNESS_REPO}
PROJECT_REPOS = {"harness": HARNESS_REPO, "product": PRODUCT_REPO}
EXPECTED_WORKSPACE = "28378cc8-2c3a-4f8e-af1c-63e308407b17"
RUNTIME_UID = 997
RUNTIME_GID = 981
REFRESH = "/usr/local/libexec/multica-zar-github-app-refresh.py"
# No runner grants: administration/actions write is not a credential-broker role.
AGENT_ROLES = {"implementer", "reviewer", "release"}
ROLE_SCOPED_REPOS = {}
for _base in ("implementer", "reviewer", "release"):
    for _suffix, _repo in (("harness", HARNESS_REPO), ("product", PRODUCT_REPO)):
        _role = f"{_base}-{_suffix}"
        AGENT_ROLES.add(_role)
        ROLE_SCOPED_REPOS[_role] = {_repo}
ROLE_PERMISSIONS = {
    "implementer": {"contents": "write", "pull_requests": "write", "checks": "read", "metadata": "read"},
    "reviewer": {"contents": "read", "pull_requests": "write", "checks": "read", "metadata": "read"},
    "release": {"contents": "write", "pull_requests": "write", "checks": "read", "metadata": "read"},
    "cache-reader": {"contents": "read", "metadata": "read"},
}
# Keep this grant narrower than the base role: reviewers and generic roles cannot edit CI.
WORKFLOWS_WRITE_ROLES = {
    "implementer-harness", "implementer-product",
    "release-harness", "release-product",
}
DEFAULT_ROOT = "/etc/multica-git-credential"
DAEMON_UNIT = "multica-zar-daemon.service"
DAEMON_PORT_FILE = Path("/srv/multica-zar/.multica/profiles/zar-prod/daemon.port")

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
    """Find a token-bound task in a VERIFIED daemon-descendant process tree.

    Hermes may spawn a persistent gateway directly beneath the daemon and
    launch the actual task shell several levels below it. Never assume the
    daemon's immediate child has task-scoped environment variables.
    """
    daemon = daemon_pid(unit, pidfile, allow_any_daemon)
    current = pid
    lineage = []
    for _ in range(64):
        if current == daemon:
            break
        ppid = int(proc_status(current).get("PPid", "0"))
        if ppid <= 1 or ppid == current:
            return None
        lineage.append(current)
        current = ppid
    else:
        return None
    if current != daemon:
        return None

    # Only after proving daemon ancestry may we inspect task identity. Select
    # the NEAREST candidate to the caller; never fall back from a malformed
    # or mismatched candidate to a more privileged ancestor.
    keys = ("MULTICA_AGENT_ID", "MULTICA_TASK_ID",
            "MULTICA_TOKEN", "MULTICA_WORKSPACE_ID")
    for ancestor in lineage:
        env = proc_environ(ancestor)
        values = [env.get(key, "").strip() for key in keys]
        if not any(values):
            continue
        agent, task, token, workspace = values
        if not (agent and task and token and workspace == EXPECTED_WORKSPACE):
            return None
        # Handler independently validates token, task, agent, workspace and
        # repo scope against the daemon's live /repo/scope endpoint.
        return agent, task, token
    return None


def repo_slug(value):
    """Normalize the GitHub repository identities used by Git and the daemon."""
    value = str(value or "").strip()
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/"):]
    elif value.startswith("git@github.com:"):
        value = value[len("git@github.com:"):]
    return value.removesuffix(".git").strip("/")


class _DenyScopeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a task bearer to an alternate endpoint.
        return None


def _trusted_daemon_port():
    """Read a pinned runtime-owned file without following symlinks or races."""
    fd = os.open(DAEMON_PORT_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != RUNTIME_UID or
                st.st_gid != RUNTIME_GID or stat.S_IMODE(st.st_mode) != 0o600 or
                st.st_nlink != 1):
            raise ValueError("daemon port file identity mismatch")
        raw = os.read(fd, 1024)
        port = int(json.loads(raw)["port"])
        if not 1 <= port <= 65535:
            raise ValueError("invalid daemon port")
        return port
    finally:
        os.close(fd)


def task_repo_scope(token):
    """Resolve task project from pinned local daemon without proxy/redirect."""
    try:
        port = _trusted_daemon_port()
        url = f"http://127.0.0.1:{port}/repo/scope"
        request = urllib.request.Request(url,
            headers={"Authorization": f"Bearer {token}"})
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _DenyScopeRedirect())
        with opener.open(request, timeout=3) as response:
            if response.geturl() != url or response.status != 200:
                return None
            data = json.loads(response.read(65536))
        if not isinstance(data, dict):
            return None
        if data.get("workspace_id") != EXPECTED_WORKSPACE:
            return None
        if not isinstance(data.get("task_id"), str) or not isinstance(data.get("repo_urls"), list):
            return None
        if not data.get("project_id"):
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def scoped_role(base_role, scope, requested_repo=None):
    """Pick a repository-scoped token role; never widen beyond the task claim."""
    allowed = {repo_slug(url) for url in scope.get("repo_urls", []) if repo_slug(url)}
    if not allowed or not allowed.issubset(ALLOWED_REPOS):
        raise ValueError("task repository scope is empty or outside the allowlist")
    if requested_repo is not None:
        requested_repo = repo_slug(requested_repo)
        if requested_repo not in allowed:
            raise ValueError("repository outside task scope")
    # Every authenticated task has a project ID. Never fall back to a
    # workspace-wide token when a project claim unexpectedly contains both
    # repositories: doing so would bypass per-project Git credential isolation.
    if len(allowed) != 1:
        raise ValueError("project task must authorize exactly one repository")
    repo = next(iter(allowed))
    for suffix, slug in PROJECT_REPOS.items():
        if slug == repo:
            return f"{base_role}-{suffix}"
    raise ValueError("project repository has no scoped credential role")


def role_base(role):
    for suffix in PROJECT_REPOS:
        if role.endswith(f"-{suffix}"):
            return role[: -(len(suffix) + 1)]
    return role


def role_permissions(role):
    """Return exact permissions expected for this scoped or base role."""
    permissions = ROLE_PERMISSIONS.get(role_base(role))
    if permissions is None:
        return None
    if role in WORKFLOWS_WRITE_ROLES:
        return {**permissions, "workflows": "write"}
    return permissions


def role_repos(role):
    if role == "harness-reader":
        return {HARNESS_REPO}
    for suffix, repo in PROJECT_REPOS.items():
        if role.endswith(f"-{suffix}"):
            return {repo}
    return ALLOWED_REPOS


def role_repo_allowed(role, repo):
    """Additional static role allowlist; live task scope is checked separately."""
    return repo in ROLE_SCOPED_REPOS.get(role, ALLOWED_REPOS)


def _cache_proc_executable(pid, kind):
    """Use /proc executable identity; argv[0] is caller-controlled."""
    approved = {
        "python": {"/usr/bin/python3", "/usr/bin/python3.11",
                   "/usr/bin/python3.12", "/usr/bin/python3.13",
                   "/usr/bin/python3.14", "/usr/bin/python3.15"},
        "git": {"/usr/bin/git", "/usr/lib/git-core/git"},
        "git-core": {"/usr/lib/git-core/git"},
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
    for _ in range(5):
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
    elif len(chain) in {4, 5} and chain[-1][1] == daemon:
        helper_pid, helper_parent, helper_argv = chain[0]
        shell_pid, shell_parent, shell_argv = chain[1]
        remote_pid, remote_parent, remote_argv = chain[2]
        exact = helper + " get"
        if (helper_parent != shell_pid or shell_parent != remote_pid or
            shell_argv != ["/bin/sh", "-c", exact, exact] or
            not _cache_proc_executable(shell_pid, "shell")):
            return False
        if len(chain) == 4:
            git_pid, _, git_argv = chain[3]
            if remote_parent != git_pid:
                return False
        else:
            # Git may insert its internal `git remote-https` dispatcher between
            # git-remote-http(s) and the original read-only fetch. Accept only
            # that exact executable/argv relationship; arbitrary extra ancestors
            # remain denied.
            dispatcher_pid, dispatcher_parent, dispatcher_argv = chain[3]
            git_pid, _, git_argv = chain[4]
            remote_transport = Path(remote_argv[0]).name.removeprefix("git-")
            if (remote_parent != dispatcher_pid or dispatcher_parent != git_pid or
                len(dispatcher_argv) != 4 or
                Path(dispatcher_argv[0]).name != "git" or
                remote_transport not in {"remote-http", "remote-https"} or
                dispatcher_argv[1] != remote_transport or
                dispatcher_argv[2:] != remote_argv[1:] or
                not _cache_proc_executable(dispatcher_pid, "git-core")):
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
    if role not in AGENT_ROLES and role != "cache-reader":
        raise ValueError("role not authorized for broker")
    if set(data.get("repositories", [])) != role_repos(role):
        raise ValueError("role token repository scope mismatch")
    expected_permissions = role_permissions(role)
    if (expected_permissions is not None and
            data.get("permissions") != expected_permissions):
        raise ValueError("role token permissions mismatch")
    if role.endswith(tuple(f"-{suffix}" for suffix in PROJECT_REPOS)):
        if data.get("role") != role:
            raise ValueError("role token permissions mismatch")
    elif role == "cache-reader":
        if (data.get("role") != "cache-reader" or
            data.get("permissions") != {"contents": "read", "metadata": "read"}):
            raise ValueError("daemon cache token permissions mismatch")
    elif data.get("role") != role:
        raise ValueError("role token permissions mismatch")
    if parse_expiry(data["expires_at"]) <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=2):
        raise ValueError("role token stale")
    return data


def refresh_tokens():
    result = subprocess.run(
        [sys.executable, REFRESH],
        capture_output=True,
        text=True,
        timeout=180,
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
        self.request.settimeout(200)
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
                scope = None
            else:
                agent_id, task_id, task_token = identity
                roles = json.loads(self.server.roles_file.read_text(encoding="utf-8"))
                role = roles.get(agent_id)
                if role not in AGENT_ROLES:
                    self.reply({"ok": False, "error": "agent_not_mapped"})
                    return
                scope = task_repo_scope(task_token)
                if (scope is None or scope.get("task_id") != task_id or
                        scope.get("agent_id") != agent_id):
                    self.reply({"ok": False, "error": "no_active_multica_task"})
                    return
            if op == "credential":
                if request.get("protocol") != "https" or request.get("host") != "github.com":
                    self.reply({"ok": False, "error": "unsupported_transport"})
                    return
                repo = str(request.get("path", "")).removesuffix(".git").strip("/")
                if not role_repo_allowed(role, repo):
                    self.reply({"ok": False, "error": "repository_not_allowed"})
                    return
                if scope is not None:
                    try:
                        role = scoped_role(role, scope, repo)
                    except ValueError:
                        self.reply({"ok": False, "error": "repository_not_allowed"})
                        return
                log.info("credential pid=%s agent=%s role=%s repo=%s", pid, agent_id, role, repo)
            elif op == "token":
                if scope is not None:
                    try:
                        role = scoped_role(role, scope)
                    except ValueError:
                        self.reply({"ok": False, "error": "repository_not_allowed"})
                        return
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
