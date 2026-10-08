#!/bin/sh
set -eu

agentdesk_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$agentdesk_root"

docker compose run --build --rm --no-deps -T mcp-check
