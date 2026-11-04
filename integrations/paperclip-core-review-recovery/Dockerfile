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
RUN cd /app && NO_COLOR=1 pnpm exec vitest run server/src/services/execution-blocker-undispatched.test.ts --reporter=default
RUN cd /app && pnpm --filter @paperclipai/server exec tsc --noEmit
RUN cd /app && pnpm --filter @paperclipai/server build
