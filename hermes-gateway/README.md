# Hermes Gateway deployment contract

The canonical production build lives at `integrations/hermes-paperclip/gateway/` in this repository and is introduced by PR #31.

This directory records the earlier private canary only. Its duplicate `Dockerfile` has been removed so production has one source-controlled build contract.

- **Canonical repository:** `miloszspyrka-code/harness-zar-i-szlif`
- **Production build context:** `/integrations/hermes-paperclip/gateway`
- **Dockerfile:** `/Dockerfile`
- **Watch paths:** `integrations/hermes-paperclip/gateway/**`
- **Pinned runtime:** `nousresearch/hermes-agent:v0.22.5`
- **Persistent state:** Keep the existing production `/opt/data` volume attached; candidate deployments use a separate volume.
- **Ingress:** Retain the existing Cloudflare Tunnel/Access routes. Do not add Workers or expose a new public domain.

The old `/hermes-gateway` canary established private Git-backed build access only. It did not establish Hermes–Paperclip–Hindsight–Opik E2E or authorize production cutover. Production remains unchanged until the canonical PR is independently reviewed and the exact merged SHA, image digest, health, persistence, API behavior and rollback are verified.
