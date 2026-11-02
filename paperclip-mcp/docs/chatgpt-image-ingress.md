# ChatGPT → Paperclip MCP → ComfyUI: production image ingress

**Deployment:** 2026-11-02, Coolify service `paperclip-mcp` UUID `gevr1m6rdj4t4fbhcjvqv8gg`, subapp UUID `yvtwulblrzpmuvi72xd9sey3`; image `paperclip-mcp:chatgpt-image-final-20261102`, OCI digest `sha256:b5c9a29df706ac7cd5fde3cfe9ee68c9dc6dd793b57008e5593bc6cbf2d60762`. Prior rollback tag: `fs9rik9axzl1ubbimekvqs03:eadd6814c29c23cd139958fa3705e197fc60b6c6`. Docker image is **local to this Coolify server**, not pushed to GHCR. Rebuild from this repo or arrange trusted image distribution before moving servers. Do not treat merely changing GitHub main as a Coolify service auto-deploy.

## Contract

New tool `paperclipUploadChatgptImage` lives in `mcp-gateway/chatgpt-image.mjs` and is attached per authenticated gateway session in `gateway.mjs`. It does **not** alter Paperclip Core.

Required `issue_id`: the existing Paperclip issue UUID. The caller must resolve as Board or agent, and the Paperclip API must authorize the issue read in the correct company. Agent principals may upload only to their **own assigned** issue.

Preferred **ChatGPT file input** `file` is the *exact official OpenAI file object*, declared in MCP `inputSchema` and `_meta["openai/fileParams"] = ["file"]`:

```json
{"issue_id":"<existing Paperclip issue UUID>",
 "file":{"download_url":"https://<short-lived file URL>","file_id":"file_...","mime_type":"image/png","file_name":"reference.png"},
 "expected_sha256":"<64 hex, optional>",
 "stage_to_comfyui":true}
```

The required properties **inside** `file` are `download_url` and `file_id`. The `mime_type` and `file_name` properties are declared but optional. `file` itself is optional so clients may send a secure `download_url` or `data_base64` directly as a fallback. A bare string `file_id` is **not** a valid ChatGPT fileParam schema and is not enough to fetch bytes; the tool rejects missing byte sources explicitly rather than reporting success.

Security boundaries: image PNG/JPEG/WebP signatures and safe basenames; up to 30 MiB downloaded; HTTPS public-DNS-only with pinned public-resolution IP and no redirects (reject private/mapped/link-local destinations); signed SHA-256 / byte count checks; no untrusted URL may override the internally configured ComfyUI origin (`http://comfyui:8188`). Original bytes persist inside the existing `paperclip_mcp_state` volume under `/paperclip/mcp-gateway/chatgpt-images` with a content-addressed ID `pcimg:<sha256>`. No public unauthenticated file server added.

ComfyUI staging uses an immutable filename derived from SHA-256 plus safe name, `POST /upload/image`, exact original-byte `GET /view?type=input` SHA readback and `/object_info/LoadImage` enumeration. Repeated same file/name returns the same `input_filename`, does not overwrite any different file. Attempts to write a receipt comment on the existing Paperclip issue; `e2e_verified` requires both actual ComfyUI LoadImage readback and actual successful Paperclip comment. If either fails, tool returns `isError: true` with specific partial status; do not use the result as CPO asset approval.

## Fresh production evidence (2026-11-02)

- Coolify new container image digest read from actual Docker inspect; service reported healthy. Live public Paperclip MCP route `https://paperclip-mcp.zariszlif.pl/mcp` returned authenticated `initialize`, `tools/list` (200 tools), real harmless call, OAuth metadata; unauthenticated POST denied 401. The legacy `SOURCE_RUNTIME_MISMATCH` in `paperclipVerifyLiveMCP` is between **Paperclip Core** version/environment commit labels, not proof the MCP overlay deployed incorrectly; keep separately tracked.
- Unit/schema probe in running production image: `_meta["openai/fileParams"]=["file"]`, strict valid OpenAI object PASS, bare-string schema rejected.
- Real image bytes reused from previously approved Żar style reference: size **762979**, SHA `0ef5e535677030f697a75f2d59f8ad8895119ffc85c9f2063374d7e6264d059c`, stored in Paperclip MCP state and posted to ComfyUI. Readback SHA identical, exact `LoadImage` choice present. Twice repeated with deterministic destination `0ef5e535677030f6_chatgpt-paperclip-zar-retry-proof-20261102.png`: **same SHA + same filename PASS**, no second file.
- Real HTTPS `file` object fixture from `https://raw.githubusercontent.com/github/explore/main/topics/javascript/javascript.png`: **10380 B**, SHA `dffd702034de08fc0d11eebc90e0118a3f8615e1d798a1796656646cf862da60`; HTTPS fetch → durable write → Comfy input → byte-identical readback → LoadImage **PASS**.
- SSRF denial for `https://127.0.0.1/forbidden.png`: `PUBLIC_HTTPS_REQUIRED` (PASS).
- **LIMITATION:** these direct production-module tests mocked Paperclip issue GET and comment responses. The issue comment endpoint was **not proven through this new tool with a real external ChatGPT caller**. The ChatGPT plugin connection may require manual tool refresh; until a genuine attached file is passed through the refreshed connector, **do not call client→Paperclip authenticated fileParams E2E verified**.

## Integration with mascot tasks

Attach new image to an existing issue such as `KOMAA-1528` only when it is part of its actual task. Use the returned ComfyUI `input_filename` in the ComfyUI graph's `LoadImage` node; record the source file ID, SHA and role in the generation manifest. A positive image transfer is not independent CPO acceptance; no publication without CPO review. Images are never made public merely by staging to ComfyUI.

## Deployment and rollback

The active production endpoint stays in the existing Coolify service, with the same persistent `paperclip_mcp_state` and Cloudflare hostname. No new Worker, route, service, agent or Paperclip Core edit. The source commit sequence is on `main` in `harness-zar-i-szlif/paperclip-mcp`. The local OCI image was built as a minimal layer on the previously-running production gateway image and switched using the authorized Coolify service compose update + start_application. **Rollback** via restoring the prior compose image tag above, then `start_application` force; do not delete the persistent volume or OAuth store.

**Outstanding to mark 100% E2E:** use the refreshed ChatGPT Paperclip MCP connector to send one *actual attached user image* with the official `file` object, prove a real caller authorization, native issue comment readback, and new-session downstream LoadImage use. Keep that test separate from already-verified module→Comfy bytes and checksums.
