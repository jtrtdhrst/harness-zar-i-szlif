# Build gate: the exact source used by Coolify must pass the MCP HTTP regression suite.
FROM node:24-alpine AS verify
RUN apk add --no-cache git
WORKDIR /app
COPY server.mjs ./server.mjs
COPY tests ./tests
RUN node --check server.mjs && node --test tests/server.test.mjs

# Runtime image contains only the tested server, not test fixtures.
FROM node:24-alpine
ENV NODE_ENV=production PORT=3000
# A git client is needed for SHA-leased ref operations; no token is baked into the image.
RUN apk add --no-cache git
WORKDIR /app
COPY --from=verify /app/server.mjs ./server.mjs
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s CMD node -e "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.mjs"]
