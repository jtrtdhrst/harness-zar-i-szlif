# Playwright MCP server + idle HTTP proxy.
#
# VERSION PAIRING IS A CONTRACT. `package-lock.json` pins @playwright/mcp and the
# exact Playwright build it depends on (currently 1.64.0-alpha-<stamp>), and that
# build launches one specific Chromium revision. A base image only ships the
# browsers of its own release, so a mismatched pair fails at the first browser
# call, not at build time:
#   browserType.launch: Executable doesn't exist at
#   /ms-playwright/chromium_headless_shell-1247/...
# That is exactly what happened on 2026-11-17 with a v1.57.0 base image and
# @playwright/mcp 0.0.83 (Chromium 1247 required, 1200 shipped).
#
# The image therefore:
#   1. installs dependencies from the lockfile only (`npm ci`, never `npm install`);
#   2. installs the Chromium build the pinned Playwright asks for, because the
#      base image cannot provide it;
#   3. fails the build unless Chromium actually launches and the MCP backend
#      serves a real browser tool call through the shipped entrypoint.
# `scripts/check-browser-pairing.cjs` (run by `npm test`) guards rules 1-3 in
# source, so the defect cannot come back unnoticed.
FROM mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_ENV=production \
    IDLE_SECONDS=600 \
    LISTEN_PORTS=8932,8761 \
    HOME=/root

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund \
    && npm cache clean --force \
    && ln -s /app/node_modules/@playwright/mcp/cli.js /app/cli.js

# The base image's browsers belong to its own release; this adds the revision
# the lockfile resolves. Deterministic because the Playwright version is pinned
# exactly by @playwright/mcp and by the lockfile.
RUN node node_modules/playwright-core/cli.js install chromium chromium-headless-shell

COPY idle-proxy.cjs ./
COPY scripts/ ./scripts/

# Fail the build on a missing or mismatched browser instead of failing in
# production traffic.
RUN node /app/scripts/smoke-chromium.cjs
# Fail the build if the shipped entrypoint cannot start the MCP backend and
# serve a real Chromium tool call.
RUN node /app/scripts/smoke-mcp.cjs

EXPOSE 8932 8761
ENTRYPOINT ["node", "/app/idle-proxy.cjs"]
