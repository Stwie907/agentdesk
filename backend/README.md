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
| `GET /memories/{agent_id}/search?query=Python&limit=5` | Read-only ranked matches for the selected Agent, with overlap scores and matched terms. |
| `PATCH /memories/item/{memory_id}?agent_id={agent_id}` | Required positive Agent scope; validated content and original content; preserves identity/time. |
| `DELETE /memories/item/{memory_id}?agent_id={agent_id}` | Removes the record only if it belongs to the supplied Agent; a mismatch or absent record returns 404. |

Invalid input returns 422. Exact duplicate content reuses its ID/timestamp.
Canonical `User's name is ...` writes replace an earlier name memory using the
same policy as automatic extraction. Old clients may omit the delete scope;
the frontend always supplies it. These APIs do not implement authentication.

Internal conversation extraction, existing saved content, and Ollama prompt
injection retain their current behavior. The manual API limit
does not truncate legacy or automatically extracted records. Memory retrieval
events remain available in `GET /execution-logs/{execution_id}`. Mock always
returns its fixed marked reply, even when relevant context was loaded.

Run `python -m app.check_memory --base-url http://frontend` from the Mock backend
container. After a successful initial check and service recreation, add
`--verify-persistence`. It validates the stored marker before writing, compares
the original ID/content/timestamp, and cleans up its temporary scope-test record.
The existing application data volume holds memories; no migration or new
dependency is required. Persistent vector indexing and Redis/PostgreSQL adapters
remain future work.

## Shared user memory

The new `user_memories` table belongs to `User.id`. An Agent resolves its owner
through `Agent.project_id -> Project.owner_id`; all that user's Agents share these
records, including Agents in separate Projects. Automatic conversation extraction
continues to save Agent-specific memories.

| Method | Endpoint | Scope and payload |
| --- | --- | --- |
| GET | `/user-memories/for-agent/{agent_id}` | Returns `agent_id`, `user_id`, `username`, and `memories`. |
| POST | `/user-memories/for-agent/{agent_id}` | Requires `{ "user_id": 1, "content": "I prefer SQLite." }`; owner must match the Agent. |
| GET | `/user-memories/for-agent/{agent_id}/search?query=SQLite&limit=5` | Query 1–500 characters; limit 1–20; owner-scoped matches. |
| PATCH | `/user-memories/item/{memory_id}?agent_id=1&user_id=1` | Requires `content` and original `expected_content`; retains ID, owner, and creation time. |
| DELETE | `/user-memories/item/{memory_id}?agent_id=1&user_id=1` | Deletes one shared row for all Agents of its owner. |

Content is a strict string of 1–2000 trimmed characters; extra body fields are
rejected. Invalid scope/content returns 422; unknown Agent/memory or mismatched
owner returns 404. Both owner and Agent are required for writes so a stale UI
cannot silently write to a reassigned Project's new owner. This is data scoping;
it does not add authentication to the existing local workbench.

Uniqueness on `(user_id, content_key)` protects parallel duplicate saves. Exact
duplicates retain ID/time. Canonical `User's name is ...` records allow one shared
name per owner: edit it explicitly. Duplicate/name collisions and stale edits
return 409. Conditional SQL protects changes after the initial read; failures roll back.

Search and Runtime share `memory_retrieval.rank_memory_rows`. Runtime includes
up to five matching shared rows and five Agent rows, with separate source labels
when shared context exists. Without shared matches, the old Agent context format
is preserved. Scores remain keyword counts, not semantic similarity.

Demo initialization/startup adds the table using `Base.metadata.create_all`.
For an Alembic-managed database, `alembic upgrade head` applies revision
`c84f31a920de` after `d09aa76d1cdb`. It preserves all existing application data
and adopts a correctly shaped runtime-created table while repairing missing
indexes. Schema drift is rejected. The initial Alembic migration must not be run
blindly on an unversioned demo database whose tables already exist. Downgrading
this revision removes only the shared-memory table and its records.

Run `python -m app.check_user_memory --base-url http://frontend` in the Mock
backend. Eight scenarios retain two markers and one synthetic isolation
User/Project/Agent. A checkpoint beside SQLite records both full rows and the
original execution/trace/snapshot. After recreation, add `--verify-persistence`;
missing or changed fixtures/checkpoints fail before replacement writes. Repeated
checks reuse the same isolation fixture and keep the original checkpoint.
`--state-file` optionally selects another checkpoint path.

### Edit a memory

`PATCH /memories/item/{memory_id}?agent_id=ID` requires a positive Agent scope
and accepts only `content` and `expected_content`:

```json
{"content": "User likes Rust.", "expected_content": "User likes Python."}
```

`content` is a strict string trimmed to 1–2000 characters. `expected_content`
is a strict string containing the original saved content verbatim, including
legacy content longer than the manual write limit. Missing, invalid, or extra
fields return 422. A missing memory or mismatched Agent returns 404. Stale content,
a duplicate within the same Agent, or introducing a second canonical name record
returns 409. Other Agents do not participate in the duplicate/name checks.

The conditional SQL update checks ID, Agent, and original content together.
Commit failure rolls back the change. The API preserves ID and creation time,
changes only the selected record, and creates no execution or conversation.
Existing create/extraction duplicate and name replacement policies remain intact.
Runtime and preview read the updated content on their next request.

Run `python -m app.check_memory_editing --base-url http://frontend` from the Mock
backend. It retains one edited marker and a versioned acceptance checkpoint in
`memory-edit-acceptance.json` beside the configured SQLite database. The optional
`--state-file` selects another local checkpoint. After restarting, add
`--verify-persistence`: missing/changed records or checkpoints fail before any
replacement write. This file validates demo acceptance; it is not an additional
application memory store. The check removes its transient memory and creates a
separate Mock execution to verify Runtime retrieval and its snapshot.

### Shared keyword retrieval preview

`GET /memories/{agent_id}/search` requires an existing positive Agent ID and a
trimmed, non-blank `query` of at most 500 characters. `limit` defaults to 5 and
accepts integers from 1 to 20. Invalid inputs return 422; an unknown Agent returns
404. The query cap keeps percent-encoded Chinese queries within the frontend
proxy's request-line limit. A valid query with no relevant terms returns 200
with an empty `results` list.

The response contains `agent_id`, the trimmed `query`, the requested `limit`,
and ordered `results`. Each result includes the existing `memory` record,
an integer `score`, and unique `matched_terms`. Score is the number of distinct
query/content terms in common, not a probability or semantic similarity. Results
sort by score descending, then Memory ID descending; zero-score records are
excluded. Repeating query terms does not increase their weight.

`memory_retrieval.rank_agent_memories` is shared by this API and Runtime's
`retrieve_relevant_memories`. Normalization uses Unicode NFKC and case folding.
English words retain possessives and technical tokens such as `C++`, `C#`, and
`Node.js`; straight and curly apostrophes match the same token.
Chinese text uses overlapping two-character fragments after filtering common
stop terms. A meaningful single Chinese character is matched literally.
Matching does not translate between languages or infer semantic relationships.
Runtime retains its default limit of 5 and its internal blank-query fallback;
the public search API rejects blank queries. Selecting a preview limit never
changes Runtime settings.

Search performs no write, message extraction, execution, or model call. Existing
duplicate/name-memory policies and table definitions are retained. Agent scope
is not an authentication boundary.

Run `python -m app.check_memory_search --base-url http://frontend` in Mock mode
for six HTTP scenarios. The command deliberately prepares three stable demo
memories, checks that searches leave memory/history/conversations unchanged,
cleans up its temporary record, and separately submits one Runtime probe.
After recreation, `--verify-persistence` requires all three original records
before any write and checks duplicate saves retain their IDs and timestamps.

## Local semantic memory APIs

Keyword endpoints retain their original response format. The optional endpoints
`GET /memories/{agent_id}/semantic-search` and
`GET /user-memories/for-agent/{agent_id}/semantic-search` accept:

| Parameter | Meaning |
| --- | --- |
| `query` | Required, 1–500 characters; whitespace-only queries are rejected. |
| `limit` | 1–20, default 5. |
| `min_similarity` | Optional finite value from 0 to 1; defaults to server configuration. |

Responses include `mode: semantic`, `provider`, `model`, `runtime_mode`,
`min_similarity`, and ranked `results`. Each result has `memory` and a positive
`similarity` up to 1. Similarities are rounded to six decimals and sorted
descending, with newer row IDs first on ties. Shared results also identify the
resolved `user_id`. Only scoped rows enter the embedding request; another Agent's
private rows and another user's shared rows are excluded beforehand.

Configuration:

| Variable | Default |
| --- | --- |
| `MEMORY_RETRIEVAL_MODE` | `keyword` |
| `OLLAMA_EMBEDDING_MODEL` | `embeddinggemma` |
| `MEMORY_EMBEDDING_TIMEOUT_SECONDS` | `60` |
| `MEMORY_SEMANTIC_MIN_SIMILARITY` | `0.35` |

Ollama embeddings use the existing `OLLAMA_BASE_URL` and a separate model;
planning/final chat keep the existing qwen2.5:7b configuration. Native requests
bypass proxy environment variables and redirects. Inputs are batched by 32 with
`truncate: false`, so oversized inputs fail explicitly. Invalid JSON, model
metadata, vector counts/dimensions, non-finite values, and zero vectors are rejected.

Explicit semantic previews return 503 on unavailable embeddings. Runtime in
semantic mode loads up to five records per scope; failures use the keyword path
and persist a warning `memory_retrieval_fallback` log. Empty-query internal
behavior and the default keyword context format remain compatible.

Vectors are generated per request and kept in memory for that request. No SQL
writes occur during either search mode, and edits/deletes need no reindexing.
This is a linear scan for the local workbench; persistent indexing and additional
storage adapters remain later work.

`LLM_PROVIDER=mock` always uses `mock-fixtures-v1` and makes no embedding HTTP
requests. Supported queries are `Keep it brief.`, `请用简短的方式解释。`,
`Can saved information stay after reboot?`, and `Unrelated semantic fixture.`.
Other queries return 503 when the scope has records, with a fixture explanation.
These fixed vectors test integration, not learned semantic quality.

Run `app.check_semantic_memory` against Mock services configured with
`MEMORY_RETRIEVAL_MODE=semantic`. Eight checks cover ranking without keyword
overlap, Chinese fixtures, thresholds/limits, Agent/User scope, read-only previews,
fresh edit/delete results, validation, and semantic Runtime retrieval. The command
retains three markers and one synthetic isolation User/Project/Agent. Restart
validation checks the immutable checkpoint and original Runtime inspection before
writes. Temporary edit records use unique IDs in their content to preserve
existing user-created fixture records.

## Real Ollama retrieval acceptance

`python -m app.check_ollama_memory --base-url http://frontend` is a separate,
read-only real-provider check. Run it in the Ollama backend after the Mock semantic
acceptance has saved `semantic-memory-acceptance.json` beside SQLite. It reuses
that checkpoint; it never seeds, edits, deletes, chats, or rewrites the checkpoint.
An optional `--state-file PATH` selects another existing checkpoint.

Seven checks verify saved identity/inspection, Agent English paraphrases, shared
Chinese paraphrases, same-user English-to-Chinese retrieval, both isolation scopes,
keyword contrast, and unchanged memory/history/transcripts/checkpoint. Responses
must report `provider: ollama`, the configured embedding model, semantic Runtime
mode, valid scope, descending cosine/ID order, and a valid threshold/result limit.

Expected preference records must appear in the relevant top five. Where the
target also appears in the control query's top 20 (`min_similarity=0`), its relevant
score must be higher. Scores are measured rather than compared to Mock's fixed
0.96. Evidence includes target rank, similarity, control similarity, and a margin
when available; null control values are explained in the root README.

`--timeout 180` is the default per-HTTP-request timeout. It must be positive and
finite; it does not change `MEMORY_EMBEDDING_TIMEOUT_SECONDS` on the server.
The client bypasses proxy environment variables and rejects redirects and HTML.
Errors exit nonzero without replacement writes. The check does not test generated
qwen2.5:7b replies or create Runtime executions. No extra dependency is required.

## Conversation workbench APIs

`POST /conversations` requires an existing positive integer Agent ID and a
trimmed, non-blank title of at most 200 characters. `GET /conversations?agent_id=ID`
returns ordered conversations for that Agent. The existing unfiltered list
remains available to older clients.

Conversation reads, message reads/writes, chat, rename, and deletion accept an optional
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

### Conversation management

`PATCH /conversations/{id}?agent_id=ID` accepts only `{"title": "New title"}`.
The title must be a strict string of 1 to 200 trimmed characters; missing,
blank, overlong, and extra fields return 422. A missing conversation or wrong
Agent returns 404. The response retains its ID, Agent, and creation time.
Legacy callers may omit the optional Agent query.

`DELETE /conversations/{id}?agent_id=ID` retains the existing
`{"message": "deleted"}` response. ORM `all, delete-orphan` cascade removes
associated messages in the same transaction, including with SQLite foreign
keys enabled. A failed commit rolls back both parent and child changes. Agent
memories, executions, traces, snapshots, and other conversations are preserved.
Deleting an already missing conversation returns 404. This relationship change
does not alter table definitions and requires no migration.

Run `python -m app.check_conversation_management --base-url http://frontend` in
Mock mode for six HTTP scenarios. After recreating services, add
`--verify-persistence`. The renamed keeper, saved messages, extracted preference,
and stored execution/snapshot are checked before any repair or test write. The
check deletes only the temporary conversation it creates.

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
`python -m app.check_memory_search --base-url http://frontend` checks shared
retrieval previews and a separate Runtime probe; its persistence option requires
all three original retrieval demo memories before any test write.

The backend image now builds from the repository root to include the separate MCP
environment. For a manual build, run `docker build -f backend/Dockerfile .` from
the repository root.

See [the Docker Compose guide](../docs/docker-compose-demo.md) for complete
commands, switching providers, persistence verification, and troubleshooting.
