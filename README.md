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
calculator-enabled `Demo Agent`, `MCP Order Agent`, and `MCP Logistics Agent`.
It explicitly selects Mock mode; a language
model and API key are not needed. The initial build downloads container images
and dependencies. Once built, Mock task execution makes no LLM requests.

Open [the workbench](http://localhost:5173), select `Demo Agent`, and submit:

- `Calculate 40 + 2`: the real Calculator returns `42`.
- `Hello AgentDesk`: a fixed reply starts with `[MOCK]`.

The Inspector shows traces and snapshots. Replay the Calculator execution to
create a linked execution with output `42`. Run `make demo-check` for an
automated check of the built workbench, API proxy, tasks, snapshots, and replay.

Select `MCP Order Agent` and submit `Get order DEMO-1001` or `查询订单DEMO-1001`.
The real MCP client discovers and calls the independent stdio order server.
The response is JSON with `source: demo_fixture`, status `shipped`, and total
`129.00`. Trace shows arguments/results; Snapshot stores the plan and output.
Replay executes the saved MCP plan using current Agent permissions and server data.
`Get order DEMO-9999` creates a failed execution with a visible tool error.

Run the integrated API check after starting the demo:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_runtime --base-url http://frontend
```

Equivalent: `make mcp-runtime-check`. The initializer preserves existing Agent
permissions and only gives `get_order` permission to the new order demo Agent.

Select `MCP Logistics Agent` for `Track order DEMO-TRACK-1001` or
`查询物流DEMO-TRACK-1002`. The real `track_order(tracking_no)` MCP tool returns
JSON with a synthetic carrier, order id, shipment status, and a UTC event timeline.
It requires a tracking number rather than an order id. Every response is marked
`source: demo_fixture`; no carrier or live logistics service is contacted.

| Tracking number | Linked demo order | Status | Timeline events |
| --- | --- | --- | --- |
| DEMO-TRACK-1001 | DEMO-1001 | in_transit | 3 |
| DEMO-TRACK-1002 | DEMO-1002 | label_created | 1 |

`Track order DEMO-TRACK-9999` creates a failed execution with a visible tool error.
Tracking Trace, Snapshot, Replay, and current permission checks use the same
Runtime pipeline as order lookup. Run the logistics API check after startup:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_tracking --base-url http://frontend
```

Equivalent: `make mcp-tracking-check`. Existing Agent permissions are preserved.

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

## Local MCP business tools

Check the standalone MCP server independently with Docker:

```sh
sh deployment/check-mcp.sh
```

The official MCP Python SDK launches the independent server over stdio,
discovers `get_order(order_id)` and `track_order(tracking_no)`, and runs 16 checks
covering structured replies and tool errors.
It uses synthetic local fixtures marked `source: demo_fixture`, requires no
model or external business API, and has no published port. The optional MCP
check container is removed after the command completes.

Run `make mcp-test` for order/tracking data, SDK, and real subprocess protocol tests.
See [the MCP guide](mcp-server/README.md) for runtime integration and native setup.
The next business-tool milestone is `create_ticket(problem)`.

## Repository layout

- `backend/`: FastAPI APIs, Agent runtime, demo commands, persistence, and tests.
- `frontend/`: React, TypeScript, and Vite execution workbench with Nginx hosting.
- `docs/`: project and deployment documentation.
- `deployment/`: the portable Mock demo startup script.
- `mcp-server/`: independent stdio order server, demo fixtures, protocol check, and tests.
- `evaluation/`: a fixed Mock dataset, HTTP evaluator, reports, and evaluator tests.

RAG and additional MCP business tools remain future milestones.

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
| `make mcp-check` | Verify both standalone MCP business tools in Docker. |
| `make mcp-test` | Run order/tracking data and MCP protocol tests in Docker. |
| `make mcp-runtime-check` | Check order tasks, permissions, traces, errors, snapshots, and replay through the running Mock API. |
| `make mcp-tracking-check` | Check shipment tasks, permissions, traces, errors, snapshots, and replay through the running Mock API. |
| `make stop` | Stop services while retaining the data volume. |

The application keeps Ollama as its default provider. The Mock Compose override
selects deterministic demo behavior. Use the Docker guide to switch an existing
demo to a local Ollama server without deleting its data.
