# Read current Runtime configuration

For an explicit inventory check, use **检查本地 Ollama 模型** after opening
settings. See [local model diagnostics](ollama-diagnostics.md). This separate
check does not change the `/runtime/config` no-probe contract.

Under **Submit Task**, find **Runtime Configuration** and click **Show runtime
configuration**. The panel starts collapsed and adds no configuration request to
startup. **Refresh runtime configuration** reads current settings again. An open
panel also reloads when the selected **Agent** changes. Hiding the panel, changing
Agent or leaving the page cancels the old read and ignores its late result.

The panel distinguishes:

- **LLM provider**: Ollama or explicitly simulated Mock.
- **Selected Agent chat model**: the actual saved `Agent.model`, rather than the
  planner model. Without an Agent, global settings remain available.
- **Configured planner model**: `OLLAMA_PLANNER_MODEL`. Mock uses its existing
  rules and simulated responses; showing a configured model does not run it.
- **Memory retrieval mode**: keyword or semantic.
- **Configured embedding model**: `OLLAMA_EMBEDDING_MODEL`.
- **Active embedding model**: unused in keyword mode, `mock-fixtures-v1` for Mock
  semantic retrieval, or the configured local embedding model for Ollama.
- **Vector cache setting** and **Vector cache activity**: a cache setting can be
  enabled while keyword retrieval leaves the vector cache inactive.
- **Configured minimum similarity** and the database dialect, without its path.

These are configuration observations. No model installation, availability,
connection or inference test is performed. Use the existing real Ollama memory
and vector-cache acceptance checks to verify actual model behaviour. Reading
configuration cannot switch providers, edit settings or submit a task.

## API and scope

`GET /runtime/config` returns version-1 global settings with `selected_agent:
null`. `GET /runtime/config?agent_id=ID` also returns that Agent's saved chat
model. Invalid IDs return 422 and missing Agents return 404. Invalid LLM or memory
configuration returns a redacted 503 without silently falling back to Mock.
`/health` retains its existing liveness response.

Successful responses include `Cache-Control: no-store` and
`X-Content-Type-Options: nosniff`. Endpoints, credentials, unrelated environment
variables and SQLite filenames are excluded. No model/provider request or record
write occurs. An unscoped read executes no SQL; a scoped read uses one existing
Agent lookup. This endpoint uses the same local application's existing access
model; it adds no authentication or remote service.

Both Vite development proxying and production Nginx forward `/runtime` to FastAPI.
The browser validates schema, booleans, provider, selected Agent and coherent
embedding/cache activity before displaying settings. Failure stays local to this
panel and does not change chat/title drafts, conversation selection or Inspector.

## Read-only local acceptance

Use the existing SQLite volume and an existing saved Agent. The checker will not
seed missing Agents, repair settings or create an acceptance checkpoint. Run it
from the backend container so its local database is the same one served by API.
The original retained-checkpoint acceptance should run before browser editing or
any new chat, rename, deletion or import.

For the original Agent 1 and real local Ollama setup:

```bash
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_runtime_configuration --base-url http://frontend --agent-id 1 \
  --expected-provider ollama --expected-chat-model qwen2.5:7b \
  --expected-planner-model qwen2.5:7b --expected-memory-mode semantic --expected-vector-cache true
```

Immediately recreate services, retaining the volume, and repeat both reads:

```bash
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_runtime_configuration --base-url http://frontend --agent-id 1 \
  --expected-provider ollama --expected-chat-model qwen2.5:7b \
  --expected-planner-model qwen2.5:7b --expected-memory-mode semantic --expected-vector-cache true
```

The original checker must still pass 10 checks with reused persistence evidence
and matching original digests. The configuration checker must pass 8 checks in
both runs with matching `response_sha256`, `read_only: true`,
`model_probe_performed: false`, unchanged records/vectors/checkpoints, and zero
new conversations, messages or chat executions. It prints a report but writes no
checkpoint. A changed database or checkpoint during the read makes it fail.
Keep failures for inspection rather than recreating fixtures or deleting data.

`make runtime-config-check RUNTIME_CONFIG_AGENT_ID=1` performs the same read-only
check without asserting provider/model/mode expectations. Defaults are keyword
retrieval and an enabled cache setting, which is inactive in keyword mode.

## Browser acceptance

1. Open `http://localhost:5173` in the same browser/profile used for drafts.
2. Select original **Agent 1** in the **Agent** dropdown under **Submit Task**.
3. Directly below that form, find **Runtime Configuration**. Click **Show runtime
   configuration**. Expect Ollama, Agent ID 1, chat and planner `qwen2.5:7b`,
   Semantic, embedding `embeddinggemma` (or your configured local model), an
   enabled and active cache, and SQLite. Model availability remains unchecked.
4. Click **Refresh runtime configuration**; the same settings must return.
5. Under **Conversation Chat**, select original **Conversation 16**. Enter an
   unsent **Chat message** and unfinished **Conversation title**. Refresh the
   configuration panel again; both texts and conversation selection must stay.
6. Choose a different Agent at the top. The open panel must show only that
   Agent's ID/chat model, or its explicit loading/error state. Return to Agent 1.
7. Click **Hide runtime configuration**, then show it again. These actions must
   not send chat, rename or change Inspector selection.
8. Complete the reload, separate-conversation, Agent-isolation and confirmed-clear
   draft checks in [conversation-drafts.md](conversation-drafts.md). Re-select
   the original scope after each browser reload; new-conversation and search
   fields are not persisted. Use `turn 01` with a space under **Search all Agent
   conversations → Agent message content search** when checking original message
   90 in conversation 16.

FastAPI, React/TypeScript/Vite, SQLite, local Ollama qwen2.5:7b and zero paid APIs
remain the stack. No database migration, dependency or CI workflow change is
required. Keep backend and MCP Python environments separate.
