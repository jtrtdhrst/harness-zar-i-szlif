FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY . .
RUN npm run build && npm prune --omit=dev --ignore-scripts

FROM node:24-alpine
ENV NODE_ENV=production MCP_TRANSPORT=http
WORKDIR /app
RUN addgroup -S coolify && adduser -S -G coolify coolify
COPY --from=build --chown=coolify:coolify /app/dist ./dist
COPY --from=build --chown=coolify:coolify /app/node_modules ./node_modules
COPY --from=build --chown=coolify:coolify /app/package.json ./package.json
USER coolify
EXPOSE 3000
CMD ["node", "dist/http.js"]
