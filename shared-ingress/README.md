# shared-ingress

Production project for shared Cloudflare ingress.

Coolify services:

- `opencode` — runtime agent, port 4096, image `local/opencode-standalone:2.0.32-custom`;
- `oauth-callback-proxy` — socat 19876 → `opencode:19877`;
- `oauth-loopback-bridge` — shared network/PID with `opencode`.

Host bind paths (runtime data, never committed):

- `/home/opencode/projects` → `/home/opencode/projects`
- `/home/opencode/server/config` → `/root/.config/opencode`
- `/home/opencode/server/data` → `/root/.local/share/opencode`
- `/home/opencode/server/cache` → `/root/.cache/opencode`
- `/home/opencode/server/recovery-secrets/*` → `/root/...`
- `/run/user/1001/docker.sock` → `/var/run/docker.sock`

No database or application data belongs to this project. Platform secrets are
mounted read-only from the host; they are not stored in this repository.
