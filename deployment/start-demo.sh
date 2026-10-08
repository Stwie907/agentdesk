#!/bin/sh
set -eu

agentdesk_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$agentdesk_root"

docker compose -f docker-compose.yml -f docker-compose.mock.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.mock.yml up \
    --build --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec \
    -T backend python -m app.seed_demo

printf '%s\n' \
    'AgentDesk Mock demo is ready.' \
    'Workbench: http://localhost:5173' \
    'API docs:  http://localhost:8000/docs' \
    'Select Demo Agent, then submit Calculate 40 + 2 or Hello AgentDesk.' \
    'Select MCP Order Agent, then submit Get order DEMO-1001.'
