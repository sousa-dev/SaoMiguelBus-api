#!/usr/bin/env bash
set -e
exec uvicorn mcp_server.asgi:application \
  --host 0.0.0.0 \
  --port "${MCP_CONTAINER_PORT:-8001}" \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --workers "${MCP_WORKERS:-1}"