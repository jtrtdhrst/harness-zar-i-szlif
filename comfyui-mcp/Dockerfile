# ComfyUI MCP only. Build context: comfyui-mcp/ (not the entire repo).
# Pinned upstream + retained validation/image-management fixes from patches/.
FROM node:22-bookworm-slim
RUN npm i -g comfyui-mcp@0.52.206 && comfyui-mcp --version
COPY patches/patch-v1.mjs patches/patch-validator-v2.mjs patches/patch-validator-v2b.mjs patches/patch-validator-v3.mjs patches/patch-validator-v4.mjs patches/patch-validator-v5.mjs patches/patch-validator-v6.mjs patches/patch-validator-v6b.mjs patches/patch-partner-auth.mjs patches/patch-color.mjs /tmp/
RUN set -eux; \
    for patch in patch-v1 patch-validator-v2 patch-validator-v2b patch-validator-v3 patch-validator-v4 patch-validator-v5 patch-validator-v6 patch-validator-v6b patch-partner-auth patch-color; do \
      node "/tmp/${patch}.mjs"; \
    done; \
    rm -f /tmp/patch-*.mjs
# The attachment source and registration live in this SAME canonical MCP folder.
COPY chatgpt-file-tool.js /usr/local/lib/node_modules/comfyui-mcp/dist/tools/chatgpt-file-tool.js
COPY output-image-refs.js /usr/local/lib/node_modules/comfyui-mcp/dist/tools/output-image-refs.js
COPY patches/patch-chatgpt-upload.mjs /tmp/patch-chatgpt-upload.mjs
RUN node /tmp/patch-chatgpt-upload.mjs && node --check /usr/local/lib/node_modules/comfyui-mcp/dist/tools/chatgpt-file-tool.js && node --check /usr/local/lib/node_modules/comfyui-mcp/dist/tools/output-image-refs.js && rm /tmp/patch-chatgpt-upload.mjs
ENV LOG_LEVEL=info COMFYUI_URL=http://comfyui:8188 COMFYUI_PUBLIC_URL=https://comfy.kompaszbiorek.pl
EXPOSE 9100
CMD ["comfyui-mcp", "--http", "--host", "0.0.0.0", "--port", "9100", "--comfyui-url", "http://comfyui:8188", "--allow-unauthenticated-non-loopback"]
