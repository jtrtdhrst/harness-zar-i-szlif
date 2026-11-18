#!/usr/bin/env python3
"""Mint a repository-scoped GitHub App token using Coolify's existing private key.
Only the short-lived token enters the MCP private volume; no private key is exported.
Never print or log any token or the subprocess stdout/stderr.
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
APP_DB_ID = 1
REPOS = ("miloszspyrka-code/harness-zar-i-szlif", "miloszspyrka-code/zar-i-szlif")
DEST = Path("/var/lib/docker/volumes/fs9rik9axzl1ubbimekvqs03-paperclip-mcp-state/_data/github-auth-bin/installation-token.json")
REQUIRED_PERMISSIONS = {"contents": "write", "pull_requests": "write", "metadata": "read", "checks": "read"}
RUNTIME_GID = 1000
CORE_DEST = Path("/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/.github-app-installation-token.json")

# The original Coolify private key NEVER leaves the Coolify container.
# Only the installation's short-lived GitHub token is transferred via the
# docker-exec stdout pipe into this script's protected memory.
PHP = r'''
$a=App\Models\GithubApp::findOrFail(1);
if((int)$a->app_id!==5398752||(int)$a->installation_id!==173456397||!$a->privateKey){throw new \RuntimeException("Wrong GitHub App or missing key");}
$j=generateGithubJwt($a);
$r=Illuminate\Support\Facades\Http::GitSource($a->api_url)->withHeaders([
 "Authorization"=>"Bearer ".$j,
 "Accept"=>"application/vnd.github+json",
 "X-GitHub-Api-Version"=>"2022-11-28"
])->post($a->api_url."/app/installations/".$a->installation_id."/access_tokens",[
 "repositories"=>["zar-i-szlif","harness-zar-i-szlif"],
 "permissions"=>["contents"=>"write","pull_requests"=>"write","checks"=>"read"]
]);
if($r->status()!==201){throw new \RuntimeException("Scoped installation grant refused: status=".$r->status());}
echo json_encode(["status"=>$r->status(),"app_id"=>(int)$a->app_id,
 "installation_id"=>(int)$a->installation_id,"token"=>$r->json("token"),
 "expires_at"=>$r->json("expires_at"),"permissions"=>$r->json("permissions"),
 "repositories"=>array_map(fn($v)=>data_get($v,"full_name"),$r->json("repositories")??[])
],JSON_UNESCAPED_SLASHES);
'''

def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("Root service account required")
    if not DEST.parent.is_dir():
        raise RuntimeError("Persistent Paperclip MCP credential directory absent")

    # Lock across simultaneous manual refreshes and timer firings.
    lockpath = DEST.parent / ".installation-refresh.lock"
    fd = os.open(lockpath, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = subprocess.run(
            ["docker", "exec", "coolify", "php", "artisan", "tinker", "--execute=" + PHP],
            capture_output=True, text=True, timeout=70, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Coolify internal installation grant failed")
        try:
            grant = json.loads(result.stdout.strip())
        except (json.JSONDecodeError, ValueError) as error:
            raise RuntimeError("Coolify installation grant returned no valid JSON") from error

        if (grant.get("status") != 201 or grant.get("app_id") != APP_ID
                or grant.get("installation_id") != INSTALLATION_ID):
            raise RuntimeError("App installation identity / token grant mismatch")
        if set(grant.get("repositories", [])) != set(REPOS):
            raise RuntimeError("Refusing token with unexpected repository scope")
        if grant.get("permissions") != REQUIRED_PERMISSIONS:
            raise RuntimeError("Refusing token with unexpected permission scope")
        token = grant.get("token")
        if not isinstance(token, str) or len(token) < 40 or any(c.isspace() for c in token):
            raise RuntimeError("Installation token missing or malformed")
        expires_at = grant.get("expires_at")
        if not isinstance(expires_at, str):
            raise RuntimeError("Installation token expiry missing")
        expiry = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expiry <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10):
            raise RuntimeError("Installation token expiry too short")

        payload = {
            "token": token,
            "expires_at": expires_at,
            "app_id": APP_ID,
            "installation_id": INSTALLATION_ID,
            "repositories": sorted(REPOS),
            "permissions": REQUIRED_PERMISSIONS,
        }
        for target, gid, mode in [(DEST, RUNTIME_GID, 0o440), (CORE_DEST, 0, 0o600)]:
            tempname = None
            try:
                out_fd, tempname = tempfile.mkstemp(prefix=".github-token-", dir=target.parent)
                os.fchown(out_fd, 0, gid)
                os.fchmod(out_fd, mode)
                with os.fdopen(out_fd, "w") as out:
                    json.dump(payload, out, separators=(",", ":"))
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tempname, target)
                tempname = None
                dir_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                if tempname is not None:
                    os.unlink(tempname)

        print(json.dumps({"refreshed": True, "expiry": expires_at, "repository_count": 2,
                          "credential": "short-lived GitHub App installation token"}))
        return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Never dump the exception's subprocess stdout/stderr (could include tokens).
        print(json.dumps({"refreshed": False, "error": str(error)[:160]}), file=sys.stderr)
        sys.exit(1)
