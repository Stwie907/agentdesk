SHELL := /bin/sh

.PHONY: help check test lint build start stop

help:
	@printf '%s\n' \
		'Available targets:' \
		'  check  Validate the monorepo structure' \
		'  test   Run backend and frontend tests' \
		'  lint   Report that no linter is configured' \
		'  build  Build service containers' \
		'  start  Start service containers' \
		'  stop   Stop service containers'

check:
	@test -f README.md
	@test -f Makefile
	@test -f docker-compose.yml
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
	@test -f backend/app/api/health.py
	@test -f backend/tests/test_health.py
	@test -f backend/requirements.txt
	@test -f backend/Dockerfile
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
	@test -f frontend/README.md

test: check
	@cd backend && python -m pytest
	@cd frontend && npm test

lint:
	@printf '%s\n' 'No linter is configured.'

build:
	docker compose build backend frontend

start:
	docker compose up --detach backend frontend

stop:
	docker compose down
