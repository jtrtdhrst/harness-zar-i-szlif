# comfy-mcp — Coolify service metadata only

This folder identifies the existing Coolify service (`kkhfw0napmeaqewgdirwhc1h`) and its volume ownership. It contains **no application source, Dockerfile, or patches**.

All ComfyUI MCP source, attachment-upload logic, OAuth bridge, Docker image build, compose, tests, and deployment instructions live in the canonical folder:

**[comfyui-mcp/](../comfyui-mcp/)**

Production service image: `local/comfyui-mcp:0.52.206-chatfiles6` (built from `comfyui-mcp/Dockerfile`).

Do not create another ComfyUI MCP implementation in this folder. Keep private tokens and volumes outside Git. Historical patch implementations remain available in Git history.
