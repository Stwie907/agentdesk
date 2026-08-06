# AgentDesk

AgentDesk is organized as a minimal monorepo with backend and frontend service
foundations. It contains no business logic, agents, RAG implementation, or MCP
implementation.

## Repository layout

- `backend/` - FastAPI backend service foundation.
- `frontend/` - React, TypeScript, and Vite frontend foundation.
- `mcp-server/` — reserved for MCP server code.
- `evaluation/` — reserved for evaluation assets.
- `docs/` — project documentation.
- `deployment/` — deployment configuration.

## Commands

- `make check` validates the monorepo structure.
- `make test` runs backend and frontend tests.
- `make build` builds service containers.
- `make start` starts service containers.
- `make stop` stops service containers.
