# AgentDesk Backend

FastAPI backend for AgentDesk. Runtime V4 plans and executes tasks with tool
permissions, stores execution traces and snapshots, and replays stored plans.
Ollama is the default provider. Explicit Mock mode supports offline demonstrations.

## Setup

The repository CI uses Python 3.11. From `backend/`:

```sh
python -m venv .venv
```

Activate with `source .venv/Scripts/activate` in Windows Git Bash, or
`. .venv/bin/activate` on Linux/macOS. Then install dependencies:

```sh
python -m pip install -r requirements.txt
```

The backend dependencies are unchanged. MCP tools use a separate SDK environment;
see the native MCP setup below.

## LLM configuration

Export settings in the terminal that starts Uvicorn. The backend reads process
environment variables. Root `.env.example` documents defaults; native Uvicorn
does not load a `.env` file automatically. Docker Compose separately reads a root
`.env` file for the variables mapped by its service configuration.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | Select `ollama` or `mock`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL without `/api/generate`. |
| `OLLAMA_PLANNER_MODEL` | `qwen2.5:7b` | Model for both Planner entry points. |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Positive finite timeout for each model request. |
| `DATABASE_URL` | `sqlite:///./agentdesk.db` | Database URL; SQLite paths are relative to the working directory. |

Final Ollama replies use the model stored on the selected Agent. The planner model
setting does not override Agent model selections. Unsupported provider names,
invalid URLs, blank planner models, and nonpositive/nonfinite timeouts raise errors
when the runtime reads settings.

### Ollama mode

Start Ollama with the planner model and the selected Agent's model available.
From `backend/`, using Git Bash or a Unix shell:

```sh
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_PLANNER_MODEL=qwen2.5:7b
export OLLAMA_TIMEOUT_SECONDS=120
python -m uvicorn app.main:app --reload
```

Connection, timeout, HTTP, and malformed-response errors remain failures. Ollama
errors never silently select Mock mode. The existing worker retry policy applies
to connection failures and timeouts.

### Mock mode

No local model or API key is required. From `backend/`, using Git Bash or a Unix shell:

```sh
export LLM_PROVIDER=mock
python -m uvicorn app.main:app --reload
```

In PowerShell, set `$env:LLM_PROVIDER = "mock"` before running Uvicorn.
Restart the backend after changing shell settings. Return to normal operation
by setting `LLM_PROVIDER=ollama` and restarting the backend.

Mock mode makes no LLM HTTP requests. Its rule-based planner supports one binary
arithmetic operation with signed numbers, optional decimal notation, and `+`, `-`,
`*`, or `/`. Inputs may start with `计算` or `Calculate`. It respects Calculator
permissions. It also recognizes `Get order DEMO-1001` and `查询订单DEMO-1001`
when the Agent allows `get_order`; these call the real MCP order server.
`Track order DEMO-TRACK-1001` and `查询物流DEMO-TRACK-1002` use the real tracking
tool when the Agent allows `track_order`.
`Create ticket Demo parcel is delayed.` and `创建工单示例订单需要帮助。` use the
local ticket write tool when the Agent allows `create_ticket`.
Other input produces a no-tool plan and a fixed reply. Mock mode does
not perform general reasoning, datetime selection, or multi-step natural-language
planning.

| Input | Requirement | Result |
| --- | --- | --- |
| `计算40+2` | Agent allows `calculator`. | Real Calculator output: `42`. |
| `Calculate 40 + 2` | Agent allows `calculator`. | Real Calculator output: `42`. |
| `Hello AgentDesk` | Any Agent. | `[MOCK] AgentDesk demo response. No language model was called.` |
| `计算40+2` | Calculator not allowed. | Fixed `[MOCK]` reply; no tool runs. |
| `Get order DEMO-1001` | Agent allows `get_order`; MCP environment installed. | JSON order with `source: demo_fixture` and status `shipped`. |
| `查询订单DEMO-1002` | Agent allows `get_order`; MCP environment installed. | JSON order with status `processing`. |
| `Get order DEMO-9999` | Agent allows `get_order`. | Failed execution with `tool_execution_error`. |
| `Get order DEMO-1001` | Order tool not allowed. | Fixed `[MOCK]` reply; no MCP call. |
| `Track order DEMO-TRACK-1001` | Agent allows `track_order`; MCP environment installed. | Synthetic JSON shipment, `in_transit`, and 3 UTC events. |
| `查询物流DEMO-TRACK-1002` | Agent allows `track_order`; MCP environment installed. | Synthetic JSON shipment, `label_created`, and 1 event. |
| `Track order DEMO-TRACK-9999` | Agent allows `track_order`. | Failed execution with `tool_execution_error`. |
| `Create ticket Demo parcel is delayed.` | Agent allows `create_ticket`. | Persistent synthetic JSON ticket with `status: open`. |
| Repeat the same ticket problem | Same local ticket store. | Original ticket ID and creation timestamp. |
| `Create ticket Demo parcel is delayed.` | Ticket write permission absent. | Fixed `[MOCK]` reply; no MCP write. |

Calculator outputs are real tool results. The Inspector's `plan_started` trace
contains `provider=mock; planner=demo_rules`. Simulated chat replies carry the
`[MOCK]` prefix. Execution history, traces, and snapshots use the existing Runtime
V4 pipeline. Calculator replay re-executes the stored tool plan and returns `42`
without calling the planner or a model again.

## Native MCP setup

Keep MCP dependencies separate because the SDK and backend have different
`httpx2` requirements. From the repository root, with Python 3.11 or newer:

```sh
python -m venv mcp-server/.venv
mcp-server/.venv/Scripts/python.exe -m pip install -r mcp-server/requirements.txt
```

Linux/macOS uses `mcp-server/.venv/bin/python`. The backend automatically finds
this environment; the backend's own virtual environment stays active. For another
location, export `MCP_PYTHON` as its absolute Python executable path in the terminal
that starts Uvicorn. `MCP_TIMEOUT_SECONDS` defaults to 30 and must be positive and
finite. Docker supplies the isolated SDK environment automatically.

Create an Agent with `allowed_tools: ["get_order"]`, or run `python -m app.seed_demo`
to create `MCP Order Agent`. A single order-tool step returns validated JSON
directly, without a model rewriting its values. Ollama receives tool metadata and
structured argument examples; Mock uses fixed lookup rules.

The adapter calls a fixed local MCP client with stdin JSON rather than shell
commands. The client discovers the server's tool, validates its contract and typed
response, and closes the server after each call. Errors use the existing tool
failure contract. Normal and replay Trace include arguments/results. Replay uses
the saved plan, current permissions, and current fixtures; it does not reuse cached
output. The first adapter starts a client/server pair per call. Pooling and
configurable remote MCP servers remain future work.

Tracking uses the same fixed client and isolated SDK environment. Create an Agent
with `allowed_tools: ["track_order"]`, or select the seeded `MCP Logistics Agent`.
An order permission does not grant tracking permission. Validated shipment JSON
returns directly and includes `source: demo_fixture`, carrier, linked order,
status, and ordered UTC events. The backend does not read shipment fixtures.
Tracking uses existing planner metadata recovery, Trace, Snapshot, and Replay;
the Agent runner and replay executor require no tool-specific changes.

Ticket creation uses the same isolated client with its own write contract. Select
`MCP Ticket Agent`, or explicitly grant `allowed_tools: ["create_ticket"]`.
Problems must be non-blank strings of at most 2000 characters. The MCP server
stores tickets in a dedicated SQLite database and reuses the same trimmed problem
atomically, including across subprocesses and replay. Returned JSON contains
`source: demo_ticket_store`, `ticket_id`, `problem`, `status: open`, and UTC
`created_at`. The backend returns it directly and does not access the ticket
database. Order/tracking permissions do not grant write permission. The Executor
checks current permissions before a normal call or replay; failures retain the
existing runtime error, trace, and snapshot behavior.

Native MCP tickets default to `mcp-server/data/tickets.db`. An optional
`MCP_TICKET_DB` must be an absolute path to a dedicated SQLite file; export it in
the Uvicorn terminal. Docker sets `/data/mcp-tickets.db` in the existing data
volume. Ticket persistence is separate from the backend's database and requires
no Alembic change. Store-level deduplication is a synthetic demo contract.

## Workbench demo

The backend listens on `http://localhost:8000`. Open `http://localhost:8000/docs`
for Swagger. Use an existing Agent, or create resources in a fresh database:

1. `POST /users`: provide a unique `username` and `email`; record the returned ID.
2. `POST /projects`: provide `name` and set `owner_id` to that user ID; record the project ID.
3. `POST /agents`: provide `name`, that `project_id`, `model: "qwen2.5:7b"`, and
   `allowed_tools: ["calculator"]`.

Start the frontend in another terminal from `frontend/`:

```sh
npm ci
npm run dev
```

At `http://localhost:5173`, select the Agent and submit `计算40+2`. Confirm
`completed`, output `42`, the Mock marker in the trace, and a stored snapshot.
Submit `Hello AgentDesk` to see the explicitly marked fixed reply.

## Persistent Agent memory

The workbench uses the existing SQLite memory table and service policy:

| Endpoint | Behavior |
| --- | --- |
| `POST /memories` | Existing positive integer `agent_id`; string content trimmed to 1–2000 characters. Returns a new or reused record. |
| `GET /memories/{agent_id}` | Existing positive Agent ID; ordered records for that Agent only. An unknown Agent returns 404. |
| `DELETE /memories/item/{memory_id}?agent_id={agent_id}` | Removes the record only if it belongs to the supplied Agent; a mismatch or absent record returns 404. |

Invalid input returns 422. Exact duplicate content reuses its ID/timestamp.
Canonical `User's name is ...` writes replace an earlier name memory using the
same policy as automatic extraction. Old clients may omit the delete scope;
the frontend always supplies it. These APIs do not implement authentication.

Internal conversation extraction, existing saved content, keyword retrieval,
and Ollama prompt injection retain their current behavior. The manual API limit
does not truncate legacy or automatically extracted records. Memory retrieval
events remain available in `GET /execution-logs/{execution_id}`. Mock always
returns its fixed marked reply, even when relevant context was loaded.

Run `python -m app.check_memory --base-url http://frontend` from the Mock backend
container. After a successful initial check and service recreation, add
`--verify-persistence`. It validates the stored marker before writing, compares
the original ID/content/timestamp, and cleans up its temporary scope-test record.
The existing application data volume holds memories; no migration or new
dependency is required. Redis/PostgreSQL adapters and semantic retrieval remain
future work.

## Conversation workbench APIs

`POST /conversations` requires an existing positive integer Agent ID and a
trimmed, non-blank title of at most 200 characters. `GET /conversations?agent_id=ID`
returns ordered conversations for that Agent. The existing unfiltered list
remains available to older clients.

Conversation reads, message reads/writes, chat, and deletion accept an optional
positive `agent_id` query. A mismatch or missing conversation returns 404 before
saving messages, extracting memory, or executing Runtime. The workbench always
includes its selected Agent ID. This scope check adds no authentication or
multi-user authorization.

`POST /conversations/{id}/chat?agent_id=ID` requires trimmed content of 1 to 4000
characters. It uses the existing conversation service: prior history is loaded
before the current user message, explicit facts are extracted, Runtime creates
an execution, and the assistant output is saved. Messages sort by creation time
and ID. Existing English/Chinese name and preference rules now skip recognizable
questions and hypotheticals instead of storing question words as facts. This
remains a limited deterministic extractor, not general language understanding.

Run `python -m app.check_conversation --base-url http://frontend` in Mock mode.
Its six scenarios cover scoped conversations, rejected writes, two saved turns,
automatic memory, Runtime history/retrieval, and snapshots. It reuses one demo
conversation and preference; subsequent runs append two turns. After recreation,
add `--verify-persistence`: conversation, transcript, and extracted memory must
already exist before new chat writes. No schema migration or dependency is added.

## Health and tests

`GET /health` continues to return `{"status": "ok"}`.

From `backend/`:

```sh
python -m pytest
```

Tests isolate the LLM environment and select providers explicitly. A shell setting
of `LLM_PROVIDER=mock` does not change the existing Ollama contract tests. The suite
does not require a live model. Real MCP API tests run when the separate environment
is available (or `MCP_PYTHON` is set); otherwise they report explicit skips.
CI installs the separate environment and runs these tests.

## Containers

From the repository root, start the complete Mock workbench with:

```sh
sh deployment/start-demo.sh
```

The container stores SQLite at `/data/agentdesk.db` in a named volume. Its health
check uses `/health`; it does not require Ollama. The Mock override explicitly
sets `LLM_PROVIDER=mock`. The base Compose file defaults to Ollama and uses
`COMPOSE_OLLAMA_BASE_URL` for requests to a host model server.

The startup script runs `python -m app.seed_demo` inside the backend. This command
reuses the matching demo User, Project, and Agent on repeated runs. It creates a
`Demo Agent` with Calculator permission and `qwen2.5:7b` as its normal Ollama
model. It preserves existing Agent settings and rejects a conflicting demo User
identity rather than modifying that User.
It also creates a separate `MCP Order Agent` with `get_order` permission and
preserves that Agent's settings on later initializer runs.
It also creates `MCP Logistics Agent` with only `track_order` permission. Existing
calculator, order, and logistics Agent settings are preserved on repeated runs.
`MCP Ticket Agent` is created with only `create_ticket` permission; its existing
settings are also preserved on repeated initializer runs.

The smoke command `python -m app.check_demo --base-url http://frontend` runs
inside the Mock backend container and checks the built workbench, API proxy,
Calculator task, marked reply, trace, snapshots, and replay.
`python -m app.check_mcp_runtime --base-url http://frontend` separately checks
order tasks, permissions, failed lookups, MCP traces, snapshots, and linked replay.
`python -m app.check_mcp_tracking --base-url http://frontend` performs the equivalent
five-scenario logistics acceptance check through the Mock API.
`python -m app.check_mcp_ticket --base-url http://frontend` checks five ticket
scenarios. After the initial check and service recreation, add
`--verify-persistence` to confirm ticket IDs/content and execution history survive.
`python -m app.check_memory --base-url http://frontend` checks six memory scenarios;
its persistence option fails if the original demo memory was lost after restart.

The backend image now builds from the repository root to include the separate MCP
environment. For a manual build, run `docker build -f backend/Dockerfile .` from
the repository root.

See [the Docker Compose guide](../docs/docker-compose-demo.md) for complete
commands, switching providers, persistence verification, and troubleshooting.
