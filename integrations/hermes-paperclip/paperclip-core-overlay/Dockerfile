# Unified source-pinned Paperclip release: preserve the already deployed
# independent review recovery (PR #43) while enabling the Hermes adapter (PR #36).
# Do not publish/deploy until the independent review and real task E2E pass.
FROM ghcr.io/paperclipai/paperclip:2026.1023.0
LABEL org.opencontainers.image.source="https://github.com/miloszspyrka-code/harness-zar-i-szlif" \
      org.opencontainers.image.description="Paperclip 2026.1023.0 review recovery plus Hermes adapter" \
      org.opencontainers.image.revision="KOMAA-1564-Hermes-with-reviewed-PR43-Core"

# Build context is the harness repo root (both copies live in one source repo).
COPY integrations/paperclip-core-review-recovery/overlay.patch /tmp/paperclip-review-recovery.patch
COPY integrations/paperclip-core-review-recovery/execution-blocker-undispatched.test.ts /app/server/src/services/execution-blocker-undispatched.test.ts
COPY integrations/hermes-paperclip/paperclip-core-overlay/overlay.patch /tmp/hermes-adapter.patch
COPY integrations/hermes-paperclip/paperclip-core-overlay/adapter-runmcp-tests.patch /tmp/hermes-adapter-tests.patch

# Apply BOTH source patches; fail closed if either upstream code or expected
# resulting bytes changed. Keep the native review state machine untouched.
RUN set -eux; \
    test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "bccaebea9d6252b1a0f5af0e2b8c669d72a4ce66fdfbbd370ff44a7c99a0d64a"; \
    test "$(sha256sum /app/packages/adapters/hermes/src/gateway/server/execute.ts | cut -d' ' -f1)" = "e3593d03d40b37b215d68342c8d615d26014bf5892eef79151b6153737764701"; \
    cd /app; \
    git apply --check /tmp/paperclip-review-recovery.patch; \
    git apply /tmp/paperclip-review-recovery.patch; \
    git apply --check /tmp/hermes-adapter.patch; \
    git apply /tmp/hermes-adapter.patch; \
    git apply --check /tmp/hermes-adapter-tests.patch; \
    git apply /tmp/hermes-adapter-tests.patch; \
    test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "bcf4e0c859c21828b7d5a2a705cf1163b35839fee0be581ddfa8c654dcc9e78d"; \
    test "$(sha256sum /app/packages/adapters/hermes/src/gateway/server/execute.ts | cut -d' ' -f1)" = "977e6ecfc457c330b8bc59e020456ca3361aebe877b065d4878573cd3cae0578"

# The same image must satisfy the Core recovery and Hermes adapter suites,
# TypeScript checks and compiled Core runtime. No fake green health-only build.
RUN cd /app && pnpm exec vitest run \
    server/src/services/execution-blocker-undispatched.test.ts \
    packages/adapters/hermes/src/gateway/server/execute.test.ts \
    --reporter=dot
RUN cd /app && pnpm --filter @paperclipai/hermes-paperclip-adapter typecheck && \
    pnpm --filter @paperclipai/server exec tsc --noEmit
RUN cd /app && pnpm --filter @paperclipai/server exec tsc && \
    test -s /app/server/dist/services/execution-blocker.js && \
    grep -q 'safeUndispatchedReviewHandoff' /app/server/dist/services/execution-blocker.js
