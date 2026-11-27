FROM mcr.microsoft.com/playwright:v1.57.0-noble

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_ENV=production \
    IDLE_SECONDS=600 \
    LISTEN_PORTS=8932,8761 \
    HOME=/home/node

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund \
    && npm cache clean --force \
    && ln -s /app/node_modules/@playwright/mcp/cli.js /app/cli.js

# The pinned MCP release requires Chromium 1247; the base image ships another revision.
# Install the revision requested by the actual locked playwright-core dependency.
RUN node node_modules/playwright-core/cli.js install chromium chromium-headless-shell

COPY idle-proxy.cjs ./
COPY scripts/ ./scripts/

# Fail the build if real Chromium cannot launch or proxy navigation/snapshot fails.
RUN node /app/scripts/smoke-chromium.cjs && node /app/scripts/smoke-mcp.cjs

EXPOSE 8932 8761
ENTRYPOINT ["node", "/app/idle-proxy.cjs"]
