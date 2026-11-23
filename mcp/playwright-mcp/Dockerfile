FROM mcr.microsoft.com/playwright:v1.57.0-noble

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    NODE_ENV=production \
    IDLE_SECONDS=600 \
    LISTEN_PORTS=8932,8761 \
    HOME=/home/node

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund \
    && npm cache clean --force \
    && ln -s /app/node_modules/@playwright/mcp/cli.js /app/cli.js

COPY idle-proxy.cjs ./

EXPOSE 8932 8761
ENTRYPOINT ["node", "/app/idle-proxy.cjs"]
