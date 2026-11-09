FROM ghcr.io/multica-ai/multica-backend:v0.8.1@sha256:864a97102959895b174f4fb1e2798bc38c896ea9ff33497564ec11eac5728374 AS multica
FROM node:24.20.0-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf

ENV NODE_ENV=production PORT=3000 MULTICA_CLI=/usr/local/bin/multica
WORKDIR /app
COPY --chown=node:node package.json catalog.mjs server.mjs ./
COPY --chown=node:node docs/paperclip-tool-baseline.json ./docs/paperclip-tool-baseline.json
COPY --from=multica --chmod=0755 /app/multica /usr/local/bin/multica
RUN /usr/local/bin/multica --version 2>&1 | grep -E 'multica v?0\.8\.1 \(commit: b1ea927de' >/dev/null
RUN mkdir -p /tmp/multica-mcp-home && chown node:node /tmp/multica-mcp-home
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD node -e "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.mjs", "http"]
