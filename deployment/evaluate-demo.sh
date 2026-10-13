#!/bin/sh
set -eu

agentdesk_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$agentdesk_root"

docker compose -f docker-compose.yml -f docker-compose.mock.yml run \
  --build --rm --no-deps -T evaluation

printf '%s\n' 'Local reports: evaluation/reports/report.json and evaluation/reports/report.md'
