# Paperclip GitHub App installation credentials — production contract

## Ownership and security

- Existing Coolify GitHub App: `coolify-zar-i-szlif`, app id **5398752**, installation id **173456397**.
- Authorized repositories: `miloszspyrka-code/zar-i-szlif` and `miloszspyrka-code/harness-zar-i-szlif` **only**.
- Token grants: repository `contents=write`, `pull_requests=write`, `metadata=read`. GitHub responds HTTP **201** when these permissions are accepted.
- The private GitHub App key stays in Coolify. The host's root-only refresh service invokes Coolify's native `generateGithubJwt` and obtains a short-lived installation token from GitHub using the two-repo/permission allowlist.
- The broker rejects missing or excessive grant scopes and tokens with less than 10 minutes of lifetime, then atomically updates two **short-lived-token** files (never the signing key).
- Paperclip MCP reads the scoped token on *every native Git operation*. When the token is missing, malformed, near expiry, or out of scope it fails **closed**, with **no** PAT fallback.
- No token is embedded in the image, Git history, Docker Compose, static environment variables or systemd units. The broker deliberately suppresses the output of subprocesses carrying the token.
- A GitHub App installation token normally expires after 1 hour; `paperclip-github-app-refresh.timer` refreshes every 20 minutes. Only the host root account can mint a token.
- Core Git uses `credential.useHttpPath=true` and `/paperclip/github-auth-bin/core-git-credential-app`. The helper checks the HTTPS hostname and exact repository path before providing the short-lived token to Git.
- Production gateway: `paperclip-mcp:github-app-rotation-20261103`, built from `Dockerfile.github-app-overlay` on the existing `paperclip-mcp:github-role-policy-20261103` image.

## Persistent state

- MCP token: `/var/lib/docker/volumes/fs9rik9axzl1ubbimekvqs03-paperclip-mcp-state/_data/github-auth-bin/installation-token.json`, mode **0440**, owner root, group 1000. Directory mode 0750. MCP token reader runs as UID/GID 1000.
- Core token: `/var/lib/docker/volumes/phime3w5l50scx9q4tjoelcx_paperclip-home/_data/.github-app-installation-token.json`, mode **0600**, owner root.
- The MCP Compose configuration does not mount `/run/paperclip-github-core-credentials` and does not export `GH_TOKEN` or `GITHUB_TOKEN`. It supplies only `PAPERCLIP_GITHUB_APP_TOKEN_FILE=/paperclip/github-auth-bin/installation-token.json`.
- Core's obsolete `.git-credentials` PAT store was detached from the active volume. No process should rely on it. Do **not** reintroduce its mount.
- `/usr/local/libexec/paperclip-github-app-refresh.py` is mode 0700, installed from `scripts/github-app-refresh.py`. The systemd service/timer definitions are in `deploy/`.

## Validation and safe operations

1. `systemctl is-enabled paperclip-github-app-refresh.timer` — `enabled`.
2. `systemctl is-active paperclip-github-app-refresh.timer` — `active`.
3. `systemctl start paperclip-github-app-refresh.service` — fresh scoped token, no MCP restart.
4. `systemctl show -p Result --value paperclip-github-app-refresh.service` — `success`.
5. Paperclip MCP `paperclipGitAuthStatus` on both authorized repositories: credential type `github-app-installation`, authenticated Git transport, `read/push/create_pr`.
6. `paperclipGitAuthStatus` for any out-of-scope repo: never advertises write permission.
7. `paperclipVerifyAgentTool` for CHO + `paperclipGitPush`: denied. Implementation agents require their authorized run/issue context.
8. `paperclipVerifyLiveMCP`: `LIVE_VERIFIED`, no failures, public initialized tools/list and unauthorized HTTP 401.
9. `git ls-remote` from Core against both authorized private repos works with the configured helper, and Git push canary to temporary branch + remote SHA readback + remote branch deletion works with the App token.
10. After a normal MCP restart, repeat 3-8. There must be **no** token values in logs.

The GitHub App installation token's `permissions.push` flag in a repository's *user-centric* REST response can be `false` even when the token has proven Contents write access. The native GitAuthStatus instead uses the attested scoped installation grant and transport probe. The original wrong `SOURCE_RUNTIME_MISMATCH` compared commits belonging to *different* components; the live verifier now compares staged MCP files against the image itself by SHA-256.

## Rollback and incident response

- Prefer fixing the Coolify GitHub App key/installation or the broker service; don't silently fall back to a PAT. If rotation fails, the last valid token works only until expiry, then authorization stops.
- Existing production Core+MCP source/Compose/bootstrap **config** backups from before migration are root-only on the VPS, but credentials must not be reintroduced without explicit authorization.
- Debug via `systemctl status paperclip-github-app-refresh.service` and the **nonsecret** service journal, and GitHub App permission/installation review. Do not enable verbose subprocess logging that might contain credentials.
- For key rotation, update the existing private key in Coolify only; broker will derive newly signed JWTs on the next run.
- Source changes live in `harness-zar-i-szlif`, not the product repo. Do not modify Paperclip Core source.
