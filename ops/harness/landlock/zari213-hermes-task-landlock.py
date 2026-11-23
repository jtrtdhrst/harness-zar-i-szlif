#!/usr/bin/python3
"""Root-owned native Multica Hermes launcher with Linux Landlock per-task filesystem scope.

The daemon remains the sole writer of the shared Git bare cache. The child
receives no access to .repos or another task's workspace. Landlock restrictions
are inherited by exec and all descendants, including CLI subprocesses.
"""
import ctypes
import os
from pathlib import Path
import re
import stat
import sys

TARGET = "/opt/hermes/.venv/bin/hermes"
ROOT = Path("/srv/multica-zar/workspaces")
UID_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
# Root-owned, independently reviewed role/provider authority. Do not derive
# this grant from task-writable profile YAML: that would let a task select the
# more privileged OpenAI OAuth credential merely by changing its model field.
# All workspace agents are authorized for the existing Hermes OpenCode provider.
# No agent task may acquire shared Codex OAuth credentials, even as fallback.
# This is a trusted, static allowlist; do NOT derive it from a task-writable file.
CODEX_ROLES = frozenset()
OPENCODE_ROLES = frozenset({"ceo", "cho", "cmo", "coo", "cpo", "cto",
    "designer", "email-creative", "engineer", "harness-engineer",
    "lifecycle-ops", "mascot-designer", "mcp-engineer", "ui-qa"})

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

EXECUTE = 1
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
REMOVE_DIR = 1 << 4
REMOVE_FILE = 1 << 5
MAKE_CHAR = 1 << 6
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
MAKE_SOCK = 1 << 9
MAKE_FIFO = 1 << 10
MAKE_BLOCK = 1 << 11
MAKE_SYM = 1 << 12
REFER = 1 << 13
TRUNCATE = 1 << 14
IOCTL_DEV = 1 << 15
ALL = ((1 << 16) - 1)
READ = READ_FILE | READ_DIR | EXECUTE
WRITE = ALL
LIBC = ctypes.CDLL(None, use_errno=True)

class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]

class PathBeneath(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

def checked_syscall(num, *args):
    value = LIBC.syscall(num, *args)
    if value < 0:
        raise OSError(ctypes.get_errno(), "landlock syscall denied")
    return value

def grant(ruleset, path, rights, *, require_regular_nofollow=False):
    path = Path(path)
    if not path.exists():
        if require_regular_nofollow:
            raise FileNotFoundError(path)
        return
    flags = os.O_PATH | os.O_CLOEXEC
    if require_regular_nofollow:
        # O_PATH|O_NOFOLLOW pins the symlink itself, never its secret target.
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags)
    try:
        if require_regular_nofollow and not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("refusing non-regular/symlinked Git configuration")
        attr = PathBeneath(rights, fd)
        checked_syscall(445, ruleset, 1, ctypes.byref(attr), 0)
    finally:
        os.close(fd)

def private_role_auth_file(shared_home: Path, role: str, uid: int) -> Path:
    """Require a private role credential file; never follow common OAuth links.

    This validates filesystem isolation, not whether upstream credentials have
    distinct token identities. An independently provisioned role credential is
    mandatory before enabling this stricter policy on the production daemon.
    """
    if role not in CODEX_ROLES:
        raise ValueError("role is not authorized for Codex credentials")
    directory = shared_home / "profiles" / role
    entry = directory / "auth.json"
    d = directory.lstat()  # reject role path symlinks
    if (not stat.S_ISDIR(d.st_mode) or d.st_uid != uid or
            stat.S_IMODE(d.st_mode) != 0o700):
        raise ValueError("Codex role credential directory is not private")
    f = entry.lstat()  # NEVER resolve a symlink into shared OAuth state
    if (not stat.S_ISREG(f.st_mode) or f.st_uid != uid or
            stat.S_IMODE(f.st_mode) != 0o600 or f.st_nlink != 1):
        raise ValueError("Codex role credential must be a private regular file")
    root_auth = shared_home / "auth.json"
    try:
        global_stat = root_auth.stat()
    except FileNotFoundError:
        global_stat = None
    if global_stat and (f.st_dev, f.st_ino) == (global_stat.st_dev, global_stat.st_ino):
        raise ValueError("Codex role credential aliases shared OAuth state")
    return entry


def role_model_provider(shared_home: Path, role: str, uid: int) -> str:
    """Read only the trusted role-local provider selector; reject provider drift.

    CTO may temporarily use the pre-approved OpenCode runtime for independent
    review while its Codex OAuth login is unavailable. No other Codex role
    silently inherits this exception.
    """
    if role not in CODEX_ROLES and role not in OPENCODE_ROLES:
        raise ValueError("role has no model credential policy")
    config = shared_home / "profiles" / role / "config.yaml"
    fd = os.open(config, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != uid
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
            raise ValueError("untrusted role model config")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as file:
            lines = file.read(65536).splitlines()
    finally:
        os.close(fd)
    found = []
    inside = False
    blocks = 0
    for line in lines:
        if line.startswith("model:"):
            blocks += 1
            inside = True
        elif inside and line and not line[0].isspace() and not line.startswith("#"):
            inside = False
        elif inside:
            match = re.fullmatch(r"  provider:\s*([a-z0-9-]+)\s*", line)
            if match:
                found.append(match.group(1))
    if blocks != 1 or len(found) != 1:
        raise ValueError("ambiguous role model provider")
    provider = found[0]
    approved = (
        role in OPENCODE_ROLES and provider == "opencode-go"
    )
    if not approved:
        raise ValueError("role model provider not approved")
    return provider


def private_role_env_file(shared_home: Path, role: str, uid: int) -> Path:
    """Validate private role .env metadata, never expose the provider key."""
    path = shared_home / "profiles" / role / ".env"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != uid
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
            raise ValueError("role provider environment is not private")
    finally:
        os.close(fd)
    return path


def verified_hermes_home_profile(task: Path, home: Path, session_root: Path,
                                 agent: str, role: str, uid: int) -> str:
    """Accept only an owned task-private home or the exact persisted role session.

    A task-local Hermes home is produced by Multica for fresh sessions. It
    must not be mistaken for a foreign shared/persistent Hermes profile.
    Never follow a symlink and never broaden the shared-profile READ grant.
    """
    if not UUID.fullmatch(agent) or not UID_NAME.fullmatch(role):
        raise ValueError("invalid task agent/role identity for Hermes home")
    resolved = home.resolve(strict=True)
    if home != resolved:
        raise ValueError("Hermes home is symlinked")
    expected_task_home = task / "hermes-home"
    if home == expected_task_home:
        st = home.lstat()
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != uid
                or stat.S_IMODE(st.st_mode) != 0o700):
            raise ValueError("task-local Hermes home is not private")
        return role
    try:
        rel = home.relative_to(session_root / agent)
    except ValueError:
        raise ValueError("Hermes home outside own task/session") from None
    if (len(rel.parts) != 2 or not UID_NAME.fullmatch(rel.parts[0])
            or not UUID.fullmatch(rel.parts[1])):
        raise ValueError("unverified persisted Hermes session for profile ACL")
    if rel.parts[0] != role:
        raise ValueError("foreign Hermes profile session")
    st = home.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid or stat.S_IMODE(st.st_mode) != 0o700:
        raise ValueError("persisted Hermes home is not private")
    return role


def task_scope():
    if not UUID.fullmatch(os.environ.get("MULTICA_TASK_ID", "")):
        raise ValueError("missing verified task context")
    if not UUID.fullmatch(os.environ.get("MULTICA_WORKSPACE_ID", "")):
        raise ValueError("missing verified workspace context")
    cwd = Path.cwd().resolve(strict=True)
    rel = cwd.relative_to(ROOT)
    if len(rel.parts) < 2 or rel.parts[0].startswith(".") or rel.parts[0].startswith("repowise-"):
        raise ValueError("task cwd outside registered workspace task root")
    task = ROOT / rel.parts[0] / rel.parts[1]
    if not task.is_dir() or task.resolve(strict=True) != task:
        raise ValueError("task root invalid or symlinked")
    # Existing daemon already provides private TMPDIR; only admit inside its
    # own per-task .task_roots index or inside this task's checkout.
    tmpdir = Path(os.environ.get("TMPDIR", "")).resolve(strict=True)
    private = ROOT / ".task_roots"
    is_daemon_tmp = (tmpdir.parent == Path("/tmp") and
                     re.fullmatch(r"multica-task-[a-zA-Z0-9]{6,32}", tmpdir.name) is not None and
                     tmpdir.stat().st_uid == os.getuid() and
                     (tmpdir.stat().st_mode & 0o077) == 0)
    if not (tmpdir.is_relative_to(task) or is_daemon_tmp or (
        tmpdir.is_relative_to(private) and len(tmpdir.relative_to(private).parts) >= 1)):
        raise ValueError("temporary directory outside task scope")
    return task, tmpdir

def restrict(task, tmpdir):
    ruleset = checked_syscall(444, ctypes.byref(Ruleset(ALL)),
                              ctypes.sizeof(Ruleset), 0)
    try:
        # Runtime and system libraries/configuration only; no global workspace,
        # no shared bare mirrors, no other task roots.
        for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc",
                     "/opt/hermes", "/opt/experiments/multica-poc/bin",
                     "/srv/multica-zar/skills",
                     "/srv/multica-zar/.local"):
            grant(ruleset, path, READ)
        # /etc/resolv.conf is a symlink to this systemd-resolved read-only file.
        # Without it, Landlock isolates the resolver's target and every model
        # provider request fails with EAI_AGAIN. No access to other /run paths.
        grant(ruleset, "/run/systemd/resolve/stub-resolv.conf", READ_FILE)
        # Git needs the non-secret credential-helper configuration in the daemon home.
        # Expose just this file as read-only; never the home tree or broker tokens.
        grant(ruleset, "/srv/multica-zar/.gitconfig", READ_FILE, require_regular_nofollow=True)
        # Specific role credential only, not the union of all role keys.
        role = re.sub(r"[^a-z0-9]+", "-", os.environ.get("MULTICA_AGENT_NAME", "").lower()).strip("-")
        if UID_NAME.fullmatch(role):
            grant(ruleset, Path("/srv/multica-zar/.config/hermes") / role, READ)
        # Runtime may read its shared settings; never writable from task.
        # Hermes/psutil enumerates process IDs for gateway liveness. Allow
        # directory listing ONLY, not /proc/<pid>/environ or fd contents.
        grant(ruleset, "/proc", READ_DIR)
        # Persistent conversation & memory stores are derived by the native
        # daemon from (agent, profile, issue). Admit only their exact paths.
        profile_root = Path("/srv/multica-zar/.multica/profiles/zar-prod")
        agent = os.environ.get("MULTICA_AGENT_ID", "")
        if not UUID.fullmatch(agent):
            raise ValueError("invalid agent identity for persisted stores")
        for variable, folder, segments in (
            ("MULTICA_TASK_HERMES_SESSION_STORE", "hermes-sessions", 2),
            ("MULTICA_TASK_HERMES_MEMORY_STORE", "hermes-state", 1),
        ):
            raw = os.environ.get(variable, "")
            if raw:
                allowed_root = profile_root / folder / agent
                target = Path(raw).resolve(strict=True)
                relative = target.relative_to(allowed_root)
                if len(relative.parts) != segments or any(
                    not (UID_NAME.fullmatch(x) or UUID.fullmatch(x)) for x in relative.parts
                ):
                    raise ValueError("persistent Hermes store outside task scope")
                grant(ruleset, target, WRITE)
        # Limit shared Hermes read authority to the invoking role. Granting
        # the whole .hermes tree makes every agent able to read other agents'
        # profiles under the common Unix uid, bypassing repo/task isolation.
        shared_home = Path("/srv/multica-zar/.hermes")
        session_root = Path("/srv/multica-zar/.multica/profiles/zar-prod/hermes-sessions")
        home_for_acl = Path(os.environ.get("HERMES_HOME", ""))
        own_profile = verified_hermes_home_profile(
            task, home_for_acl, session_root, agent, role, os.getuid())
        if not UID_NAME.fullmatch(role) or own_profile != role:
            raise ValueError("agent role and trusted persisted session profile disagree")
        if role not in CODEX_ROLES and role not in OPENCODE_ROLES:
            raise ValueError("no approved model credential policy for this role")
        if own_profile != "default":
            own_shared = shared_home / "profiles" / own_profile
            if not own_shared.is_dir() or own_shared.is_symlink():
                raise ValueError("role-scoped Hermes profile missing or linked")
            grant(ruleset, own_shared, READ)
        # Only exact shared bootstrap files needed for profile symlinks;
        # never grant other profiles, global session DBs, logs or backups.
        grant(ruleset, shared_home / "installs", READ)
        # Provider-scoped secrets: never grant global .env or auth.json.
        # Every Codex role requires an independently provisioned local auth file;
        # missing, linked, hardlinked or group-readable credentials fail closed.
        bootstrap_names = ("auth.lock", "install_id", "SOUL.md",
                           ".codex_gpt55_autoraise_notice",
                           "models_dev_cache.json", "provider_models_cache.json",
                           "context_length_cache.yaml")
        for name in bootstrap_names:
            grant(ruleset, shared_home / name, READ_FILE)
        provider = role_model_provider(shared_home, role, os.getuid())
        if provider == "openai-codex":
            grant(ruleset, private_role_auth_file(shared_home, role, os.getuid()),
                  READ_FILE, require_regular_nofollow=True)
        elif provider == "opencode-go":
            grant(ruleset, private_role_env_file(shared_home, role, os.getuid()),
                  READ_FILE, require_regular_nofollow=True)
        # Hermes startup uses an existing per-install flock. Permit only
        # this single lock file to be opened for writing, never shared config
        # or a parent directory, so no other task's data becomes writable.
        locks = list(Path("/srv/multica-zar/.hermes/installs").glob("*/.install.lock"))
        if len(locks) != 1:
            raise ValueError("Hermes installation lock is not unique")
        grant(ruleset, locks[0], READ_FILE | WRITE_FILE | TRUNCATE)
        # Hermes' runtime lease files are ephemeral and version-specific.
        # Permit only the active install environment's lease subdirectory.
        # Hermes retains managed environments after updates. Admit only the
        # most recently installed managed environment, never every .leases path.
        # Ties or missing ownership evidence must fail closed.
        leases = Path("/srv/multica-zar/.hermes/installs").glob("*/environments/*/.leases")
        candidates = []
        for lease in leases:
            marker = lease.parent / ".lease-managed"
            if not lease.is_dir() or lease.is_symlink() or not marker.is_file():
                continue
            if lease.resolve(strict=True) != lease:
                continue
            if lease.stat().st_uid != os.getuid() or marker.stat().st_uid != os.getuid():
                continue
            candidates.append((marker.stat().st_mtime_ns, lease))
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        if not candidates:
            raise ValueError("Hermes managed lease environment unavailable")
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            raise ValueError("Hermes active lease environment ambiguous")
        grant(ruleset, candidates[0][1], WRITE)
        for path in ("/dev/null", "/dev/zero", "/dev/urandom", "/dev/random", "/dev/tty"):
            grant(ruleset, path, READ_FILE | WRITE_FILE)
        # The daemon constructs a resumable Hermes session home for THIS
        # agent, outside the checkout tree. Admit exactly that session root,
        # never global .multica, other agents or another conversation.
        session_home_raw = os.environ.get("HERMES_HOME", "")
        agent_id = os.environ.get("MULTICA_AGENT_ID", "")
        if session_home_raw and UUID.fullmatch(agent_id or ""):
            session_home = Path(session_home_raw).resolve(strict=True)
            sessions = Path("/srv/multica-zar/.multica/profiles/zar-prod/hermes-sessions")
            if not session_home.is_relative_to(task):
                relative = session_home.relative_to(sessions / agent_id)
                if len(relative.parts) != 2 or not all(UID_NAME.fullmatch(x) or UUID.fullmatch(x) for x in relative.parts):
                    raise ValueError("Hermes session home is not a scoped agent session")
                grant(ruleset, session_home, WRITE)
        grant(ruleset, task, WRITE)
        if not tmpdir.is_relative_to(task):
            grant(ruleset, tmpdir, WRITE)
        if LIBC.prctl(38, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "no_new_privs failed")
        checked_syscall(446, ruleset, 0)
    finally:
        os.close(ruleset)

def localize_private_vision_cache(home: Path, shared_profile: Path):
    """Keep Hermes vision temp images inside the authenticated task session.

    The daemon projects cache as a link to a shared role profile. Under Landlock
    that shared profile is READ-only. Remove ONLY that exact expected link and
    create a private cache/vision; never grant shared write or follow unknown links.
    """
    import errno
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    home_fd = os.open(home, flags)
    try:
        try:
            link = os.readlink("cache", dir_fd=home_fd)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOENT):
                raise
            link = None
        if link is not None:
            if link != str(shared_profile / "cache"):
                raise ValueError("unexpected Hermes cache symlink target")
            os.unlink("cache", dir_fd=home_fd)
        try:
            os.mkdir("cache", 0o700, dir_fd=home_fd)
        except FileExistsError:
            pass
        cache_fd = os.open("cache", flags, dir_fd=home_fd)
        try:
            st = os.fstat(cache_fd)
            if st.st_uid != os.getuid() or (st.st_mode & 0o077):
                raise ValueError("unsafe task-local Hermes cache")
            try:
                os.mkdir("vision", 0o700, dir_fd=cache_fd)
            except FileExistsError:
                pass
            vision_fd = os.open("vision", flags, dir_fd=cache_fd)
            try:
                st = os.fstat(vision_fd)
                if st.st_uid != os.getuid() or (st.st_mode & 0o077):
                    raise ValueError("unsafe task-local vision cache")
            finally:
                os.close(vision_fd)
        finally:
            os.close(cache_fd)
    finally:
        os.close(home_fd)


def localize_sqlite_locks(task):
    """Do not let Hermes SQLite lockfiles follow shared-profile symlinks.

    Multica's current overlay excludes state.db and state.db-* from mirroring,
    but inadvertently mirrors state.db.*. Remove only the two proven lock
    symlinks within the current authenticated task's conversation home.
    Never write the shared profile, never follow an unexpected symlink.
    """
    raw = os.environ.get("HERMES_HOME", "")
    if not raw:
        return
    home = Path(raw).resolve(strict=True)
    if home.is_relative_to(task):
        return
    base = Path("/srv/multica-zar/.multica/profiles/zar-prod/hermes-sessions")
    rel = home.relative_to(base)
    agent = os.environ.get("MULTICA_AGENT_ID", "")
    if (len(rel.parts) != 3 or not UUID.fullmatch(agent)
            or rel.parts[0] != agent or not UID_NAME.fullmatch(rel.parts[1])
            or not UUID.fullmatch(rel.parts[2])
            or home.is_symlink() or home.stat().st_uid != os.getuid()):
        raise ValueError("unverified Hermes conversation home for lock localization")
    profile = rel.parts[1]
    shared = Path("/srv/multica-zar/.hermes/profiles") / profile
    for filename in ("state.db.quarantine.lock", "state.db.fts_rebuild.lock"):
        lock = home / filename
        if not lock.is_symlink():
            continue
        target = Path(os.readlink(lock))
        if target != shared / filename:
            raise ValueError("unexpected external Hermes SQLite lock symlink")
        lock.unlink()  # unlink task-owned symlink, NEVER its shared target
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        fd = os.open(str(lock), flags, 0o600)
        os.close(fd)
    localize_private_vision_cache(home, shared)


def main():
    argv = sys.argv[1:]
    if not argv:
        raise ValueError("missing Hermes command")
    # Discovery/version probe is trusted daemon-owned work without a task cwd.
    # Never permit an ACP process outside an authenticated task scope.
    if argv in (["--version"], ["-V"], ["version"]):
        os.execv(TARGET, [TARGET, *argv])
    # This daemon-owned cleanup runs BEFORE a task's ACP subprocess is
    # launched; it is not an agent tool call. An agent already inside Landlock
    # cannot escape its restrictions by executing this trusted command.
    # Strictly allow only the fixed gateway-stop argv that Multica generates.
    is_gateway_stop = (os.environ.get("HERMES_DISABLE_LAZY_INSTALLS") == "1" and
                       argv in (["--profile", "default", "gateway", "stop", "--yes"],
                                ["--profile", "default", "gateway", "stop"]))
    if is_gateway_stop:
        for key in ("MULTICA_TASK_ID", "MULTICA_TOKEN", "MULTICA_AGENT_ID",
                    "MULTICA_WORKSPACE_ID", "MULTICA_TASK_CONFIG_ROOT",
                    "MULTICA_TASK_WORKSPACES_ROOT", "MULTICA_LANDLOCK_REQUIRED"):
            os.environ.pop(key, None)
        os.execv(TARGET, [TARGET, *argv])
    task, tmpdir = task_scope()
    localize_sqlite_locks(task)
    # Never direct ephemeral Python/runtime cache into a shared home.
    cache = tmpdir / "hermes-cache"
    cache.mkdir(mode=0o700, exist_ok=True)
    os.environ["PYTHONPYCACHEPREFIX"] = str(cache / "pycache")
    os.environ["XDG_CACHE_HOME"] = str(cache)
    restrict(task, tmpdir)
    os.execv(TARGET, [TARGET, *argv])

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"multica task Landlock deny: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(126)
