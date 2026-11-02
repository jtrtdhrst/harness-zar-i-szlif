# ComfyUI and its MCP — canonical source of truth
**Current deployment (2026-11-02):** All ComfyUI MCP implementation changes are authored under `comfyui-mcp/` in this repo, built with `comfyui-mcp/Dockerfile` and deployed to the existing Coolify service (`kkhfw0napmeaqewgdirwhc1h`, app `y1ugra7qn0s7sygccgfbwrpe`) as `local/comfyui-mcp:0.52.206-chatfiles6`. `comfy-mcp/` is metadata for the Coolify project, **not** a separate source tree. Do not add patched ComfyUI MCP code there.

- Upload implementation: `chatgpt-file-tool.js`, registered by `patches/patch-chatgpt-upload.mjs`, built **after** the retained validator/base64/color patch chain. Tool `upload_chatgpt_image` declares `_meta["openai/fileParams"]=["file"]` so ChatGPT attachments can be passed through MCP after connecting the client.
- Exact image-byte preservation: downloads original HTTPS file (not ChatGPT preview), blocks private DNS/SSRF, enforces 30 MiB limit and image signatures, SHA-256, optional expected SHA-256/bytes, checks server-stored `/view` bytes and `LoadImage` selection. Returns `byte_identical:true` and hashes only after readback.
- Backward-compatible `upload_image(data_base64,filename)` remains usable for direct raw bytes. A PNG RGBA 1254×1254 passed a byte-perfect roundtrip on the canonical built canary.
- Build on Ubuntu from the actual `comfyui-mcp/` folder with `docker build --pull=false -f Dockerfile -t local/comfyui-mcp:0.52.206-chatfiles6 .`; production Coolify application image is set to that tag and deployed. Never build the release from the `comfy-mcp/` project metadata directory.
- Validated after production redeploy: `tools/list` 42 tools; `upload_chatgpt_image` with original-public PNG → `byte_identical:true`, same SHA-256 from ComfyUI storage, `LoadImage` selectable. A forged/wrong SHA fails; invalid/expired JWT denied on OAuth bridge fixture.
- Cloudflare Access auth bridge source: `oauth-bridge.mjs` and `oauth-bridge.compose.yml`. Secret-bearing `.env` stays on the server and is excluded from Git. Internal origin MCP token is NOT the ChatGPT OAuth token. Keep upstream bearer auth active.
- User-facing endpoint: `https://mcp-comfy.kompaszbiorek.pl/mcp`. Its OAuth connection needs a one-time ChatGPT-side login/reconnect to the correct Access application. `UNAUTHORIZED` in a pre-existing connector is not proof of a failed server-side build.
- Production image is built from GitHub canonical source and not a hotpatch to app/Core. The legacy notes below describe the earlier pre-Coolify state and should not override this current deployment block.

---


Production: ComfyUI 0.42.1 (CPU-only) + `comfyui-mcp` 0.52.206, plain Docker on host
(`coolify` network), Caddy reverse-proxy, Cloudflare Worker edge. This folder is
the durable deployable unit (mirrors `/opt/comfy` on the host).

- `Dockerfile.comfyui` — python:3.12-slim, torch CPU, ComfyUI v0.42.1, `--cpu`.
- `Dockerfile` — canonical Coolify MCP-only image: node:22, `comfyui-mcp@0.52.206`, applies the pinned `patches/patch-*.mjs` chain at build. `Dockerfile.mcp` is a compatible legacy copy.
- `compose.yml` — local `comfyui` + `comfy-mcp` on external `coolify` network, with relative build contexts; sets
  `COMFYUI_URL=http://comfyui:8188` (fixes Prompt Director 127.0.0.1 bug).
- `patch-v1.mjs` — durable production patches (idempotent, applied at build + live):
  `upload_image data_base64` (remote clients, SHA-256, magic-byte check, 30MB cap),
  `train_doctor ready_for_training/diagnostic_completed` (no false success).
- `patch-color.mjs` — `color-analysis`: uniform fills report `FLAT, not washed out`
  (`washedOut:false`, measurements preserved).
- Public: UI `https://comfy.kompaszbiorek.pl/` (Caddy → `comfyui:8188`),
  MCP `https://mcp-comfy.kompaszbiorek.pl/mcp` (Worker `comfyui-mcp` → origin
  `https://comfy-engine.zariszlif.pl/mcp` → Caddy → `comfy-mcp:9100`).
  UI address unchanged; MCP URL unchanged (Worker takes over the same hostname).
- Volumes (persist across restart/recreate): `comfy-models`, `comfy-input`,
  `comfy-output`, `comfy-user`, `comfy-custom`. No models installed (CPU-only;
  local diffusion generation NOT_CONFIGURED; hosted ArkFal nodes via contract only).
- Manager/panel NOT installed (intentional): MCP already returns honest
  `FEATURE_UNAVAILABLE` for Manager snapshots and Apps (404 panel predates Apps);
  installing heavy deps on 93% disk risks production. Classified as justified
  unsupported (PA-24/26/27), not a defect blocking the primary workflow.
- Auth: origin currently OPEN (`--allow-unauthenticated-non-loopback`, owner decision
  2026-10-26). Worker supports `MCP_AUTH_TOKEN` (client→Worker) + `UPSTREAM_TOKEN`
  (Worker→origin); to lock down: set `COMFYUI_MCP_HTTP_TOKEN` on `comfy-mcp`
  (compose env) + same value as Worker `UPSTREAM_TOKEN` + client `MCP_AUTH_TOKEN`,
  then redeploy both. Secrets never enter the repo (Cloudflare secrets + host env).
- Rollback: host backups `/opt/comfy/compose.yml.bak-*`, `/data/caddy/Caddyfile.bak-*`,
  images `local/comfyui-cpu:0.42.1`, `local/comfyui-mcp:0.52.206`; restore compose/Caddy
  + `docker compose up -d` + DNS revert (Worker custom domain → DNS-only A).
- Codex-only (owner decision 2026-10-26): pipelines use ONLY Codex custom nodes
  (`ArkCodexLLM` model `gpt-6-luna` -> `ArkCodexImageGen` -> `SaveImage`).
  No ComfyUI.org / fal nodes. Auth resolves `CODEX_HOME` -> `~/.codex`;
  compose pins `CODEX_HOME=/app/user/.codex` (persistent volume; the
  container-layer `/root/.codex` copy is identical, SHA-verified, but lost on
  rebuild). Verified live: login ok, plan plus, token fresh (236h left),
  end-to-end run 47.30s -> 1254x1254 PNG via the same MCP URL.
- Verify: `get_system_stats(action:health)`, model-free `LoadImage→ImageScale→SaveImage`
  enqueue→history→`get_image(action:get)` SHA-256 match → `stage` → second pass;
  `upload_image data_base64` round-trip; `train_doctor` shows `ready_for_training:false`.
- GPT Image 2.5 (Luna 6 pipeline, 2026-10-26): nodes `ArkCodexLLM` (model
  `gpt-6-luna`) → `OpenAIGPTImageNodeV2` (model `gpt-image-2.5-flare`) → `SaveImage`
  already installed — NO new MCP tools needed (`create_workflow` validate,
  `enqueue_workflow`, `list_api_nodes schema`, `get_history`, `get_image` cover it).
  Reference FLAT-format workflow: `workflows/zar_szlif_luna6_gptimage25_api_20261026.json`
  (`"model": "<key>"` + `"model.<sub>"` flat keys; nested `model` dicts validate but cannot execute; Web-UI `widgets_values` alone fail validation too; the validator now mirrors the server 1:1). `create_workflow validate` = PASS.
  Blocker is ONLY auth: Codex login works (`/app/user/.codex/auth.json`,
  fallback `zar_szlif_luna6_codex_image_fallback_00001_.png` 1254×1254 rendered in
  47.36s); `OpenAIGPTImageNodeV2` is a ComfyUI partner node requiring ComfyUI.org
  login (`auth_token_comfy_org`/`api_key_comfy_org`, 401 otherwise) — owner logs the
  server into comfy.org, then re-run validate + enqueue. No paid run without approval.

- Image loop: mandatory 8-step Codex-only pipeline, parity rules, acceptance evidence: docs/comfy-image-loop.md. Brand contract: mcp/comfyui/brand/ (PNG refs live in input/brand/ on the volume).
- Canvas bridge (`mcp/comfyui/canvas-bridge/`): the MCP can read the OPEN tab — node 1 filename + pixels — via the pack's shipped browser bridge, whose server half was missing (every POST 404'd). `comfy_bridge.py` implements exactly the JS protocol behind `from .mcp_service.comfy_bridge import register_routes` (register/heartbeat+queued read/ack/disconnect/connection-status + agent read/result/sessions). No new MCP tools, no Manager, no panel install: agent enqueues `read`, next tab heartbeat returns the snapshot, node 1 filename → existing `get_image` downloads byte-identical pixels (E2E 13/13 live, `scripts/check-canvas-bridge.py`). Restore: re-copy the two files + `docker restart comfyui` (see `patches/apply.sh`).
