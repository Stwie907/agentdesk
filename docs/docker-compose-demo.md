# Docker Compose demo

This guide runs the existing FastAPI, React/Vite, and SQLite application with
Docker Compose. Mock mode uses deterministic planning and marked replies; the
Calculator, MCP order, tracking, and ticket tools execute through Runtime V4. No local model or API key is
needed for Mock task execution.

## Requirements

- Docker with Linux containers and Docker Compose v2 supporting `up --wait`.
- Windows Git Bash, or a Unix shell, for the startup script.
- Internet access for the initial image and dependency build.
- Local ports `5173` and `8000` available. Stop native Vite and Uvicorn servers
  before starting these containers.

The Docker workflow installs application dependencies inside images. A host
Python virtual environment, Node.js installation, and Make are not required for
the direct startup command.

## Start the Mock demo

From the repository root:

```sh
sh deployment/start-demo.sh
```

With Make installed, `make demo` runs the same script. The script validates
Compose configuration, builds both services, waits for healthy containers, and
runs an idempotent demo initializer. Repeating it reuses matching demo records
and preserves existing Agent settings.

The initializer creates a User named `agentdesk-demo`, an `AgentDesk Demo`
Project, a `Demo Agent` with Calculator permission, and a separate `MCP Order Agent`
with `get_order` permission. It also creates `MCP Logistics Agent` with only
`track_order` permission, plus `MCP Ticket Agent` with only `create_ticket`
permission. It prints their actual
IDs. Do not assume that the Agent ID is `1` in an existing volume.

Open `http://localhost:5173` and select `Demo Agent`. Submit these new tasks:

| Task | Expected result |
| --- | --- |
| `Calculate 40 + 2` or `计算40+2` | Completed, output `42`, Calculator step, and `provider=mock` in the initial trace. |
| `Hello AgentDesk` | Completed, reply starting with `[MOCK]`, and a stored snapshot. |
| Replay the Calculator execution | A new completed execution with output `42` and a link to its source. |

The startup script always loads `docker-compose.mock.yml`, which explicitly
selects Mock even when the shell or root `.env` contains `LLM_PROVIDER=ollama`.
Unsupported Mock inputs produce a fixed marked reply rather than general LLM
reasoning. The application itself still defaults to Ollama.

Select `MCP Order Agent` for these tasks:

| Task | Expected result |
| --- | --- |
| `Get order DEMO-1001` or `查询订单DEMO-1001` | Completed JSON order, `shipped`, CNY `129.00`, `source: demo_fixture`. |
| `Get order DEMO-1002` | Completed JSON order, `processing`, CNY `59.00`. |
| `Get order DEMO-9999` | Failed execution with `tool_execution_error` and a not-found message. |
| Replay a successful order execution | A new linked execution with its own trace and snapshot. |

The tool calls a real stdio MCP server in a separate SDK environment inside the
backend image. It publishes no MCP port. The initial build also installs the SDK;
no host virtual environment is required. The initializer preserves existing Agent
permissions and does not add order permission to `Demo Agent`. Traces include
arguments/results or errors. Replay uses the saved plan and current permissions.
The existing eight-case arithmetic/chat evaluation suite remains separate.

Select `MCP Logistics Agent` for shipment queries:

| Task | Expected result |
| --- | --- |
| `Track order DEMO-TRACK-1001` | Completed JSON, `in_transit`, linked order `DEMO-1001`, and 3 UTC events. |
| `查询物流DEMO-TRACK-1002` | Completed JSON, `label_created`, linked order `DEMO-1002`, and 1 event. |
| `Track order DEMO-TRACK-9999` | Failed execution with `tool_execution_error` and a not-found message. |
| Replay a successful tracking execution | A new linked execution with its own arguments/result trace and snapshot. |

Tracking numbers use `DEMO-TRACK-1001`; order ids use `DEMO-1001`. The example
carrier, locations, and event times are fixed synthetic data, not live carrier
information. Order and tracking permissions are independent. Existing Agent
settings are preserved; the order Agent is not granted tracking automatically.

Select `MCP Ticket Agent` for synthetic local support tickets:

| Task | Expected result |
| --- | --- |
| `Create ticket Demo parcel is delayed.` | Completed JSON with a ticket ID, `status: open`, UTC creation time, and `source: demo_ticket_store`. |
| Repeat the same problem | The same ticket ID and timestamp; no duplicate record. |
| `创建工单示例订单需要帮助。` | A different ticket for the different problem. |
| Replay a successful ticket execution | A linked execution with its own trace/snapshot and the original ticket. |

Ticket creation writes only to the local demo SQLite store. The server trims
leading/trailing problem whitespace; the same trimmed problem is deduplicated
across the whole store. Case and internal whitespace remain significant. Inputs
must be non-blank strings of at most 2000 characters. Order/tracking permissions
do not grant write access. Existing Agent settings remain preserved.

## Continue a conversation and extract memory

Select `Demo Agent`. Under **Conversation Chat**, enter `Memory demo` in
**New conversation title** and select **Create conversation**. In **Chat message**,
send `My name is Tom`, then `I like Python`. Confirm the transcript shows both
user and assistant turns and the Memory panel refreshes with the name/preference.
Repeated preferences reuse the same record. A new canonical name replaces the
previous name memory for that Agent.

Send `What do I like about Python?` as a follow-up. Mock returns its fixed marked
reply; Runtime receives history and relevant memory, and the question does not
create a new preference. Each returned execution opens in the Inspector. Return
to the same Agent/conversation after reloading the page to see saved messages.

Titles require 1 to 200 characters; messages require 1 to 4000 characters after
trimming. Failed requests retain drafts. Use **Reload messages** to check the
saved transcript before sending again. Switching Agents resets selections and
drafts and ignores old responses. The panel uses existing SQLite storage and
does not add multi-user authentication.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_conversation --base-url http://frontend
```

Expected JSON includes `status: passed`, `checks_passed: 6`, conversation/memory
IDs, and two execution IDs. The check reuses one named demo conversation and
preference; each run appends two turns. Equivalent: `make conversation-check`.

## Manage Agent memories

Select `Demo Agent` in the task form. In **Agent Memory**, save
`I prefer concise Python answers.`. Confirm that the saved row has a Memory ID,
then save the same content again: its ID remains the same. Select another Agent
to see that Agent's list. Return to `Demo Agent` and use **Reload memories** to
see the original record. **Delete memory** asks for confirmation before removal.

Manual content is trimmed and must contain 1 to 2000 characters. Lists and
workbench delete requests include the selected Agent's scope. Switching Agents
clears drafts and ignores old request results. Existing name replacement and
conversation extraction behavior are preserved. This panel adds no login or
multi-user authorization.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory --base-url http://frontend
```

Expected JSON includes `status: passed`, `checks_passed: 6`, and the Memory and
execution IDs. The check verifies trimming, duplicate reuse, isolation, invalid
input, scoped deletion, and relevant Runtime retrieval. It retains one stable
demo memory and removes its temporary record. Equivalent: `make memory-check`.
The Mock reply remains fixed; successful retrieval is verified in execution
logs. This check does not evaluate model recall.

## Preview memory retrieval

Select `Demo Agent`. Save `User likes Python.` and `我喜欢机器学习。` under
**Agent Memory**. Enter `Python` in **Memory search query**, select **Search
memories**, and inspect the Memory ID, content, keyword-match count, and matched
text. Repeat with `机器学习`. Change **Result limit** to 1 and search again to
see at most one result. An unrelated query shows **No relevant memories found**
while the full saved-memory list remains available.

Queries allow 1 to 500 trimmed characters; the limit defaults to 5. English case,
full-width forms, punctuation, and Chinese fragments use shared keyword rules
with Runtime. This is deterministic matching, not semantic search or translation.
Changing the preview limit does not change Runtime's default limit of 5.
Search creates no execution, conversation, or memory. Saving, editing, deleting,
reloading, or a chat-triggered refresh clears the preview and retains its draft.
Switching Agents resets the query and limit. Failed searches require manual retry.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_search --base-url http://frontend
```

Equivalent: `make memory-search-check`. Expected JSON contains `status: passed`,
`checks_passed: 6`, three `memory_ids`, an `execution_id`, and
`persistence_verified: false`. The acceptance command prepares three stable demo
memories, verifies read-only searches, removes its temporary record from the
other Agent, and submits one separate Mock Runtime probe. That probe is the
source of the reported execution; preview searches themselves create none.

## Edit a saved memory

Select `Demo Agent`. Save `User likes Python.` in **Agent Memory**, note its ID
and creation time, then select **Edit memory** for that row. Change **Edited
memory content** to `User likes Rust.` and select **Save changes**. The row keeps
its ID and creation time. Search `Rust` to see the updated content. Test **Cancel
editing** separately; it sends no request and leaves the saved record unchanged.

A duplicate or an original record changed by chat/another client returns a
conflict and keeps the edit draft. Copy any draft you need, cancel editing, and
reload before resolving the conflict. Edits leave other saved memories, existing
conversations/messages, and historical executions/traces/snapshots available.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_editing --base-url http://frontend
```

Equivalent: `make memory-editing-check`. Expected JSON includes `status: passed`,
`checks_passed: 6`, `memory_id`, `created_at`, and `persistence_verified: false`.
The check retains one edited demo record and an acceptance checkpoint in the
same `/data` volume as SQLite. It cleans up a temporary duplicate-check record
and creates one separate fixed-Mock execution for Runtime retrieval.

After the initial check, recreate services and verify the retained record:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml down
sh deployment/start-demo.sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_editing --base-url http://frontend --verify-persistence
```

Expected: the same `memory_id` and `created_at`, six passed checks, and
`persistence_verified: true`. Missing or changed checkpoint/record data fails
before creating a replacement memory. Avoid editing the acceptance marker
`AgentDeskMemoryEditRust updated.` when testing your own records.

## Share memories across Agents of one user

Select `Demo Agent`, open **Show shared memories**, and save
`I prefer concise SQLite examples.`. Switch to `MCP Order Agent`: the owner
label, shared ID, and content are the same. Agents in separate Projects share
these records when their Projects have the same owner; another owner has a
separate list. Ownership scoping does not add login to this local workbench.

Edit `SQLite` to `Rust`: the row keeps its ID/time. Search `Rust` in **Shared
memory search query** to inspect keyword matches. Canceling keeps an add draft;
stale or duplicate edits preserve the edit draft and report a conflict. Deletion
requires confirmation and affects every Agent of the owner. Automatic extraction
still belongs only to the selected Agent. Mock replies stay fixed; Ollama receives
relevant shared and Agent context.

Run the initial acceptance from the repository root:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_user_memory --base-url http://frontend
```

Equivalent: `make user-memory-check`. Expect `status: passed`, `checks_passed: 8`,
`user_id`, `memory_id`, `isolation_agent_id`, and `persistence_verified: false`.
The check retains `AgentDeskSharedMemoryRust shared.` for the demo owner and
`AgentDeskSharedIsolation private.` for a synthetic second User/Project/Agent.
That isolation Agent appears in the selector. Temporary records are removed.
Keep both acceptance markers unchanged when editing your own records.

A checkpoint `user-memory-acceptance.json` beside SQLite records both full rows
and the original execution/trace/snapshot. Recreate while retaining the volume:

```sh
docker compose down
sh deployment/start-demo.sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_user_memory --base-url http://frontend --verify-persistence
```

Expect the original `memory_id`, eight passed checks, and
`persistence_verified: true`. Both owners, row IDs/content/timestamps, and original
Runtime inspection are checked before any write; data loss fails instead of
recreating fixtures. Repeated checks reuse the isolation Agent and never overwrite
the original checkpoint. Demo initialization/startup adds the new table to existing
SQLite files without changing old records. The supplied Alembic migration supports
versioned databases; the normal Mock demo needs no manual migration command.

## Optional semantic memory retrieval

The keyword default continues to work without an embedding model. Both memory
panels now offer a Semantic search method. With real Ollama, install the separate
local `embeddinggemma` model; chat continues to use `qwen2.5:7b`. The model
requires Ollama v0.11.10 or later; see its
[official model page](https://ollama.com/library/embeddinggemma).

For the offline Mock acceptance, start the demo and enable semantic Runtime:

```sh
sh deployment/start-demo.sh
MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml -f docker-compose.mock.yml \
  up --detach --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_semantic_memory --base-url http://frontend
```

Equivalent after starting the demo: `make semantic-memory-check`. This target
recreates services with semantic Runtime enabled while retaining the data volume.
Expected JSON includes `status: passed`, `checks_passed: 8`,
`embedding_provider: mock`, `runtime_mode: semantic`, and
`persistence_verified: false`. The fixed vectors validate the pipeline without
calling Ollama. They do not measure a real embedding model's semantic quality.

The acceptance retains an Agent fixture `I prefer concise answers.`, a shared
fixture `我喜欢简洁的回答。`, and a shared fixture for a synthetic isolation
User/Project/Agent. Temporary edit records are uniquely named and removed.
Keep these acceptance rows unchanged; the checkpoint records their original
IDs, content, and timestamps plus one execution/trace/snapshot.

After recreation, enable semantic mode again and verify:

```sh
docker compose down
sh deployment/start-demo.sh
MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml -f docker-compose.mock.yml \
  up --detach --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_semantic_memory --base-url http://frontend --verify-persistence
```

Expect the same memory IDs and `persistence_verified: true`. Missing or changed
checkpoints, Agent/shared/isolation rows, or original Runtime inspection fail
before replacement writes. The checkpoint lives beside SQLite in the retained volume.

To try real Ollama vectors:

```sh
ollama pull embeddinggemma
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic docker compose \
  up --build --detach --wait --wait-timeout 180 backend frontend
```

Use the base Compose file for this step so the Mock provider override is omitted.
Save a concise-answer preference and query `Keep it brief.` in Semantic preview;
expect `provider: ollama` and your configured embedding model. Inspect the actual
retrieved content; model-specific quality and scores require local acceptance.
No minimum fixed score is promised for arbitrary real-model queries.

The root `.env` controls the four memory variables in the configuration table.
Compose still maps the local Ollama address through `COMPOSE_OLLAMA_BASE_URL`.
A failed semantic preview displays an error; semantic Runtime records a warning
and uses keyword retrieval. Restore keyword Mock Runtime with:

```sh
MEMORY_RETRIEVAL_MODE=keyword sh deployment/start-demo.sh
```

Semantic previews are read-only and calculate fresh vectors for each request.
They require no new SQLite table or migration.

## Read-only acceptance with real Ollama

Complete the offline semantic acceptance above once, and retain its fixture rows
and checkpoint. Issue #126 users can reuse their already verified checkpoint.

On the Windows host, check the Ollama version and install the local embedding model:

```sh
ollama --version
ollama pull embeddinggemma
```

EmbeddingGemma requires Ollama v0.11.10 or later and its default model download is
approximately 622 MB. See the [official model page](https://ollama.com/library/embeddinggemma).
Keep Ollama running locally. Only the embedding model is used by this check;
chat/planning remain qwen2.5:7b.

From the repository root, use only the base Compose file to select real Ollama:

```sh
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend

docker compose -f docker-compose.yml exec -T backend python -m app.check_ollama_memory --base-url http://frontend
```

Do not include `docker-compose.mock.yml` in the real-provider startup command.
The configured host Ollama address still uses `COMPOSE_OLLAMA_BASE_URL`.
The root `.env` controls the embedding model, threshold, and backend embedding
timeout; the check runs inside that same backend environment.

Expected JSON includes `status: passed`, `checks_passed: 7`,
`embedding_provider: ollama`, `runtime_mode: semantic`, `read_only: true`, and
`chat_executions_created: 0`. The `evidence` list reports actual similarities and
ranks. No fixed 0.96 score is expected. For the control query, a null score means
the target was not returned in the top 20; the bilingual sharing scenario has no
control request. Review the reported records in the workbench if a quality check fails.

The command sends only application GET requests. It reads existing records and
original inspection, then verifies that memory, transcripts, execution history,
and checkpoint are unchanged. It never seeds or repairs missing records.
Avoid editing the acceptance fixtures while the check runs.

To verify the same records after recreation in real-provider mode:

```sh
docker compose down
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml exec -T backend python -m app.check_ollama_memory --base-url http://frontend
```

No new persistence flag is needed: every run validates the original checkpoint.
The named SQLite volume is retained.

A 503 can indicate a stopped/unreachable Ollama, missing embedding model, input
exceeding its context window, or backend embedding timeout. Check the local model
and host address. The client `--timeout` option changes only its wait for the API;
the server's `MEMORY_EMBEDDING_TIMEOUT_SECONDS` remains separate.

Restore the keyword Mock demo after testing:

```sh
MEMORY_RETRIEVAL_MODE=keyword sh deployment/start-demo.sh
```

CI exercises this check with controlled protocol responses and explicit failures;
it does not download a model or claim real-model quality acceptance.

## Inspect captured Runtime memory

In **Runtime V4 Execution Inspector**, load an execution and select **Show
memory retrieval**. Agent and shared user results show the content captured for
that execution, scope, IDs, and the scores that selected them. The panel also
shows the requested and used modes, embedding provider/model/threshold, and an
explicit fallback reason. Expand **Memory context sent to Runtime** to inspect
the exact injected text. Mock similarity is identified as fixed test vectors.

Evidence persists in SQLite execution logs and remains unchanged after source
memory edits or deletion. It is a historical capture, not a fresh preview.
Reading it makes no embedding requests and writes no records. Old executions,
plan replays, and executions that have not reached retrieval may have no
recorded evidence. **Refresh memory retrieval** checks again after an active
execution finishes. A corrupt capture displays an error instead of current
memory. Existing traces and snapshots retain their formats.

Use the offline semantic fixtures already created above. Run:

```sh
MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml -f docker-compose.mock.yml \
  up --detach --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_evidence --base-url http://frontend
```

Equivalent initial check: `make memory-evidence-check` after
`make semantic-memory-check`. Expect `checks_passed: 6`,
`chat_executions_created: 3` on the first run, and execution IDs labelled
`semantic`, `fallback`, and `isolation`. The checks cover both captured scopes,
keyword fallback, user isolation, positive/scoped API IDs, unchanged source
fixtures, and the original saved inspections. Subsequent runs reuse the
checkpoint and create zero chats. Mock replies stay fixed; this check measures
the recording pipeline and does not measure a learned embedding model.

Open the returned `semantic` execution ID in the Inspector. Expect provider
`mock`, model `mock-fixtures-v1`, and fixture cosine `0.960000` for the concise
answer memories. The `fallback` execution shows keyword ranking with the Mock
unsupported-query reason.

Recreate services while retaining the volume, then verify:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml down
MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml -f docker-compose.mock.yml \
  up --detach --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_evidence --base-url http://frontend --verify-persistence
```

Expect the same execution IDs, `persistence_verified: true`, and
`chat_executions_created: 0`. The read-only verification compares each original
execution, trace, snapshot, and retrieval capture. Keep
`semantic-memory-acceptance.json`, `memory-evidence-acceptance.json`, their
fixture rows, and the SQLite volume. Missing or changed checkpoints or records
fail before replacement writes; rerunning the initial command does not repair
an invalid existing checkpoint.

## Verify SQLite vector caching

The semantic Runtime caches unchanged document vectors in SQLite and embeds
only the current query on a fully warm retrieval. Keyword mode is unchanged.
Agent vectors remain Agent-scoped, and shared vectors remain scoped to their
user owner. Preview searches read existing cache entries without writing any
cache or source records. Ollama model digest checks prevent reuse after a model
update, including changes behind the same model tag.

After rebuilding the Mock backend and retaining the existing semantic fixtures:

```sh
MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml -f docker-compose.mock.yml \
  up --detach --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_vector_cache --base-url http://frontend
```

Expect `checks_passed: 7`, positive `cache_hits`, `cache_misses: 0`, and
`cache_written: 0` for the warm proof execution. On the first run,
`chat_executions_created: 6`. The check also exercises scoped edit/delete
invalidation using unique temporary records, then removes those records. Saved
fixture memories and their original inspections remain unchanged. Cache
metrics are available in the warm execution's `/logs` endpoint.

Recreate services while keeping the volume:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml down
MEMORY_RETRIEVAL_MODE=semantic docker compose -f docker-compose.yml -f docker-compose.mock.yml \
  up --detach --wait --wait-timeout 180 backend frontend
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_vector_cache --base-url http://frontend --verify-persistence
```

Expect `persistence_verified: true`, unchanged `original_execution_ids`, positive
warm hits, zero misses and writes, and `chat_executions_created: 1`. This check
first verifies the exact original vectors, source fixtures, execution records,
traces, snapshots, and memory captures. Only then does one new fixed Mock chat
prove that saved document vectors are reused. Missing or changed data fails
before any replacement chat or vector can be created. Keep
`memory-vector-cache-acceptance.json`, the semantic checkpoint, and the volume.
The existing `check_memory_evidence --verify-persistence` remains read-only.

Caching defaults to enabled for semantic retrieval. To bypass it, set
`MEMORY_VECTOR_CACHE_ENABLED=false` in the root `.env` and recreate the backend.
This bypass retains stored cache data. Embeddings, ranking, and the local
`qwen2.5:7b` chat model remain available with the original configuration.

## Check services and run the smoke check

```sh
docker compose ps
docker compose exec -T frontend nginx -t
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend python -m app.check_demo --base-url http://frontend
```

The final command returns JSON containing `"status": "passed"` and the actual
Agent, execution, and replay IDs. It checks the served React build and assets,
API health, Agent selection, Calculator execution, Mock trace marker, marked
chat reply, snapshots, and replay history. It creates demo executions during
the check. `make demo-check` runs the same command.

Run the MCP acceptance check separately:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_runtime --base-url http://frontend
```

Expected JSON includes `status: passed`, `transport: stdio`, `checks_passed: 5`,
and actual execution/replay IDs. The check creates demo executions. It also checks
that `Demo Agent` has no order permission and uses a no-tool Mock response; keep
its original Calculator-only permissions for this check.

Run the logistics acceptance check:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_tracking --base-url http://frontend
```

Expected JSON includes `status: passed`, `checks_passed: 5`, and actual tracking
execution/replay IDs. Keep `MCP Order Agent` without tracking permission for the
negative permission scenario. This check creates demo executions. Equivalent:
`make mcp-tracking-check`.

Run the ticket acceptance check:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_ticket --base-url http://frontend
```

Expected JSON includes `status: passed`, `checks_passed: 5`, ticket IDs, and the
execution/replay IDs. Keep `MCP Logistics Agent` without `create_ticket`
permission for the negative planning scenario. The check creates two distinct
demo tickets, repeats one problem, and replays it. Equivalent: `make mcp-ticket-check`.

The following addresses have different purposes:

| Address | Purpose |
| --- | --- |
| `http://localhost:5173` | Browser workbench and API proxy. |
| `http://localhost:5173/healthz` | Nginx/frontend health. |
| `http://localhost:5173/health` | Backend health through the frontend proxy. |
| `http://localhost:8000/health` | Direct backend health. |
| `http://localhost:8000/docs` | Direct API documentation. |
| `http://backend:8000` | Internal Compose backend address. |

Nginx forwards API paths and query strings to the backend service. It starts
after backend health succeeds. Its proxy read timeout allows for local planning,
final replies, and the existing retry policy with the default LLM timeout.

## Persistence and stop

Compose fixes the container database URL to `sqlite:////data/agentdesk.db` and
mounts `/data` from the project's `agentdesk-data` named volume. Native
`backend/agentdesk.db` is a separate database and is not copied into the image.
The image also sets `MCP_TICKET_DB=/data/mcp-tickets.db`; this dedicated MCP store
uses the same persistent volume. Native MCP tickets instead default to
`mcp-server/data/tickets.db`, also excluded from Git and image builds.

Stop containers while retaining data:

```sh
docker compose down
```

To verify persistence after a successful smoke check:

```sh
docker compose down
sh deployment/start-demo.sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend python -m app.check_demo --base-url http://frontend --verify-persistence
```

After the initial ticket acceptance check, verify its persistence after the same
service recreation:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_ticket --base-url http://frontend --verify-persistence
```

This compares newly returned tickets against saved execution outputs. Losing the
MCP database produces different ticket IDs and fails the check, even if backend
execution history survives. Normal shutdown retains both databases.

After running the initial memory check, verify its record after the same restart:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory --base-url http://frontend --verify-persistence
```

The demo memory must already exist before the check writes anything. Its ID,
content, and creation time must match the repeated save. Agent memories share
`/data/agentdesk.db`; keep the same Compose project and volume across restarts.

After the initial memory retrieval check, verify its records after the same
restart:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_search --base-url http://frontend --verify-persistence
```

Expected JSON includes `status: passed`, `checks_passed: 6`, and
`persistence_verified: true`. All three original retrieval demo memories must
exist before any test write. A lost record fails instead of being recreated to
pass. Duplicate saves retain the original IDs, contents, and creation times.

The persistence option checks that earlier Calculator, Mock chat, and linked
replay records and their snapshots are present before creating new test tasks.
Keep the same repository directory and Compose project name across runs so
Compose reuses the same volume.

After the initial conversation check, verify it after the same service restart:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_conversation --base-url http://frontend --verify-persistence
```

Conversation, transcript, and extracted preference must already exist. Missing
data fails before any new chat can recreate it. All three use `/data/agentdesk.db`.

## Rename and delete conversations

Select `Demo Agent` and a conversation. Edit **Conversation title** and select
**Rename conversation**. Confirm that its ID, saved messages, and chat draft
stay the same. Reload the page and select it again to see the persisted title.

Choose **Delete conversation**. Review its title and ID, then test **Cancel
delete** first. Choose **Delete conversation** again and **Confirm delete** to
remove that conversation and its messages. Its selector entry and transcript
disappear. Agent memories and execution history, including Inspector traces and
snapshots, stay available. Use **Agent Memory** separately to delete a memory.

Run the automated checks from the repository root:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_conversation_management --base-url http://frontend
```

Equivalent: `make conversation-management-check`. Expected JSON includes
`status: passed`, `checks_passed: 6`, `keeper_conversation_id`,
`deleted_conversation_id`, and `preserved_execution_id`. A named keeper is
retained; only a newly created disposable conversation is deleted. The check
verifies that protected conversations, Agent memories, and the deleted
conversation's execution, trace, and snapshot are unchanged.

After the same service recreation described above, run:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_conversation_management --base-url http://frontend --verify-persistence
```

The renamed keeper, transcript, memory, and stored execution/snapshot must exist
before any test writes. Missing data fails instead of being recreated to pass.
This uses the existing `/data/agentdesk.db` volume without a schema migration.

## Switch to local Ollama

Use the base Compose file without the Mock override. Ollama must run on the host,
have `qwen2.5:7b` available for `Demo Agent`, and accept connections from Docker.
The container uses `COMPOSE_OLLAMA_BASE_URL`, whose default is
`http://host.docker.internal:11434`; native `OLLAMA_BASE_URL=localhost` is kept
separate because container localhost refers to the container itself.

From Git Bash or a Unix shell:

```sh
LLM_PROVIDER=ollama docker compose up --build --detach --wait --wait-timeout 180 backend frontend
```

This recreates the backend with normal Ollama settings and retains its data
volume. On a fresh volume, create demo records with:

```sh
docker compose exec -T backend python -m app.seed_demo
```

Agent model selections continue to control final replies; the planner model
setting does not overwrite them.

Ollama binds to host loopback by default. If Docker cannot reach it, configure a
Docker-reachable bind address using `OLLAMA_HOST` and restart Ollama. The
[official Ollama FAQ](https://docs.ollama.com/faq#how-do-i-configure-ollama-server)
describes Windows application and Linux service configuration. Mock mode works
without changing Ollama settings. Backend connection and timeout errors remain
failures and do not silently select Mock.

Return to Mock using `sh deployment/start-demo.sh`.

## Configuration

Compose reads a root `.env` for interpolated values; native Uvicorn reads values
exported into its own terminal. Copying `.env.example` to `.env` does not activate
native backend settings. The script does not require a `.env` file.

| Setting | Container behavior |
| --- | --- |
| `LLM_PROVIDER` | Base Compose defaults to `ollama`; the Mock override forces `mock`. |
| `MEMORY_VECTOR_CACHE_ENABLED` | `true` by default; `false` bypasses document vector caching. |
| `COMPOSE_OLLAMA_BASE_URL` | Container Ollama URL; defaults to the host Docker gateway. |
| `OLLAMA_PLANNER_MODEL` | Defaults to `qwen2.5:7b`. |
| `OLLAMA_TIMEOUT_SECONDS` | Defaults to `120` seconds per model request. |
| `MCP_TIMEOUT_SECONDS` | Defaults to `30` positive finite seconds per MCP call; cleanup has a separate grace period. |
| `DATABASE_URL` | Container value is fixed to the SQLite volume; the native reference value does not override it. |

## Troubleshooting

- Docker connection errors: start Docker Desktop/the Docker daemon and confirm
  `docker compose version` works.
- Port already allocated: stop the native frontend/backend or other containers
  using `5173` or `8000`, then repeat startup.
- Unhealthy backend: inspect `docker compose logs backend`. Health requires a
  started application; Ollama is not part of the health check.
- API `502`: inspect `docker compose ps` and `docker compose logs frontend
  backend`; verify both services are healthy and run the Nginx config check.
- Missing `Demo Agent`: repeat startup or rerun the initializer. A demo User
  identity conflict is reported without changing that User.
- A changed Demo Agent no longer allows Calculator: the initializer preserves
  existing settings; restore Calculator permission explicitly before checking
  the arithmetic demo.
- Missing `MCP Order Agent`: run `docker compose exec -T backend python -m app.seed_demo`.
- Missing `MCP Logistics Agent`: rerun the initializer after rebuilding the backend.
- Missing `MCP Ticket Agent`: rerun the initializer after rebuilding the backend.
- Ticket creation errors: verify the dedicated MCP database path is writable and
  the Agent explicitly permits `create_ticket`. Native overrides must be absolute
  file paths. Blank or oversized Mock commands select no tool.
- MCP import/client errors: rebuild with `sh deployment/start-demo.sh`; the updated
  image includes the isolated SDK. Native setups require the separate environment
  described in the backend guide.

## CI verification

The existing `structure` job runs backend tests, frontend tests, and the
production frontend build. The `compose-demo` job builds and starts actual
containers, validates Nginx and the published health endpoints, runs the Mock
smoke check, recreates the services, and verifies persisted executions and
snapshots. It prints container logs and removes its temporary CI volume at the
end. Normal local shutdown retains the volume.

CI installs the separate SDK environment for real backend API tests, runs the
integrated MCP check in `compose-demo`, and retains standalone protocol checks
and tests in `mcp-tools`.
Order, tracking, and ticket acceptance checks run in `compose-demo`, including
ticket persistence after recreation. Memory acceptance also runs before and
after recreation. Conversation history and automatic memory acceptance also run
before and after recreation. Conversation management acceptance verifies rename,
scoped message deletion, retained Agent data, and restart persistence.
Memory retrieval acceptance checks shared ranking, read-only scoped previews,
and retained retrieval demo memories before and after recreation.
Memory editing acceptance checks scoped conditional updates, conflicts, updated
retrieval, and exact retained identity against its checkpoint after recreation.
Shared user memory acceptance checks same-user sharing, cross-user isolation,
conditional edits, scoped deletion, and Runtime retrieval before recreation, then
checks both owners' rows and original Runtime inspection after recreation.
The semantic check then enables Mock Runtime semantic mode and verifies explicit
fixture vectors before and after recreation. It covers both memory scopes and
never downloads or requires an Ollama model in CI.
Memory evidence acceptance then records three Mock executions and verifies
their captured retrieval facts, scopes, fallback, traces, and snapshots after
recreation without creating replacement chats.
Vector cache acceptance verifies warm reuse, scoped source invalidation, and
read-only previews, then validates its original saved vectors before creating
one proof chat after recreation. It uses fixed Mock fixtures without a model
download or paid API.
Standalone protocol checking covers 25
checks and the MCP test suite contains 52 tests. Ticket protocol tests use
temporary databases independently of the application's store.

References: [Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/),
[Compose networking](https://docs.docker.com/compose/how-tos/networking/), and
[Nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
