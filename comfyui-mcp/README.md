# ComfyUI and its MCP — canonical source of truth
**Current deployment (2026-11-02):** All ComfyUI MCP implementation changes are authored under `comfyui-mcp/` in this repo, built with `comfyui-mcp/Dockerfile` and deployed to the existing Coolify service (`kkhfw0napmeaqewgdirwhc1h`, app `y1ugra7qn0s7sygccgfbwrpe`) as `local/comfyui-mcp:0.52.206-chatfiles7`. `comfy-mcp/` is metadata for the Coolify project, **not** a separate source tree. Do not add patched ComfyUI MCP code there.

- Upload implementation: `chatgpt-file-tool.js`, registered by `patches/patch-chatgpt-upload.mjs`, built **after** the retained validator/base64/color patch chain. Tool `upload_chatgpt_image` declares `_meta["openai/fileParams"]=["file"]` so ChatGPT attachments can be passed through MCP after connecting the client.
- Exact image-byte preservation: downloads original HTTPS file (not ChatGPT preview), blocks private DNS/SSRF, enforces 30 MiB limit and image signatures, SHA-256, optional expected SHA-256/bytes, checks server-stored `/view` bytes and `LoadImage` selection. Returns `byte_identical:true` and hashes only after readback.
- Backward-compatible `upload_image(data_base64,filename)` remains usable for direct raw bytes. A PNG RGBA 1254×1254 passed a byte-perfect roundtrip on the canonical built canary.
- Build on Ubuntu from the actual `comfyui-mcp/` folder with `docker build --pull=false -f Dockerfile -t local/comfyui-mcp:0.52.206-chatfiles7 .`; production Coolify application image is set to that tag and deployed. Never build the release from the `comfy-mcp/` project metadata directory.
- Validated after production redeploy: `tools/list` 44 tools; `upload_chatgpt_image` with original-public PNG → `byte_identical:true`, same SHA-256 from ComfyUI storage, `LoadImage` selectable. A forged/wrong SHA fails; invalid/expired JWT denied on OAuth bridge fixture.
- Cloudflare Access auth bridge source: `oauth-bridge.mjs` and `oauth-bridge.compose.yml`. Secret-bearing `.env` stays on the server and is excluded from Git. Internal origin MCP token is NOT the ChatGPT OAuth token. Keep upstream bearer auth active.
- User-facing endpoint: `https://mcp-comfy.kompaszbiorek.pl/mcp`. Its OAuth connection needs a one-time ChatGPT-side login/reconnect to the correct Access application. `UNAUTHORIZED` in a pre-existing connector is not proof of a failed server-side build.
- Production image is built from GitHub canonical source and not a hotpatch to app/Core. The legacy notes below describe the earlier pre-Coolify state and should not override this current deployment block.


## Exact generated-image links and reusable references (2026-11-02, production v7)

**These capabilities are native MCP tools registered from `comfyui-mcp/output-image-refs.js`. They do not require constructing URLs manually.**

Workflow:

1. Upload original ChatGPT attachment using `upload_chatgpt_image` (MCP `file` input), or upload base64 bytes with `upload_image`. Both return the ComfyUI `input_filename`/filename for a `LoadImage` node; attachment tool validates byte-level SHA-256.
2. Build/use a ComfyUI API workflow containing `LoadImage` (`inputs.image = uploaded filename`), a generative/edit node or image pass-through, and `SaveImage`. Run via `enqueue_workflow` and obtain `prompt_id`.
3. Call `get_output_image_ref({"prompt_id":"<uuid>"})`. The tool enumerates the **actual saved outputs**, including multiple nodes/images. Optional `node_id` and `image_index` choose an exact result. It returns `primary` and `images[]`, each with stable `image_id`, direct `view_url`, `filename`, `subfolder`, `type`, dimensions where available, `bytes`, `sha256`, `prompt_id`, and `node_id`.
4. In a **different ChatGPT window**, `get_output_image_ref({"image_id":"comfy:v1:..."})` retrieves the exact image and link without relying on the chat transcript. The self-contained `image_id` encodes the precise output filename, subfolder, prompt ID, node ID and image index; resolving it checks that bytes are still present in ComfyUI storage.
5. To reuse a saved output, call `stage_output_image_reference({"image_id":"comfy:v1:..."})`. The tool copies **original stored bytes** from `output/` to `input/`, validates SHA-256 and verifies `LoadImage` visibility, returning `input_filename` and a ready-to-paste `load_image` node. No resize, preview conversion or lossy recompression.
6. The `view_url` is a directly openable URL at `https://comfy.kompaszbiorek.pl/view?filename=...&type=output[&subfolder=...]`. The page shows the exact output file. **A link is valid while the output file is retained on the server**; it is not an immutable external archival copy. The ComfyUI UI is publicly reachable, so treat output links as shareable, not as secret links.

Verified live on production/canary:
- `get_output_image_ref` by `prompt_id` and by `image_id` → same URL and SHA-256;
- external HTTPS GET of returned URL → HTTP 200 and byte-perfect SHA-256;
- `stage_output_image_reference` → `byte_identical: true`, `loader_selectable: true`;
- staged reference `LoadImage → SaveImage` → completed workflow, new `prompt_id`, new exact image ID and working public URL;
- invalid `image_id` rejected; in `readonly` policy, exact-link lookup is accessible while stage/upload tools are suppressed.

Production original-result test `prompt_id`: `afad26b4-6600-4788-bbd2-dd3fbe739d28`.
Production direct result: `https://comfy.kompaszbiorek.pl/view?filename=e2e_reuse_exact_image_ref_20261102_00001_.png&type=output`.

**Remaining ChatGPT connector step:** if the existing ChatGPT app has a cached unauthenticated MCP session, reconnect using Cloudflare Access OAuth on `https://mcp-comfy.kompaszbiorek.pl/mcp`, then rescan tools. Server-side E2E is verified, but do not label an actual ChatGPT-app attachment E2E verified without invoking the newly authenticated app with an actual user upload.


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

## Cloudflare OAuth discovery compatibility — 2026-11-02

- Public MCP endpoint: `https://mcp-comfy.kompaszbiorek.pl/mcp` (Cloudflare Access Managed OAuth, owner-only login, internal MCP bearer token still enforced).
- An app refresh diagnostic found Cloudflare `403 / 1010` for some non-browser user agents (e.g. `Python-urllib/3.14`) querying MCP OAuth discovery metadata. Cloudflare zone `kompaszbiorek.pl` had Browser Integrity Check enabled.
- Fixed with a single **hostname-scoped** Cloudflare Configuration Rule at `http_config_settings`, ruleset `a854c6ec20884489a32631ed02a75f2e`, rule `f76ad874a0e04117afa2b0eccc2ac76d`: `(http.host eq "mcp-comfy.kompaszbiorek.pl")` → `set_config` with `{ "bic": false }`. Browser Integrity Check remains unchanged for unrelated hostnames; Cloudflare Access and the origin MCP bearer token remain required.
- Verified after change: non-browser OAuth metadata `200` (previously `403`); unauthenticated MCP `401` (correct); OAuth dynamic client registration `201`; PKCE authorization begins with `302` to Cloudflare Access login; production MCP and bridge healthy.
- Connection-level caveat: an existing ChatGPT app created before migration from static token/no auth to Cloudflare OAuth may still be bound to an older authentication configuration. Refreshing tools alone does not establish a new authenticated session. Reconnect the app with OAuth in ChatGPT UI; no server-side code change or Core edit can perform an interactive owner login.
- Current full tool metadata: 44 tools, approximately 219 KB `tools/list`, including 110k characters of descriptions. This is **only a size observation**, not a demonstrated cause of any app refresh failure. Avoid changing the tool surface without an app-level error identifying a schema/size limit.

## Browser 403 on a generated-image link — resolved 2026-11-02

Direct links from ChatGPT to ComfyUI output files such as
`https://comfy.kompaszbiorek.pl/view?filename=mcp_multi_output_B_20261102_00001_.png&type=output`
previously returned **HTTP 403** because browsers send `Sec-Fetch-Site: cross-site` during cross-site navigation.
ComfyUI rejects that header on all endpoints, including read-only image downloads. Plain server-side curl without the header misleadingly succeeded with HTTP 200.

**Production fix:** Caddy 2.11.7 (existing container `coolify-caddy`), host-bound
`/data/caddy/Caddyfile`, `comfy.kompaszbiorek.pl` vhost only:
- **only** `GET/HEAD /view?type=output` strips the upstream `Sec-Fetch-Site` request header;
- all other paths and `/view?type=input` remain forwarded unchanged, retaining the cross-site guard;
- no Cloudflare Workers or MCP auth changes; the ComfyUI DNS A-record is DNS-only and therefore the fix belongs in Caddy, not Cloudflare;
- config source snippet: [`caddy-cross-site-output-view.caddyfile`](caddy-cross-site-output-view.caddyfile);
- host backup: `/data/caddy/Caddyfile.bak-comfy-view-cross-site-20261102`.

E2E verification: identical URL + Chrome-like `Sec-Fetch-Site: cross-site` returns
`HTTP 200` `image/png` with 197897 bytes and SHA-256
`1433dbd6a0cad4e23e7feed82e25aacd5b4086ed875f5fd616acc165b80a7c6e`.
Control requests using the same cross-site header to `/system_stats` and to
`/view?type=input` continue to return `HTTP 403`.
Caddy validated and hot-reloaded without a container restart.

A link remains accessible while the exact output file exists on the ComfyUI volume. These are public sharable output image links — not private authenticated URLs.
