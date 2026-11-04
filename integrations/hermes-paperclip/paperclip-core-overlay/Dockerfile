# Only the Hermes adapter source is patched; Paperclip Core/server remains immutable.
# Fail if the pinned base image or resulting adapter bytes drift.
FROM ghcr.io/paperclipai/paperclip:2026.1023.0
LABEL org.opencontainers.image.source="https://github.com/miloszspyrka-code/harness-zar-i-szlif" \
      org.opencontainers.image.description="Paperclip 2026.1023.0 Hermes adapter-only audited overlay" \
      org.opencontainers.image.revision="paperclip-issue-KOMAA-1564-source-3fc315ed4b70e76c350c168f43b2dc4176786bdc"
COPY overlay.patch /tmp/hermes-adapter.patch
RUN test "$(sha256sum /app/packages/adapters/hermes/src/gateway/server/execute.ts | cut -d' ' -f1)" = "e3593d03d40b37b215d68342c8d615d26014bf5892eef79151b6153737764701" && \
    cd /app && git apply --check /tmp/hermes-adapter.patch && git apply /tmp/hermes-adapter.patch && \
    test "$(sha256sum /app/packages/adapters/hermes/src/gateway/server/execute.ts | cut -d' ' -f1)" = "ad69e65cf4827dcc46d33110d80511ce7e09d07030e1e19a2a8a7e3e0c44b249" && \
    pnpm --filter @paperclipai/hermes-paperclip-adapter typecheck
