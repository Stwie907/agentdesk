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
calculator-enabled `Demo Agent`, `MCP Order Agent`, `MCP Logistics Agent`, and
`MCP Ticket Agent`.
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

Select `MCP Ticket Agent` for `Create ticket Demo parcel is delayed.` or
`创建工单示例订单需要帮助。`. The real `create_ticket(problem)` tool writes to a
separate local SQLite ticket store and returns JSON containing `ticket_id`,
`problem`, `status: open`, `created_at`, and `source: demo_ticket_store`.
It contacts no external support service. Only this Agent is given ticket write
permission; existing Agent settings are preserved.

Submitting the same problem again, after trimming leading/trailing whitespace,
returns the original ticket and timestamp. Replay calls MCP again but reuses the
stored ticket. Different problems create different tickets. Problems must be
non-blank strings of at most 2000 characters; this is a local demo deduplication
contract rather than customer-scoped ticket management.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_mcp_ticket --base-url http://frontend
```

Equivalent: `make mcp-ticket-check`. It checks English/Chinese creation, duplicate
submission, linked replay, and planning without write permission. After running
this check, stop and restart the demo, then repeat it with `--verify-persistence`
to verify the ticket IDs and contents survive service recreation.

SQLite is stored in a Docker named volume. `docker compose down` stops the
services while retaining application data and `/data/mcp-tickets.db`. Native MCP
tickets default to `mcp-server/data/tickets.db`; both native databases are separate
from the container data. The MCP server owns ticket persistence.

See [Docker Compose instructions](docs/docker-compose-demo.md),
[backend setup](backend/README.md), and [frontend setup](frontend/README.md).

## Agent Memory workbench

Select an Agent in the task form to view its persistent memories. Enter
`I prefer concise Python answers.` in **Memory content**, then select **Save
memory**. The panel supports reload, empty/error states, duplicate reuse, and
inline editing, and confirmed deletion. Switching Agents starts a new draft and ignores old requests.

Manual writes require an existing Agent and trimmed content of 1 to 2000
characters. Exact duplicates reuse the same record. Canonical name memories use
the existing replacement policy. Lists and workbench deletes are Agent-scoped;
this scope check does not add authentication or multi-user authorization.
Existing conversation extraction remains unchanged. Runtime and the retrieval
preview below share the same keyword ranking.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory --base-url http://frontend
```

Equivalent: `make memory-check`. Six scenarios check trimming, duplicate reuse,
Agent isolation, validation, scoped deletion, and Runtime retrieval. The check
leaves one stable demo memory, cleans up its temporary record, and creates a
marked Mock execution. After stopping and restarting the services, repeat with
`--verify-persistence`; missing data fails before any replacement write.

Memory uses the application's existing SQLite volume. Mock replies stay fixed
even when relevant memory is loaded; the check verifies retrieval in execution
logs and the saved snapshot. Ollama receives relevant context through the existing
runtime. Shared user memory and optional local semantic retrieval are available
below; persistent vector indexing and Redis/PostgreSQL adapters remain future
Memory work.

## Preview relevant memories

Under **Agent Memory**, enter `Python` or `机器学习` in **Memory search query**
and select **Search memories**. Matching records show their Memory ID, content,
keyword-match count, and matched text. **Result limit** defaults to 5 and affects
only the preview; Runtime continues to use its existing default limit of 5.

The Agent-scoped `GET /memories/{agent_id}/search` API accepts a trimmed query of
1 to 500 characters and a limit of 1 to 20. It uses the same ranking as Runtime:
distinct overlapping terms count once, with newer IDs first when scores tie.
Case and full-width forms are normalized. English technical tokens and adjacent
Chinese character pairs support deterministic keyword matching, without semantic
search or translation. Blank queries are rejected; unrelated queries return an
empty result list.

Search only reads saved memories: it creates no execution, conversation, or
memory. Changes to the query, limit, or saved memories clear stale results.
Saving, editing, deleting, reloading, or a chat-triggered memory refresh preserves the
search draft; switching Agents resets it. Failed searches keep the draft and
require an explicit retry.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_search --base-url http://frontend
```

Equivalent: `make memory-search-check`. Six scenarios verify ranking and match
evidence, limits and normalization, Chinese/no-match behavior, Agent isolation,
read-only validation, and a separate Runtime retrieval probe. The acceptance
command creates three stable demo memories, removes its temporary scoped record,
and creates one marked Mock execution for that explicit Runtime probe. After
recreating services, add `--verify-persistence`; all three memories must already
exist before any test write. No database migration or dependency is added.

## Edit a saved memory

Select **Edit memory** beside a saved record, change **Edited memory content**,
then choose **Save changes** or **Cancel editing**. Edits allow 1 to 2000 trimmed
characters and retain the original Memory ID, Agent, and creation time. Other
memories, conversations, and saved executions, traces, and snapshots are preserved.

An identical record or another canonical name record for the same Agent causes
an explicit conflict. If chat or another client changed the original content,
the edit is rejected rather than overwriting that newer content. Failed edits
keep the draft. Copy any draft you want to keep, cancel editing, and reload before
resolving a conflict. Writes and reloads are locked during submission; chat-triggered
refreshes wait until editing ends. Saving clears the previous retrieval preview.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_editing --base-url http://frontend
```

Equivalent: `make memory-editing-check`. Six scenarios check preserved identity,
updated preview/Runtime retrieval, duplicate conflicts, stale/invalid writes,
Agent isolation, and protected records. The command retains one edited demo
memory and a persistence checkpoint beside the SQLite database, removes a
transient record, and creates one separate Mock Runtime probe. After recreation,
repeat with `--verify-persistence`: the checkpoint and the exact original ID,
content, and creation time must exist before any test write. No migration,
dependency, or paid API is added.

## Shared user memory

Select **Show shared memories** under **Shared User Memory**. This panel resolves
the selected Agent's Project owner, then lists that user's shared records. Save
`I prefer concise SQLite examples.`, switch from `Demo Agent` to `MCP Order Agent`,
and see the same ID and content. Agents in different Projects also share memories
when their Projects have the same owner. Another user's Agents have a separate list.

Shared records support add, conditional edit, confirmed delete, reload, and a
keyword retrieval preview. Content allows 1–2000 trimmed characters. Exact
duplicates retain the original ID/time; conflicting edits return HTTP 409 and
preserve the draft. Deleting one shared row affects every Agent of its owner.
Shared memory is saved explicitly: automatic conversation extraction still
belongs only to the selected Agent. Ownership checks use the existing data model;
they do not add authentication to this local workbench.

Runtime retrieves up to five relevant shared records and five Agent records with
the same deterministic bilingual ranking. It labels the two sources separately
when shared context is present. Ollama receives that context; Mock replies remain
fixed. The new SQLite table is created by the existing demo initializer/startup,
and an additive Alembic migration supports versioned databases without rewriting
existing Agent memories, conversations, messages, executions, traces, or snapshots.

```sh
make user-memory-check
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_user_memory --base-url http://frontend --verify-persistence
```

Run the first command before recreation and the second after recreation. Eight
scenarios check sharing, isolation, duplicate reuse, edit identity/conflicts,
validation, scoped deletion, protected Agent data, and Runtime retrieval. The
check retains two shared markers and a separate synthetic User/Project/Agent for
isolation, with an immutable checkpoint beside SQLite. Restart validation checks
both records and the original execution/trace/snapshot before any write. See the
[Compose guide](docs/docker-compose-demo.md) for the full recreation sequence.

## Optional local semantic memory retrieval

Both memory panels offer **Keyword** and **Semantic (local embeddings)** search.
Keyword remains the default. Semantic previews use cosine similarity over
owner-scoped records and show the provider, embedding model, and Runtime mode.
Agent memories remain private to their Agent; shared memories remain user-scoped.

Ollama semantic search uses `POST /api/embed` with a separately configured local
embedding model. Chat and planning retain `qwen2.5:7b`. The default embedding model
is `embeddinggemma`; pull it locally before using semantic search in Ollama mode:

```sh
ollama pull embeddinggemma
```

The model requires Ollama v0.11.10 or later. See the
[Ollama embedding model](https://ollama.com/library/embeddinggemma) and
[embedding API](https://docs.ollama.com/api/embed).

`MEMORY_RETRIEVAL_MODE=semantic` enables semantic Runtime retrieval; selecting a
preview method affects only that preview. The default minimum cosine similarity
is 0.35, configurable with `MEMORY_SEMANTIC_MIN_SIMILARITY`. Runtime retrieves
up to five matching rows from each scope. Embedding failures produce an explicit
503 in semantic previews; Runtime uses keyword ranking and records
`memory_retrieval_fallback` in execution logs.

Vectors are calculated on demand in batches of at most 32 inputs. Previews
remain read-only, and edits/deletion are reflected on the next request. No
embedding cache, vector database, new migration, or paid API is required.

Mock semantic mode uses a documented set of fixed vectors for pipeline tests.
Save `I prefer concise answers.`, select Semantic, and query `Keep it brief.`.
A Chinese fixture uses `我喜欢简洁的回答。` and `请用简短的方式解释。`.
Results are labeled **Mock fixture vectors**. These fixtures validate the
pipeline; real semantic quality requires a local Ollama model acceptance.

```sh
make semantic-memory-check
```

This target enables semantic Runtime in the running Mock services, then runs
eight acceptance scenarios. It retains Agent/shared/isolation markers and a
checkpoint beside SQLite. After recreation, enable semantic Runtime again and
run `app.check_semantic_memory --verify-persistence`; checkpoint identities and
the original execution/trace/snapshot are checked before any fixture writes.
Restart `make demo` with `MEMORY_RETRIEVAL_MODE=keyword` to restore keyword Runtime.
See the [Compose guide](docs/docker-compose-demo.md) for the exact commands.

## Read-only Ollama memory acceptance

After completing the Mock semantic check, keep its checkpoint and fixture rows.
Switch the backend to `LLM_PROVIDER=ollama` and `MEMORY_RETRIEVAL_MODE=semantic`,
then run:

```sh
docker compose -f docker-compose.yml exec -T backend python -m app.check_ollama_memory --base-url http://frontend
```

Equivalent: `make ollama-memory-check`. Seven read-only checks reuse the existing
Agent/shared/isolation fixtures and original saved inspection. They check English
paraphrases, Chinese retrieval, same-user cross-language retrieval, Agent/User
scope, keyword contrast, and unchanged records/checkpoint. The check sends only
GET requests to the application; it creates no chat execution or memory.

The JSON report includes the real provider/model, target rank, cosine similarity,
and comparison with an unrelated database-recovery query. Relevant targets must
appear in the top five at the configured threshold. When a target is returned for
the control query, its relevant score must be higher. `control_similarity: null`
means the target was absent from the control's top 20, or no control was requested
for that scenario. This checks the documented fixtures, not a general model benchmark.

Missing/changed fixtures, Mock responses, mismatched configuration, unavailable
models, invalid scores/scopes, and unmet quality expectations fail explicitly.
A failure does not repair or overwrite data. Chat still uses qwen2.5:7b and is not
invoked by this check. See the [Compose guide](docs/docker-compose-demo.md) for
model installation, switching, restart verification, and restoring Mock mode.

## Inspect the memory used by an execution

Load an execution in the Inspector and select **Show memory retrieval**. The
panel displays captured Agent and shared user memories, their original content
and identity, the requested and used retrieval modes, keyword matched terms or
cosine scores, embedding metadata, and any keyword fallback reason. Expand
**Memory context sent to Runtime** to inspect the exact memory text supplied to
the Agent runner. Mock scores are explicitly identified as fixed test vectors.

Evidence is saved with the execution in the existing SQLite execution logs.
Editing or deleting a source memory does not rewrite historical evidence, and
reading evidence does not call Ollama or rerun retrieval. Older executions,
plan replays, and executions that have not reached retrieval return an explicit
unavailable result. Refresh the panel after an active execution completes.

After `make semantic-memory-check`, run `make memory-evidence-check`. The first
run creates three fixed Mock chats to capture semantic, keyword fallback, and
cross-user isolation evidence. Later runs reuse those executions. The restart
check is read-only and verifies their original evidence, traces, and snapshots:

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_evidence --base-url http://frontend --verify-persistence
```

Keep both acceptance checkpoint files and the SQLite volume. Missing or changed
evidence fails verification without creating replacement chats. See the
[demo guide](docs/docker-compose-demo.md) for the complete restart sequence.

## SQLite memory vector cache

Semantic Runtime caches scoped document embeddings in SQLite. A warm retrieval
embeds its query again and reuses unchanged document vectors. Agent memories
stay Agent-scoped; shared memory vectors can be reused by Agents of one owner.
Read-only previews can consume the cache but never populate or repair it.

The cache verifies source content and creation time, provider, model, endpoint,
vector checksum and dimensions. Ollama cache reuse also checks the configured
model digest from its local model catalog. Changed or corrupt vectors are
recomputed. Source edits and deletion clear all matching cache versions in the
same transaction. Model identity changes during cached retrieval produce an
explicit semantic error or the existing Runtime keyword fallback.

Set `MEMORY_VECTOR_CACHE_ENABLED=false` to bypass caching. Keyword mode remains
the default, and the chat model stays `qwen2.5:7b`. If cache storage or model
identity is unavailable, retrieval computes document vectors normally.

After the existing Mock semantic acceptance, run `make memory-vector-cache-check`.
The check verifies both scopes, warm hits, source invalidation, isolation,
read-only previews, and original persisted inspections. It uses fixed Mock
vectors and measures the cache pipeline, not a learned model's quality.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_memory_vector_cache --base-url http://frontend --verify-persistence
```

Restart verification checks the original cache rows and executions before
creating one proof chat. Expect positive `cache_hits`, zero `cache_misses`, and
zero `cache_written`. Missing or changed checkpoints or original cache entries
fail before the proof chat can regenerate them. See the
[demo guide](docs/docker-compose-demo.md) for the complete sequence.

For the installed local Ollama embedding model, run
`make ollama-memory-vector-cache-check` after starting the real-provider backend
with semantic retrieval and caching enabled. The check invokes the Runtime
memory context builder, records the real embedding inputs, and verifies four
warm scopes using query-only embeddings. It also runs the existing real-model
preview quality checks. It does not invoke the chat model or create executions.

The initial run may populate document cache rows and saves a separate Ollama
checkpoint. After container recreation, `--verify-persistence` validates the
original cache and every business table before any embedding call, then performs
read-only retrieval. Existing Mock namespaces, source records, and checkpoints
are preserved. See the [demo guide](docs/docker-compose-demo.md) for both commands.

## Multi-turn conversation workbench

Select an Agent, then create or select a conversation under **Conversation Chat**.
Send `My name is Tom` and `I like Python` as separate **Chat message** turns.
The transcript is saved, each execution opens in the Inspector, and **Agent
Memory** refreshes with the extracted facts. A follow-up such as
`What do I like about Python?` loads previous history and relevant memories
without saving the question as a new preference.

Conversation titles allow 1 to 200 trimmed characters; chat messages allow 1 to
4000. Requests include the selected Agent's scope. Failed requests keep drafts
and are not retried automatically. Switching Agents ignores old responses.
One-off task submission retains its existing behavior. Mock replies remain fixed;
Ollama receives history and relevant context through the existing Runtime.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_conversation --base-url http://frontend
```

Equivalent: `make conversation-check`. The command reuses a demo conversation
and extracted preference and appends two turns. After restarting, add
`--verify-persistence` to check that conversation, messages, and memory survived
before creating further turns. This uses existing SQLite storage and adds no
paid service. Persistent vector indexing and Redis/PostgreSQL adapters remain
future work.

## Rename or delete a conversation

Select a conversation, edit **Conversation title**, and choose **Rename
conversation**. A title contains 1 to 200 trimmed characters. Renaming preserves
the conversation ID, Agent, creation time, transcript, and chat draft.

Choose **Delete conversation** to review its title and ID. **Cancel delete**
keeps it; **Confirm delete** removes that conversation and its messages in one
database transaction. The panel clears its selection and transcript. Other
conversations, Agent memories, execution history, traces, and snapshots remain
available. Deleting a conversation does not delete its previously extracted
Agent memories; manage those separately in **Agent Memory**.

```sh
docker compose -f docker-compose.yml -f docker-compose.mock.yml exec -T backend \
  python -m app.check_conversation_management --base-url http://frontend
```

Equivalent: `make conversation-management-check`. Six scenarios verify rename,
rejected writes, deletion with messages, missing/deleted resources, retained
Agent memory and inspection, and protected conversations. It retains one named
keeper conversation and removes a temporary conversation. After restarting,
add `--verify-persistence`; the renamed keeper, transcript, memory, and stored
execution must already exist before any test write. No migration or dependency
is added.

## Search and paginate conversations

Use **Conversation title search** to find saved titles for the selected Agent.
Choose **Search conversations** to apply a trimmed title fragment, or
**Clear conversation search** to browse all titles. English ASCII matching
ignores case, Chinese fragments match directly, and punctuation such as `%`
and `_` stays literal. This searches titles rather than message contents.

The workbench loads 10 conversations per page, newest first. Choose 5, 10, 20,
or 50 under **Conversations per page**, then use **Previous conversations** and
**Next conversations**. Changing the search or size returns to the first page.
The matching count is shown separately from the selected chat.

Paging and searching retain the active conversation, transcript, chat draft,
rename draft, and new-conversation draft. An active conversation outside the
results is kept under **Current conversation**. Selecting a different chat
clears its unsent chat draft. Creating a new conversation clears the applied
search and selects the new record on the first page. A rename refreshes filtered
results; deletion fills the page or moves back when the final page becomes empty.
Reload validates an off-page selection with the existing scoped read endpoint.

```sh
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_conversation_pagination --base-url http://frontend
```

Equivalent: `make conversation-pagination-check`. It works with either Mock
or Ollama, creates six acceptance conversations and one saved message initially,
and makes no model or chat-execution request. Eight checks cover pages, bilingual
literal title search, validation, scope, original identity/transcript, and
unchanged data during reads. After recreating services, add
`--verify-persistence`; original IDs, messages, timestamps, and SQLite fingerprints
must match before read-only probes. Keep records unchanged between the two runs.
The new `/conversations/page` endpoint is additive; legacy lists remain available.
See the [Compose guide](docs/docker-compose-demo.md) for the complete commands.

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
discovers `get_order(order_id)`, `track_order(tracking_no)`, and
`create_ticket(problem)`, and runs 25 checks
covering structured replies and tool errors.
Lookups use fixtures marked `source: demo_fixture`; ticket checks write to an
isolated temporary store marked `source: demo_ticket_store`. The check requires no
model or external business API, and has no published port. The optional MCP
check container is removed after the command completes.

Run `make mcp-test` for business data, SQLite deduplication/concurrency, SDK, and
real subprocess protocol tests.
See [the MCP guide](mcp-server/README.md) for runtime integration and native setup.
All three initial MCP business tools are implemented. Remote server configuration
and connection pooling remain future MCP work.

## Repository layout

- `backend/`: FastAPI APIs, Agent runtime, demo commands, persistence, and tests.
- `frontend/`: React, TypeScript, and Vite execution workbench with Nginx hosting.
- `docs/`: project and deployment documentation.
- `deployment/`: the portable Mock demo startup script.
- `mcp-server/`: independent stdio business tools, lookup fixtures, SQLite ticket store, and protocol tests.
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
| `make mcp-check` | Verify all three standalone MCP business tools in Docker. |
| `make mcp-test` | Run business data, ticket storage, and MCP protocol tests in Docker. |
| `make mcp-runtime-check` | Check order tasks, permissions, traces, errors, snapshots, and replay through the running Mock API. |
| `make mcp-tracking-check` | Check shipment tasks, permissions, traces, errors, snapshots, and replay through the running Mock API. |
| `make mcp-ticket-check` | Check ticket creation, duplicate submission, write permissions, traces, snapshots, and replay. |
| `make memory-check` | Check Agent memory storage, isolation, validation, deletion, and Runtime retrieval. |
| `make memory-editing-check` | Check scoped edits, conflicts, preserved identity, and updated Runtime retrieval. |
| `make memory-search-check` | Check shared keyword ranking, scoped read-only previews, match evidence, and Runtime retrieval. |
| `make user-memory-check` | Check same-user sharing, different-user isolation, conditional edits, and Runtime retrieval. |
| `make semantic-memory-check` | Enable offline semantic fixtures and check cosine ranking, scopes, fresh edits, and Runtime retrieval. |
| `make ollama-memory-check` | Check real Ollama fixture retrieval, scope, measured quality, and unchanged saved data using only GET requests. |
| `make conversation-check` | Check scoped multi-turn chat, automatic memory, Runtime context, and saved snapshots. |
| `make conversation-management-check` | Check rename, scoped message cleanup, protected conversations, and retained Agent data. |
| `make stop` | Stop services while retaining the data volume. |

The application keeps Ollama as its default provider. The Mock Compose override
selects deterministic demo behavior. Use the Docker guide to switch an existing
demo to a local Ollama server without deleting its data.

## Load older conversation messages

Selecting a conversation loads its latest 20 saved messages in chronological
order. **Load older messages** prepends another page while keeping the selected
conversation and all drafts. The loaded count and older-history availability are
shown above the transcript. Failed older loads retain the rendered history and
allow an explicit retry. **Reload messages** returns to the latest 20 and keeps
the chat draft; a completed chat also refreshes the latest page. Late responses
from another conversation or Agent are ignored.

The additive `GET /conversations/{id}/messages/page` endpoint requires `agent_id`,
accepts `limit` from 1 to 100 (default 20), and uses an exclusive `before_id`
cursor. Timestamp and ID ties are handled together. The legacy full-message
endpoint and the Runtime's complete conversation context stay available.
No dependency, database schema, model, or paid API changes are required.

```bash
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_message_pagination --base-url http://frontend
```

Equivalent: `make message-pagination-check`. The first run creates three
uniquely marked conversations and 46 saved fixture messages, with no chat
executions or model requests. Eight checks walk all 45 main-history messages,
verify an empty history and a foreign scope, and preserve all existing rows,
vectors, and checkpoint files. Restart the services without deleting the SQLite
volume and immediately run the same command with `--verify-persistence`.
The checkpoint is `message-pagination-acceptance.json` beside SQLite.
Restart/reuse performs only reads, expects the original IDs and fingerprints,
and fails on missing or changed data without recreating fixtures. Keep the
initial/restart pair idle; subsequent normal activity changes its strict
fingerprint. Older acceptance checkpoints are preserved byte for byte.

## Export a complete conversation

Select **Export JSON** or **Export Markdown** under **Conversation Chat** to
download all saved messages, including history not yet loaded on the page. JSON
preserves structured metadata; Markdown preserves the transcript as literal text.
Exports keep unsent drafts and do not execute chat. Empty conversations are valid;
foreign conversations are rejected. See [export instructions](docs/conversation-export.md)
for the API contract, limits, and eight-check initial/restart Docker acceptance.

Run `make conversation-export-check` against the existing running demo. The first
run adds three fixture conversations and 26 messages; restart verification is
read-only and checks that both formats retain their original bytes.

## Import a conversation backup

Choose an Agent and a **Conversation JSON backup**, inspect its title and saved
message count, then select **Confirm import as new conversation**. A new local
conversation retains the backup's message roles, text, timestamps, and full history.
The selected chat, loaded messages, and all drafts remain available. Find the new
conversation by its title after import. JSON schema version 1 supports up to
10,000 messages and 10 MiB; Markdown is a readable export format.

Imports use new local IDs and the explicitly selected destination Agent. Existing
records, memories, cached vectors, executions, and source backup files remain
available. Importing does not run chat or extract memories. No migration or new
dependency is required. See [import instructions](docs/conversation-import.md).

`make conversation-import-check` imports three marked fixture conversations and
50 messages with zero chat executions. Eight checks verify a real export/import
round trip, original text and timestamps, scope, empty history, a valid upload
larger than 1 MiB through Nginx, validation errors, and preserved existing data.
Restart verification is read-only and retains the original local IDs and all six
export hashes. Keep the initial/restart pair idle and retain its checkpoint.
