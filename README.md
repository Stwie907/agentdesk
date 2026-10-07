# AgentDesk

AgentDesk is a local Agent workbench built with FastAPI, React, TypeScript,
SQLite, and Ollama. Runtime V4 supports execution plans, tool permissions,
structured traces, snapshots, and replay. The workbench supports task submission,
execution history, filters, pagination, cancellation, retry, and automatic refresh.

Run the backend with the default Ollama provider, or explicitly enable Mock mode
for an offline demonstration without a local model. Mock mode uses fixed planning
rules and clearly marked simulated chat replies. Calculator demo tasks still run
the real Calculator tool through the normal execution pipeline.

See [backend setup and demo instructions](backend/README.md) and
[frontend setup](frontend/README.md).

## Repository layout

- `backend/` - FastAPI APIs, Agent runtime, persistence, and tests.
- `frontend/` - React, TypeScript, and Vite execution workbench.
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

The current Compose configuration is a service foundation. Local development
instructions cover LLM configuration; container environment wiring and deployment
are separate follow-up work. RAG and MCP integrations are not implemented yet.
