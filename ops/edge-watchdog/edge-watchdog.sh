#!/bin/sh
# Restore the public edge when Caddy is down but the container is not running.
# A docker daemon restart can leave it exited because a referenced network is
# missing; `restart: unless-stopped` does not help after an explicit stop.
set -eu
check() {
  curl -fsS --max-time 10 https://panel.zariszlif.pl/healthz >/dev/null 2>&1 &&
  curl -fsS --max-time 10 https://mcp.zariszlif.pl/health >/dev/null 2>&1
}
check && exit 0
logger -t edge-watchdog "public edge unhealthy, starting coolify-caddy"
docker start coolify-caddy >/dev/null 2>&1 || logger -t edge-watchdog "docker start failed"
sleep 10
if check; then
  logger -t edge-watchdog "public edge recovered"
  exit 0
fi
logger -t edge-watchdog "public edge still down after restart"
exit 1
