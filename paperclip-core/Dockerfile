# Production-source pinned Paperclip Core validation image; NOT the MCP gateway.
# No deployment from this Dockerfile. Independent review + controlled rollout required.
ARG PAPERCLIP_CORE_BASE=ghcr.io/paperclipai/paperclip@sha256:40f46940c4612ead131aebe6079cd4651f8cd1434af49f7c621887f4a452a62e
FROM ${PAPERCLIP_CORE_BASE}
WORKDIR /app
USER root
COPY apply-native-invariants.mjs native-issue-question-governance.ts native-issue-question-governance.test.ts native-core-review-guard.test.ts /opt/paperclip-core-overrides/
ARG PAPERCLIP_CORE_BASE_SHA=1b4c803816e82b0265c8422e1a804327a7ed8c54
RUN PAPERCLIP_CORE_BASE_SHA=${PAPERCLIP_CORE_BASE_SHA} node /opt/paperclip-core-overrides/apply-native-invariants.mjs
# Real Core tests, not the MCP-only suite.
RUN /app/node_modules/.bin/vitest run --root /app \
    server/src/services/native-issue-question-governance.test.ts \
    server/src/__tests__/native-core-review-guard.test.ts \
    server/src/__tests__/issue-execution-policy.test.ts \
    server/src/__tests__/issues-checkout-wakeup.test.ts \
    --maxWorkers=2 --reporter=dot
RUN pnpm --filter @paperclipai/server build
USER node
