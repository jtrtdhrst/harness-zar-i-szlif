#!/usr/bin/env python3
"""Mint role-scoped Multica GitHub App installation tokens via Coolify.

The App private key never leaves the Coolify container. Tokens are written
root-only under roles/ and are served to agents by the credential broker,
never by a file the agent account can read.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

APP_ID = 5398752
INSTALLATION_ID = 173456397
REPOS = ("jtrtdhrst/harness-zar-i-szlif", "jtrtdhrst/zar-i-szlif")
REPO_NAMES = ("harness-zar-i-szlif", "zar-i-szlif")
DEST = Path("/etc/multica-git-credential/roles")
ROLE_PERMISSIONS = {
    "implementer": {"contents": "write", "pull_requests": "write", "checks": "read", "metadata": "read"},
    "reviewer": {"contents": "read", "pull_requests": "write", "checks": "read", "metadata": "read"},
    "release": {"contents": "write", "pull_requests": "write", "checks": "read", "metadata": "read"},
    "runner": {"actions": "write", "administration": "write", "contents": "read", "metadata": "read"},
    "harness-reader": {"contents": "read", "metadata": "read"},
    "cache-reader": {"contents": "read", "metadata": "read"},
    "github-ops-reader": {"actions": "read", "administration": "read", "contents": "read", "deployments": "read", "metadata": "read"},
    # Dedicated, non-brokered credential for a digest-pinned GitHub Ops MCP image.
    "github-ops-reader-harness": {"contents": "read", "metadata": "read"},
    "github-ops-reader-image": {"actions": "read", "administration": "read", "contents": "read", "deployments": "read", "metadata": "read"},
    "github-ops-writer": {"actions": "write", "contents": "write", "pull_requests": "write", "metadata": "read"},
}
ROLE_REPO_NAMES = {"harness-reader": ("harness-zar-i-szlif",), "github-ops-reader-harness": ("harness-zar-i-szlif",)}
ROLE_REPOS = {"harness-reader": (REPOS[0],), "github-ops-reader-harness": (REPOS[0],)}
# Scoped agent grants are consumed by the broker; runner is a separate privileged role.
# Only project-specific implementer/release roles may update repository workflows.
for _base in ("implementer", "reviewer", "release"):
    _scoped_permissions = dict(ROLE_PERMISSIONS[_base])
    if _base in {"implementer", "release"}:
        _scoped_permissions["workflows"] = "write"
    for _suffix, _repo, _name in (("harness", REPOS[0], REPO_NAMES[0]),
                                  ("product", REPOS[1], REPO_NAMES[1])):
        ROLE_PERMISSIONS[f"{_base}-{_suffix}"] = dict(_scoped_permissions)
        ROLE_REPOS[f"{_base}-{_suffix}"] = (_repo,)
        ROLE_REPO_NAMES[f"{_base}-{_suffix}"] = (_name,)
RUNTIME_GID = 981
# The writer role is not automatically activated by a source deployment.
# Until independent release authorization is present, the root-owned systemd
# environment must explicitly opt in. The reader and existing agent roles
# continue refreshing without requesting new GitHub App write scopes.
WRITER_ROLE = "github-ops-writer"
WRITER_OPT_IN = "GITHUB_OPS_WRITER_MINT_ENABLED"


def selected_roles():
    enabled = os.environ.get(WRITER_OPT_IN, "false")
    if enabled not in ("true", "false"):
        raise RuntimeError("Invalid writer mint gate")
    return [role for role in ROLE_PERMISSIONS if role != WRITER_ROLE or enabled == "true"]


PHP_TEMPLATE = r'''
$a=App\Models\GithubApp::findOrFail(1);
if((int)$a->app_id!==5398752||(int)$a->installation_id!==173456397||!$a->privateKey){throw new \RuntimeException("Wrong GitHub App or missing key");}
$j=generateGithubJwt($a);
$r=Illuminate\Support\Facades\Http::GitSource($a->api_url)->withHeaders([
 "Authorization"=>"Bearer ".$j,
 "Accept"=>"application/vnd.github+json",
 "X-GitHub-Api-Version"=>"2022-11-28"
])->post($a->api_url."/app/installations/173456397/access_tokens",[
 "repositories"=>{repos},
 "permissions"=>{perms}
]);
if($r->status()!==201){throw new \RuntimeException("Scoped installation grant refused: status=".$r->status());}
echo json_encode(["status"=>$r->status(),"app_id"=>(int)$a->app_id,
 "installation_id"=>(int)$a->installation_id,"token"=>$r->json("token"),
 "expires_at"=>$r->json("expires_at"),"permissions"=>$r->json("permissions"),
 "repositories"=>array_map(fn($v)=>data_get($v,"full_name"),$r->json("repositories")??[])
],JSON_UNESCAPED_SLASHES);
'''


def php_list(values):
    return "[" + ",".join(json.dumps(value) for value in values) + "]"


def php_map(values):
    return "[" + ",".join(json.dumps(key) + "=>" + json.dumps(value) for key, value in values.items()) + "]"


def mint(role):
    permissions = ROLE_PERMISSIONS[role]
    names = ROLE_REPO_NAMES.get(role, REPO_NAMES)
    expected_repos = ROLE_REPOS.get(role, REPOS)
    php = PHP_TEMPLATE.replace("{repos}", php_list(names)).replace("{perms}", php_map(permissions))
    result = subprocess.run(
        ["docker", "exec", "coolify", "php", "artisan", "tinker", "--execute=" + php],
        capture_output=True, text=True, timeout=70, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{role}: Coolify internal installation grant failed")
    try:
        grant = json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"{role}: grant returned no valid JSON") from error
    if (grant.get("status") != 201 or grant.get("app_id") != APP_ID
            or grant.get("installation_id") != INSTALLATION_ID):
        raise RuntimeError(f"{role}: installation identity / token grant mismatch")
    if set(grant.get("repositories", [])) != set(expected_repos):
        raise RuntimeError(f"{role}: unexpected repository scope")
    if grant.get("permissions") != permissions:
        raise RuntimeError(f"{role}: unexpected permission scope")
    token = grant.get("token")
    if not isinstance(token, str) or len(token) < 40 or any(c.isspace() for c in token):
        raise RuntimeError(f"{role}: token missing or malformed")
    expires_at = grant.get("expires_at")
    if not isinstance(expires_at, str):
        raise RuntimeError(f"{role}: expiry missing")
    expiry = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if expiry <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10):
        raise RuntimeError(f"{role}: token expiry too short")
    return {
        "token": token,
        "expires_at": expires_at,
        "app_id": APP_ID,
        "installation_id": INSTALLATION_ID,
        "repositories": sorted(expected_repos),
        "permissions": permissions,
        "role": role,
    }


def write_token(role, payload):
    target = DEST / f"{role}.json"
    tempname = None
    try:
        out_fd, tempname = tempfile.mkstemp(prefix=f".{role}-", dir=DEST)
        os.fchown(out_fd, 0, 0)
        os.fchmod(out_fd, 0o600)
        with os.fdopen(out_fd, "w") as out:
            json.dump(payload, out, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tempname, target)
        tempname = None
    finally:
        if tempname is not None:
            os.unlink(tempname)


def retire_writer_grant():
    """Fail closed on writer deactivation or a failed grant; never follow links."""
    import stat
    target = DEST / f"{WRITER_ROLE}.json"
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return False
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
                info.st_gid != 0 or info.st_nlink != 1 or
                stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError("Untrusted writer grant file")
    finally:
        os.close(fd)
    os.unlink(target)
    return True


def refresh_bgh_reader():
    """Renew only the existing BGH read grant and its verified live volume.

    Never mint an agent, runner, release or writer grant in this mode.
    The caller holds the same root-owned refresh lock as the legacy entrypoint.
    """
    import runpy
    here = Path(__file__).resolve().parent
    volume = runpy.run_path(str(here / "github-ops-image-reader-project.py"))
    projector = runpy.run_path(str(here / "github-ops-token-project.py"))
    app_uuid = "t09dqe2eppn2eiqmhzlf8xzp"
    name = app_uuid + "-bgh-github-app-reader"
    directory = volume["validated_volume"](app_uuid, name)
    projector["check_dir"](directory, projector["NODE_GID"], 0o750)
    role = "github-ops-reader"
    grant = mint(role)
    if (grant["role"] != role or grant["permissions"] != projector["PERMISSIONS"]
            or set(grant["repositories"]) != projector["REPOS"]):
        raise RuntimeError("Reader grant scope mismatch")
    write_token(role, grant)
    projector["project"](projector["SOURCE"], projector["TARGET"], role,
                         projector["PERMISSIONS"])
    volume["project"](grant, directory)
    print(json.dumps({"reader_refreshed": True, "role": role,
                      "expires_at": grant["expires_at"]}))
    return 0


def _refresh_core(*, reader_only=False):
    if os.geteuid() != 0:
        raise RuntimeError("Root service account required")
    # Reject any untrusted directory or lock file before touching credentials.
    import stat
    def checked_directory(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or
                info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700):
                raise RuntimeError("Untrusted root-only token directory")
        finally:
            os.close(fd)

    checked_directory(DEST.parent)
    DEST.mkdir(mode=0o700, exist_ok=True)
    checked_directory(DEST)
    fd = os.open(DEST / ".refresh.lock",
                 os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
        info.st_gid != 0 or info.st_nlink != 1 or
        stat.S_IMODE(info.st_mode) != 0o600):
        os.close(fd)
        raise RuntimeError("Untrusted refresh lock file")
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if reader_only:
            return refresh_bgh_reader()
        # The same refresh lock MUST cover mint, remote revoke, all local
        # projections, image-reader projection and every failure cleanup.
        # The independent writer projector obtains this same lock.
        try:
            roles = selected_roles()
            summary = {}
            writer_blocked = False
            if WRITER_ROLE not in roles:
                # A failed revocation blocks all subsequent mints even if
                # the local copies were removed. Do not silently continue.
                cleanup_failed_writer()
            for role in roles:
                try:
                    payload = mint(role)
                except Exception:
                    if role != WRITER_ROLE:
                        raise
                    # Optional writer refusal must not starve reader mints,
                    # but provider revocation failures remain hard failures.
                    cleanup_failed_writer()
                    writer_blocked = True
                    continue
                write_token(role, payload)
                summary[role] = payload["expires_at"]
            # Optional image-only application rotation shares this root lock.
            app_uuid = os.environ.get("GITHUB_OPS_IMAGE_APP_UUID", "")
            volume = os.environ.get("GITHUB_OPS_IMAGE_READER_VOLUME", "")
            if bool(app_uuid) != bool(volume):
                raise RuntimeError("Incomplete image-reader rotation configuration")
            if app_uuid:
                projection = subprocess.run(
                    [sys.executable, "/usr/local/libexec/github-ops-image-reader-project.py"],
                    capture_output=True, text=True, timeout=25, check=False)
                if projection.returncode != 0:
                    raise RuntimeError("Dedicated GitHub Ops image-reader projection failed")
            print(json.dumps({"refreshed": True, "roles": sorted(summary),
                              "writer_mint_enabled": WRITER_ROLE in roles,
                              "writer_ready": WRITER_ROLE in summary,
                              "writer_grant_blocked": writer_blocked,
                              "expiry": min(summary.values())}))
            return 0
        except Exception:
            cleanup_failed_writer()
            raise


def revoke_existing_writer_at_github():
    """Revoke the current installation writer grant before removing its files.

    Use an O_NOFOLLOW root-only reader; never send the token to logs or argv.
    """
    import stat
    import urllib.request
    path = DEST / f"{WRITER_ROLE}.json"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return False
    with os.fdopen(fd, "r", encoding="utf-8") as reader:
        st = os.fstat(reader.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600):
            raise RuntimeError("Untrusted writer grant for provider revocation")
        grant = json.load(reader)
    if (grant.get("role") != WRITER_ROLE or grant.get("app_id") != APP_ID
            or grant.get("installation_id") != INSTALLATION_ID
            or set(grant.get("repositories", [])) != set(REPOS)
            or grant.get("permissions") != ROLE_PERMISSIONS[WRITER_ROLE]):
        raise RuntimeError("Writer grant scope mismatch for provider revocation")
    token = grant.get("token")
    if not isinstance(token, str) or len(token) < 40 or any(ch.isspace() for ch in token):
        raise RuntimeError("Invalid writer grant token for provider revocation")
    request = urllib.request.Request(
        "https://api.github.com/installation/token",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "zari-github-ops-fail-closed"},
        method="DELETE",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 204:
            raise RuntimeError("GitHub writer revocation unconfirmed")
    return True


def cleanup_failed_writer():
    """On ANY full refresh error, retire the root role and both live copies.

    Each location is attempted even if provider revocation or another location fails.
    Never follow symlinks or suppress a failed cleanup as a successful refresh.
    """
    import runpy
    errors = []
    try:
        revoke_existing_writer_at_github()
    except Exception:
        errors.append("github")
    try:
        retire_writer_grant()
    except Exception:
        errors.append("role")
    try:
        projector = runpy.run_path(str(Path(__file__).resolve().parent /
                                       "github-ops-token-project.py"))
        for key in ("WRITER_TARGET", "WRITER_RUNTIME"):
            try:
                projector["retire_writer_target"](projector[key])
            except Exception:
                errors.append(key)
    except Exception:
        errors.append("projector")
    if errors:
        raise RuntimeError("Writer cleanup incomplete after failed refresh")


def main(*, reader_only=False):
    # The core owns the entire lifecycle lock, including error cleanup.
    # Never clean up after it releases that lock.
    return _refresh_core(reader_only=reader_only)


def run_cli(args):
    if args not in ([], ["--github-ops-reader-only"]):
        raise RuntimeError("Unknown refresh mode")
    return main(reader_only=bool(args))


if __name__ == "__main__":
    try:
        sys.exit(run_cli(sys.argv[1:]))
    except Exception as error:
        print(json.dumps({"refreshed": False, "error": str(error)[:160]}), file=sys.stderr)
        sys.exit(1)

