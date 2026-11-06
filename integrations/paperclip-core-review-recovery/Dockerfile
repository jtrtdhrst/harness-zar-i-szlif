# Independent Paperclip Core review-recovery bug fix, not the Hermes adapter overlay.
# The prior failure is a resolved action (no-replay hold) retained after a stopped
# pre-dispatch, confirmed-reassignment run; it blocks even independent CTO review.
FROM ghcr.io/paperclipai/paperclip:2026.1023.0
LABEL org.opencontainers.image.source="https://github.com/miloszspyrka-code/harness-zar-i-szlif" \
      org.opencontainers.image.description="Paperclip Core pre-dispatch independent-review hold regression fix"
COPY overlay.patch /tmp/paperclip-review-recovery.patch
COPY execution-blocker-undispatched.test.ts /app/server/src/services/execution-blocker-undispatched.test.ts
RUN test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "bccaebea9d6252b1a0f5af0e2b8c669d72a4ce66fdfbbd370ff44a7c99a0d64a" && \
    cd /app && git apply --check /tmp/paperclip-review-recovery.patch && git apply /tmp/paperclip-review-recovery.patch && \
    test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "bcf4e0c859c21828b7d5a2a705cf1163b35839fee0be581ddfa8c654dcc9e78d"
COPY reviewer-checkout.patch /tmp/paperclip-reviewer-checkout.patch
# H03 Core source: pinned upstream 1b4c803816e82b0265c8422e1a804327a7ed8c54,
# exact reviewed candidate source 78ac75e5178f2036ff01561c096967951f529bb3.
# All original and final files must match, or the image build stops.
RUN test "$(sha256sum /app/server/src/services/issues.ts | cut -d' ' -f1)" = "b5b3066bd585870c219e50f8fd760a16486fa06c246a4605fcbb9b9185553afe" && \
    test "$(sha256sum /app/server/src/routes/issues.ts | cut -d' ' -f1)" = "641b3d9cb5e744671527f16129dd78518376dca31616b845ec6b8da99d636d8c" && \
    test "$(sha256sum /app/server/src/services/heartbeat.ts | cut -d' ' -f1)" = "f3369d87010af52fa30a69df6cc4f8b0b227d0644aef9a13840bc4604e0c0691" && \
    test "$(sha256sum /app/server/src/__tests__/issue-stale-execution-lock-routes.test.ts | cut -d' ' -f1)" = "0c592a764ea7eb0b8c49327e6833e3d1d6c8acc76f240ea05c80267d020e0874" && \
    test ! -e /app/server/src/__tests__/issue-h03-false-progress-rework.integration.test.ts && \
    cd /app && git apply --check /tmp/paperclip-reviewer-checkout.patch && git apply /tmp/paperclip-reviewer-checkout.patch && \
    test "$(sha256sum /app/server/src/services/issues.ts | cut -d' ' -f1)" = "1fe74c51a5e93d9323868425b5780273ce8790620787ed34c6c7f98c42d60bc5" && \
    test "$(sha256sum /app/server/src/routes/issues.ts | cut -d' ' -f1)" = "6631daa3d0ddf679e00d4514b60beef654a5671a06e80855d4bd568f0833e125" && \
    test "$(sha256sum /app/server/src/services/heartbeat.ts | cut -d' ' -f1)" = "6ce316dc1329f1d58d721994f409a30a0fc730691b93d43abf30a94f2bb41879" && \
    test "$(sha256sum /app/server/src/__tests__/issue-stale-execution-lock-routes.test.ts | cut -d' ' -f1)" = "664ba301371d061fcd585d9aba572a3fcb8d4d1cbc578fd20be58d3d3d162bf8" && \
    test "$(sha256sum /app/server/src/__tests__/issue-h03-false-progress-rework.integration.test.ts | cut -d' ' -f1)" = "6c3b400e8ea1c8e69a7966d21ff01397b0825d9b6a9a07e61588f8a339b5b552"
# Verified issue-scoped H02 legacy disposition recovery. Source is pinned to
# the exact preceding PR43-overlay SHA; unknown drift stops the build.
COPY reconciliation-overlay.patch /tmp/paperclip-reconciliation-overlay.patch
COPY execution-blocker-rework.test.ts /app/server/src/services/execution-blocker-rework.test.ts
RUN test "$(sha256sum /app/server/src/services/execution-blocker.ts | cut -d' ' -f1)" = "bcf4e0c859c21828b7d5a2a705cf1163b35839fee0be581ddfa8c654dcc9e78d" && \
    cd /app && git apply --check /tmp/paperclip-reconciliation-overlay.patch && \
    git apply /tmp/paperclip-reconciliation-overlay.patch && \
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

# PostgreSQL integration tests must ACTUALLY execute: Vitest's all-skipped exit 0
# is not acceptable. Run under the existing non-root node account.
USER node
RUN cd /app && NO_COLOR=1 pnpm exec vitest run \
    server/src/__tests__/issue-stale-execution-lock-routes.test.ts \
    server/src/__tests__/issue-h03-false-progress-rework.integration.test.ts \
    server/src/services/execution-blocker-undispatched.test.ts \
    server/src/services/execution-blocker-rework.test.ts \
    server/src/services/legacy-execution-recovery.test.ts \
    server/src/services/legacy-auth-admission.integration.test.ts \
    --reporter=json --outputFile=/tmp/paperclip-h03-tests.json --maxWorkers=1 && \
    node -e "const r=require('/tmp/paperclip-h03-tests.json');if(r.numPassedTests!==51||r.numPendingTests!==0||r.numFailedTests!==0)throw Error('H03 expected 51 real passing tests, zero skipped or failed');"
USER root
RUN cd /app && pnpm --filter @paperclipai/server exec tsc --noEmit
# The pinned runtime already contains compiled runner/vendor assets. Rebuilding
# unrelated Rust runner binaries requires cargo absent from the production base.
# Emit only the changed TypeScript server module and verify that it is present.
RUN cd /app && pnpm --filter @paperclipai/server exec tsc && \
    test -s /app/server/dist/services/execution-blocker.js && \
    grep -q 'safeUndispatchedReviewHandoff' /app/server/dist/services/execution-blocker.js && \
    grep -q 'safeAbortedLegacyReworkHandoff' /app/server/dist/services/execution-blocker.js && \
    grep -q 'confirmedHermesCreateAuthDenial' /app/server/dist/services/legacy-execution-recovery.js
