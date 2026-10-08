# AgentDesk

AgentDesk is a local Agent workbench built with FastAPI, React, TypeScript,
SQLite, and Ollama. Runtime V4 supports execution plans, tool permissions,
structured traces, snapshots, and replay. The workbench supports task submission,
execution history, filters, pagination, cancellation, retry, and automatic refresh.

## Quick Mock demo

Start Docker with Linux containers and Docker Compose v2 available. From the
repository root, using Windows Git Bash or a Unix shell:

```sh
sh deployment/start-demo.sh
```

The script builds both services, waits for healthy containers, and creates a
calculator-enabled `Demo Agent`. It explicitly selects Mock mode; a language
model and API key are not needed. The initial build downloads container images
and dependencies. Once built, Mock task execution makes no LLM requests.

Open [the workbench](http://localhost:5173), select `Demo Agent`, and submit:

- `Calculate 40 + 2`: the real Calculator returns `42`.
- `Hello AgentDesk`: a fixed reply starts with `[MOCK]`.

The Inspector shows traces and snapshots. Replay the Calculator execution to
create a linked execution with output `42`. Run `make demo-check` for an
automated check of the built workbench, API proxy, tasks, snapshots, and replay.

SQLite is stored in a Docker named volume. `docker compose down` stops the
services while retaining this data. Container data is separate from the native
backend's `backend/agentdesk.db`.

See [Docker Compose instructions](docs/docker-compose-demo.md),
[backend setup](backend/README.md), and [frontend setup](frontend/README.md).

## Runtime evaluation

After starting the Mock demo, run this from the repository root:

```sh
sh deployment/evaluate-demo.sh
```

The evaluator uses Python inside a temporary Docker container. It runs eight
fixed Runtime V4 cases through the frontend API proxy and writes
`evaluation/reports/report.json` and `evaluation/reports/report.md` on your
computer. Cases check outputs, tool selection, trace order, snapshots, and replay.
Reports include execution success rate, exact output accuracy, overall pass
rate, and POST latency. A failed check makes the command exit with status 1.

This deterministic suite evaluates the current runtime. Router/RAG accuracy,
hallucination scoring, and token accounting remain future evaluation work.
See [the evaluation guide](evaluation/README.md) for metrics and troubleshooting.

## Repository layout

- `backend/`: FastAPI APIs, Agent runtime, demo commands, persistence, and tests.
- `frontend/`: React, TypeScript, and Vite execution workbench with Nginx hosting.
- `docs/`: project and deployment documentation.
- `deployment/`: the portable Mock demo startup script.
- `mcp-server/`: reserved for MCP server code.
- `evaluation/`: a fixed Mock dataset, HTTP evaluator, reports, and evaluator tests.

RAG and MCP integrations are not implemented yet.

## Commands

| Command | Purpose |
| --- | --- |
| `make check` | Validate the monorepo structure. |
| `make test` | Run backend and frontend tests using installed local dependencies. |
| `make build` | Build service containers. |
| `make start` | Start the base Compose services and wait for health; Ollama is the default. |
| `make demo` | Build, start, and seed the explicit Mock demo. |
| `make demo-check` | Check the running Mock demo through the frontend proxy. |
| `make evaluate` | Evaluate the running Mock demo and save JSON/Markdown reports. |
| `make evaluation-test` | Test evaluator scoring and error handling without Docker. |
| `make stop` | Stop services while retaining the data volume. |

The application keeps Ollama as its default provider. The Mock Compose override
selects deterministic demo behavior. Use the Docker guide to switch an existing
demo to a local Ollama server without deleting its data.
