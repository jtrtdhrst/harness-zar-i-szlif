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
RUN test "$(sha256sum /app/server/src/services/issues.ts | cut -d' ' -f1)" = "b5b3066bd585870c219e50f8fd760a16486fa06c246a4605fcbb9b9185553afe" && \
    test "$(sha256sum /app/server/src/__tests__/issue-stale-execution-lock-routes.test.ts | cut -d' ' -f1)" = "0c592a764ea7eb0b8c49327e6833e3d1d6c8acc76f240ea05c80267d020e0874" && \
    cd /app && git apply --check /tmp/paperclip-reviewer-checkout.patch && git apply /tmp/paperclip-reviewer-checkout.patch && \
    test "$(sha256sum /app/server/src/services/issues.ts | cut -d' ' -f1)" = "d7d192b5afba12178840612d3436b3fce2b7e04166170c243d4ef5020235606b" && \
    test "$(sha256sum /app/server/src/__tests__/issue-stale-execution-lock-routes.test.ts | cut -d' ' -f1)" = "78abb65759d7fd296a7dec33ad7a494679abe357c50027c13b62df457d700d30"
RUN cd /app && NO_COLOR=1 pnpm exec vitest run server/src/__tests__/issue-stale-execution-lock-routes.test.ts --reporter=dot --maxWorkers=1
RUN cd /app && NO_COLOR=1 pnpm exec vitest run server/src/services/execution-blocker-undispatched.test.ts --reporter=default
RUN cd /app && pnpm --filter @paperclipai/server exec tsc --noEmit
# The pinned runtime already contains compiled runner/vendor assets. Rebuilding
# unrelated Rust runner binaries requires cargo absent from the production base.
# Emit only the changed TypeScript server module and verify that it is present.
RUN cd /app && pnpm --filter @paperclipai/server exec tsc && \
    test -s /app/server/dist/services/execution-blocker.js && \
    grep -q 'safeUndispatchedReviewHandoff' /app/server/dist/services/execution-blocker.js
