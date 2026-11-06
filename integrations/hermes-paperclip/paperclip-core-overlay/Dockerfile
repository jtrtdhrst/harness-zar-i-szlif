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
COPY integrations/hermes-paperclip/paperclip-core-overlay/model-routing.patch /tmp/hermes-model-routing.patch
COPY integrations/hermes-paperclip/paperclip-core-overlay/model-routing-tests.patch /tmp/hermes-model-routing-tests.patch
COPY integrations/paperclip-core-review-recovery/reviewer-checkout.patch /tmp/paperclip-reviewer-checkout.patch
COPY integrations/hermes-paperclip/paperclip-core-overlay/reconciliation-overlay.patch /tmp/h03-reconciliation.patch
COPY integrations/hermes-paperclip/paperclip-core-overlay/execution-blocker-rework.test.ts /app/server/src/services/execution-blocker-rework.test.ts

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
    test "$(sha256sum /app/packages/adapters/hermes/src/gateway/server/execute.ts | cut -d' ' -f1)" = "977e6ecfc457c330b8bc59e020456ca3361aebe877b065d4878573cd3cae0578"; \
    git apply --check /tmp/hermes-model-routing.patch; \
    git apply /tmp/hermes-model-routing.patch; \
    git apply --check /tmp/hermes-model-routing-tests.patch; \
    git apply /tmp/hermes-model-routing-tests.patch; \
    test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "bcf4e0c859c21828b7d5a2a705cf1163b35839fee0be581ddfa8c654dcc9e78d"; \
    test "$(sha256sum /app/packages/adapters/hermes/src/gateway/server/execute.ts | cut -d' ' -f1)" = "c30d88b557b7c443b76ff52e77cff93fdea1427eae030cdc65563cc850d2b051"


# Apply the independently tested reviewer rework fix from PR #57 to this exact
# Hermes-patched source. These are source attestation hashes from the isolated
# combined build; fail on drift rather than silently patching different bytes.
RUN set -eux; \
    test "$(sha256sum /app/server/src/services/issues.ts | cut -d' ' -f1)" = "b5b3066bd585870c219e50f8fd760a16486fa06c246a4605fcbb9b9185553afe"; \
    test "$(sha256sum /app/server/src/routes/issues.ts | cut -d' ' -f1)" = "641b3d9cb5e744671527f16129dd78518376dca31616b845ec6b8da99d636d8c"; \
    test "$(sha256sum /app/server/src/services/heartbeat.ts | cut -d' ' -f1)" = "f3369d87010af52fa30a69df6cc4f8b0b227d0644aef9a13840bc4604e0c0691"; \
    cd /app; git apply --check /tmp/paperclip-reviewer-checkout.patch; \
    git apply /tmp/paperclip-reviewer-checkout.patch; \
    test "$(sha256sum /app/server/src/services/issues.ts | cut -d' ' -f1)" = "1fe74c51a5e93d9323868425b5780273ce8790620787ed34c6c7f98c42d60bc5"; \
    test "$(sha256sum /app/server/src/routes/issues.ts | cut -d' ' -f1)" = "6631daa3d0ddf679e00d4514b60beef654a5671a06e80855d4bd568f0833e125"; \
    test "$(sha256sum /app/server/src/services/heartbeat.ts | cut -d' ' -f1)" = "6ce316dc1329f1d58d721994f409a30a0fc730691b93d43abf30a94f2bb41879"

# H03 legacy cancellation recovery is strictly pre-provider, and only a new
# CTO changes_requested return-owner run is admitted; historical audit kept.
RUN set -eux; \
    test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "bcf4e0c859c21828b7d5a2a705cf1163b35839fee0be581ddfa8c654dcc9e78d"; \
    cd /app; git apply --check /tmp/h03-reconciliation.patch; \
    git apply /tmp/h03-reconciliation.patch; \
    test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "7ec285484ef6664321e9b2e6aba73eb2c0254554db703328f5a02d6169a960a0"

# Fail closed unless the exact Core source matches the reviewed production base.
# A definitive Hermes /v1/runs auth denial must not manufacture a legacy recovery hold.
COPY integrations/paperclip-core-review-recovery/legacy-auth-admission.patch /tmp/paperclip-legacy-auth-admission.patch
COPY integrations/paperclip-core-review-recovery/legacy-auth-admission.integration.test.ts /app/server/src/services/legacy-auth-admission.integration.test.ts
RUN test "$(sha256sum /app/server/src/services/legacy-execution-recovery.ts | cut -d' ' -f1)" = "dd5997b5f46e58d6033b7144c4ebbcd45afbea83adaa2b59e5c761ef1856de5c" && \
    cd /app && git apply --check /tmp/paperclip-legacy-auth-admission.patch && \
    git apply /tmp/paperclip-legacy-auth-admission.patch && \
    test "$(sha256sum /app/server/src/services/legacy-execution-recovery.ts | cut -d' ' -f1)" = "36046af06728f6e800d5eb87289025014150b1a1b0ebe927290619fc7c2e7712" && \
    chown node:node /app/server/src/services/legacy-auth-admission.integration.test.ts

RUN find /app -type d -name .vite-temp -prune -exec chown node:node {} + && \
    chown node:node /app/server/src/services/execution-blocker-rework.test.ts
USER node
RUN cd /app && NO_COLOR=1 pnpm exec vitest run \
    server/src/services/execution-blocker-rework.test.ts \
    server/src/services/legacy-execution-recovery.test.ts \
    server/src/services/legacy-auth-admission.integration.test.ts \
    server/src/services/execution-blocker-undispatched.test.ts \
    server/src/__tests__/issue-stale-execution-lock-routes.test.ts \
    server/src/__tests__/issue-h03-false-progress-rework.integration.test.ts \
    packages/adapters/hermes/src/gateway/server/execute.test.ts \
    --reporter=json --outputFile=/tmp/hermes-h03-full-suite.json --maxWorkers=1 && \
    node -e "const r=require('/tmp/hermes-h03-full-suite.json');if(r.numPassedTests!==161||r.numPendingTests!==0||r.numFailedTests!==0)throw Error('Expected 161 real tests with zero skip/fail');"
USER root
RUN cd /app && pnpm --filter @paperclipai/hermes-paperclip-adapter typecheck && \
    pnpm --filter @paperclipai/server exec tsc --noEmit && \
    pnpm --filter @paperclipai/server exec tsc && \
    grep -q 'safeUndispatchedReviewHandoff' /app/server/dist/services/execution-blocker.js && \
    grep -q 'safeAbortedLegacyReworkHandoff' /app/server/dist/services/execution-blocker.js && \
    grep -q 'confirmedHermesCreateAuthDenial' /app/server/dist/services/legacy-execution-recovery.js
