SHELL := /bin/sh

.PHONY: help check test lint build start stop

help:
	@printf '%s\n' \
		'Available targets:' \
		'  check  Validate the monorepo structure' \
		'  test   Validate the initialization state' \
		'  lint   Report that no linter is configured' \
		'  build  Report that no build is configured' \
		'  start  Report that no services are configured' \
		'  stop   Report that no services are configured'

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

test: check

lint:
	@printf '%s\n' 'No linter is configured.'

build:
	@printf '%s\n' 'No build is configured.'

start:
	@printf '%s\n' 'No services are configured.'

stop:
	@printf '%s\n' 'No services are configured.'
