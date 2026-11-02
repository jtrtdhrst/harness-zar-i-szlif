# Hermes Gateway runtime — pinned to the currently running Coolify POC image.
# No Paperclip Core or Cloudflare Workers runtime is built here.
# Persistent /opt/data, profile keys, gateway settings and integrations are supplied
# by the owning Coolify application and are not embedded in the image.
FROM nousresearch/hermes-agent:v0.22.5
CMD ["gateway", "run"]
