FROM node:22-alpine
ENV NODE_ENV=production PORT=3000
# git is required at runtime: branch deletion uses the receive-pack protocol
# (`git push --force-with-lease=<ref>:<expected> ... :<ref>`) so the delete
# carries an expected-SHA precondition. No GitHub REST DELETE is used.
RUN apk add --no-cache git
WORKDIR /app
COPY server.mjs ./server.mjs
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s CMD node -e "fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.mjs"]
