#!/bin/bash
set -e

echo "Starting Reflex backend on port 8000..."
reflex run --env prod --backend-only --backend-port 8000 &

sleep 5

echo "Starting Caddy reverse proxy on port 8080..."
caddy run --config /etc/caddy/Caddyfile
