SHELL := /bin/sh

.PHONY: help check test lint build start stop demo demo-check evaluate evaluation-test mcp-check mcp-test mcp-runtime-check mcp-tracking-check mcp-ticket-check memory-check conversation-check

help:
	@printf '%s\n' \
		'Available targets:' \
		'  check  Validate the monorepo structure' \
		'  test   Run backend and frontend tests' \
		'  lint   Report that no linter is configured' \
		'  build  Build service containers' \
		'  start  Start service containers' \
		'  stop   Stop service containers, retaining demo data' \
		'  demo   Build and start the Mock demo with a Demo Agent' \
		'  demo-check  Check the workbench, Mock tasks, snapshots, and replay' \
		'  evaluate  Evaluate the running Mock demo and save reports' \
		'  evaluation-test  Test the evaluator without a running backend' \
		'  mcp-check  Verify standalone business tools over stdio' \
		'  mcp-test  Run business data and MCP protocol tests in Docker'
	@printf '%s\n' '  mcp-runtime-check  Check MCP order tasks and replay through the running Mock API'
	@printf '%s\n' '  mcp-tracking-check  Check MCP shipment tasks and replay through the running Mock API'
	@printf '%s\n' '  mcp-ticket-check  Check MCP ticket writes, deduplication, permissions, and replay'
	@printf '%s\n' '  memory-check  Check Agent memory storage, scope, deletion, and Runtime retrieval'
	@printf '%s\n' '  conversation-check  Check multi-turn chat, automatic memory, and Agent scope'

check:
	@test -f README.md
	@test -f Makefile
	@test -f docker-compose.yml
	@test -f docker-compose.mock.yml
	@test -f .env.example
	@test -f .github/workflows/ci.yml
	@test -d backend
	@test -d frontend
	@test -d mcp-server
	@test -d evaluation
	@test -d docs
	@test -d deployment
	@test -f backend/app/main.py
	@test -f backend/app/config.py
	@test -f backend/app/seed_demo.py
	@test -f backend/app/check_demo.py
	@test -f backend/app/api/health.py
	@test -f backend/tests/test_health.py
	@test -f backend/requirements.txt
	@test -f backend/Dockerfile
	@test -f backend/.dockerignore
	@test -f backend/README.md
	@test -f frontend/src/main.tsx
	@test -f frontend/src/App.tsx
	@test -d frontend/src/components
	@test -d frontend/src/pages
	@test -d frontend/tests
	@test -f frontend/package.json
	@test -f frontend/package-lock.json
	@test -f frontend/vite.config.ts
	@test -f frontend/Dockerfile
	@test -f frontend/nginx.conf
	@test -f frontend/README.md
	@test -f deployment/start-demo.sh
	@test -f docs/docker-compose-demo.md
	@test -f deployment/evaluate-demo.sh
	@test -f evaluation/__init__.py
	@test -f evaluation/dataset.json
	@test -f evaluation/run.py
	@test -f evaluation/tests/test_run.py
	@test -f evaluation/README.md
	@test -f deployment/check-mcp.sh
	@test -f mcp-server/server.py
	@test -f mcp-server/orders.py
	@test -f mcp-server/check.py
	@test -f mcp-server/fixtures.json
	@test -f mcp-server/requirements.txt
	@test -f mcp-server/Dockerfile
	@test -f mcp-server/.dockerignore
	@test -f mcp-server/README.md
	@test -f mcp-server/tests/test_orders.py
	@test -f mcp-server/client.py
	@test -f mcp-server/tests/test_client.py
	@test -f backend/app/tools/mcp_order.py
	@test -f backend/app/runtime/trace_details.py
	@test -f backend/app/check_mcp_runtime.py
	@test -f backend/tests/test_mcp_order.py
	@test -f backend/tests/test_mcp_runtime_api.py
	@test -f .dockerignore
	@test -f mcp-server/tracking.py
	@test -f mcp-server/tracking-fixtures.json
	@test -f mcp-server/tests/test_tracking.py
	@test -f backend/app/tools/mcp_tracking.py
	@test -f backend/app/check_mcp_tracking.py
	@test -f backend/tests/test_mcp_tracking.py
	@test -f backend/tests/test_mcp_tracking_api.py
	@test -f mcp-server/tickets.py
	@test -f mcp-server/tests/test_tickets.py
	@test -f backend/app/tools/mcp_ticket.py
	@test -f backend/app/check_mcp_ticket.py
	@test -f backend/tests/test_mcp_ticket.py
	@test -f backend/tests/test_mcp_ticket_api.py
	@test -f backend/app/check_memory.py
	@test -f backend/tests/test_memory_api_contract.py
	@test -f frontend/src/components/MemoryPanel.tsx
	@test -f frontend/src/api/memories.ts
	@test -f frontend/src/types/memories.ts
	@test -f frontend/tests/MemoryPanel.test.tsx
	@test -f frontend/tests/MemorySelection.test.tsx
	@test -f backend/app/check_conversation.py
	@test -f backend/tests/test_conversation_api_contract.py
	@test -f frontend/src/components/ConversationPanel.tsx
	@test -f frontend/src/api/conversations.ts
	@test -f frontend/src/types/conversations.ts
	@test -f frontend/tests/ConversationPanel.test.tsx
	@test -f frontend/tests/ConversationFlow.test.tsx

test: check
	@python -m unittest discover -s evaluation/tests -v
	@cd backend && python -m pytest
	@cd frontend && npm test

lint:
	@printf '%s\n' 'No linter is configured.'

build:
	docker compose build backend frontend

start:
	docker compose up --detach --wait --wait-timeout 180 backend frontend

stop:
	docker compose down

demo:
	sh deployment/start-demo.sh

demo-check:
	docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
		python -m app.check_demo --base-url http://frontend

evaluate:
	sh deployment/evaluate-demo.sh

evaluation-test:
	python -m unittest discover -s evaluation/tests -v

mcp-check:
	sh deployment/check-mcp.sh

mcp-test:
	docker compose run --build --rm --no-deps -T mcp-check \
		python -m unittest discover -s tests -v

mcp-runtime-check:
	docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
		python -m app.check_mcp_runtime --base-url http://frontend

mcp-tracking-check:
	docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
		python -m app.check_mcp_tracking --base-url http://frontend

mcp-ticket-check:
	docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
		python -m app.check_mcp_ticket --base-url http://frontend

memory-check:
	docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
		python -m app.check_memory --base-url http://frontend

conversation-check:
	docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
		python -m app.check_conversation --base-url http://frontend
