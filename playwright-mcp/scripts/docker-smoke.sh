#!/usr/bin/env bash
# Container smoke for the Playwright MCP image.
#
# Builds the image and proves inside the container that Chromium launches and
# that the shipped entrypoint (idle proxy -> MCP backend) serves a real browser
# tool call. Run this wherever Docker is available; the CI/agent runtime used to
# author the fix had no Docker socket, so this is the operator-side step:
#
#   bash playwright-mcp/scripts/docker-smoke.sh
#
# Exit 0 = image is usable; any failure aborts before a deploy.
set -euo pipefail

cd "$(dirname "$0")/.."
TAG="${1:-local/playwright-mcp:smoke}"

echo "== build $TAG"
docker build -t "$TAG" .

echo "== chromium launch inside the image"
docker run --rm --entrypoint node "$TAG" /app/scripts/smoke-chromium.cjs

echo "== idle proxy + MCP backend + browser tool call inside the image"
docker run --rm --entrypoint node "$TAG" /app/scripts/smoke-mcp.cjs

echo "DOCKER_SMOKE PASS $TAG"
