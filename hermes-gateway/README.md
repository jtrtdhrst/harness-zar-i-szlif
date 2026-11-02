# Hermes Gateway — Git source of truth

- **Canonical repository:** `miloszspyrka-code/harness-zar-i-szlif` (do **not** create `hermes-zar-i-szlif`).
- **Source directory:** `hermes-gateway/`.
- **Integration branch:** `main` after reviewed PR; task branches are for changes, not production releases.
- **Coolify:** existing `Hermes Gateway POC` project, running app `2sganhxhhnioiqh4an9g2f4k`.
- **Build context:** `/hermes-gateway`; **Dockerfile:** `/Dockerfile`; **Watch paths:** `hermes-gateway/**`.
- **Runtime image:** `nousresearch/hermes-agent:v0.22.5` (matches current POC; pin immutable digest on release).
- **Runtime config:** named profiles and credentials remain in native Hermes/Coolify facilities, not in Git. The production volume is `/opt/data`, never replace or reinitialize.
- **Ingress:** Cloudflare Tunnel/Access to Coolify; no additional Cloudflare Worker.
- **Do not touch** the three existing Workers (`stronaglowna`, `zariszlif-prawne`, `paperclip-mcp`).

## Cutover checklist

1. Grant the existing **Coolify** GitHub App `coolify-zar-i-szlif` access to this private repository; confirm through `github_apps(list_repos)`. This access is independent of the ChatGPT GitHub connector.
2. Merge an independently reviewed PR into harness `main`; read back exact SHA and files.
3. Build a private unexposed Coolify Git-backed candidate; attach a **separate test volume**, not production `/opt/data`. Match the source path and Dockerfile above.
4. Validate gateway authenticated request, `/p/hermes-test`, negative cross-profile access, real Paperclip Named MCP call, Hindsight isolation and correlated Opik trace.
5. Preserve active POC until the replacement passes, then move only the approved runtime to the correct Coolify project, with pinned commit/digest and verified rollback.
6. Prove webhook deployment for `hermes-gateway/**`, and prove unrelated folders do **not** rebuild Hermes.
7. Record release acceptance in the existing Paperclip release task; no Paperclip Core changes, no agent-profile cutover by implication.

The Dockerfile in this folder reproduces the currently running *base POC* image, **not** a claim that Hermes–Paperclip–Hindsight–Opik is fully accepted. Existing `integrations/hermes-paperclip/` PR evidence remains an independent gate.
