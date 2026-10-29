# ComfyUI MCP only. Build context: comfyui-mcp/ (not the entire repo).
# Pinned upstream + retained validation/image-management fixes from patches/.
FROM node:22-bookworm-slim
RUN npm i -g comfyui-mcp@0.52.206 && comfyui-mcp --version
COPY patches/patch-v1.mjs patches/patch-validator-v2.mjs patches/patch-validator-v2b.mjs patches/patch-validator-v3.mjs patches/patch-validator-v4.mjs patches/patch-validator-v5.mjs patches/patch-validator-v6.mjs patches/patch-validator-v6b.mjs patches/patch-color.mjs /tmp/
RUN set -eux; \
    for patch in patch-v1 patch-validator-v2 patch-validator-v2b patch-validator-v3 patch-validator-v4 patch-validator-v5 patch-validator-v6 patch-validator-v6b patch-color; do \
      node "/tmp/${patch}.mjs"; \
    done; \
    rm -f /tmp/patch-*.mjs
ENV LOG_LEVEL=info COMFYUI_URL=http://comfyui:8188
EXPOSE 9100
CMD ["comfyui-mcp", "--http", "--host", "0.0.0.0", "--port", "9100", "--comfyui-url", "http://comfyui:8188", "--allow-unauthenticated-non-loopback"]
