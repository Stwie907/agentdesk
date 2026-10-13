# Local Ollama model diagnostics

The runtime settings view reports configuration. A separate, explicit model
check reads the configured local Ollama inventory with `GET /api/tags`.
Installation observations do not certify chat inference, available memory,
embedding capability or future service health.

## Contract

`GET /runtime/ollama` optionally accepts a positive saved `agent_id`.
The version-1 response contains `read_only: true`, `inference_performed: false`,
provider, selected Agent ID, retrieval mode, connection status and model checks
for saved Agent chat, configured planner and configured embedding roles.

- Ollama: one explicit inventory request, redirects disabled, proxy environment
  disabled, connect/read timeout capped at five seconds, inventory bounded to
  1 MiB and 1,000 rows.
- Mock: `not_required`, no inventory request and `model_probe_performed: false`.
- Keyword retrieval: the embedding role is `not_required`.
- No selected Agent: chat is `not_selected`; global diagnosis performs no SQL.
- A scoped diagnosis uses one Agent SELECT and never writes records or vectors.
- A successful inventory read reports `installed` or `missing` for required
  models. Failed connection, timeout, upstream HTTP error or malformed inventory
  reports `unknown`, not `missing`.
- Bare model names match their `:latest` alias. Explicit tags match exactly.
- Raw upstream bodies, endpoints, credentials and database paths are omitted.
- Invalid settings return redacted 503; missing Agent returns 404; invalid ID
  returns 422. Successful responses are uncached JSON with `nosniff`.

`/runtime/config` keeps its previous no-probe contract, and `/health` keeps its
existing liveness response. Existing `/runtime/` Vite and Nginx routing covers
the additional endpoint.

## Browser steps

1. Open `http://localhost:5173` and select the saved **Agent 1** at the top.
2. Use the **运行配置** navigation entry and **Show runtime configuration**.
3. Click **检查本地 Ollama 模型**. Expected local models are chat/planner
   `qwen2.5:7b` and, in Semantic mode, `embeddinggemma` or its `:latest` alias.
4. Select conversation 16 and enter unsent chat and unfinished title drafts.
   Repeat the explicit model check; selection and both drafts must remain.
5. Refresh runtime settings, change Agent or hide the panel. Old model results
   are cleared and pending reads cancelled. A fresh model check needs another
   explicit click. Returning to an Agent follows the existing draft-saving rules.

The model check starts idle. It is not run at startup, when settings are opened
or refreshed, when another Agent is selected, or when the panel is reopened.
Only the model-check button requests inventory. Model checking does not send
chat, download/install models, produce embeddings, populate vector caches or
create acceptance checkpoints.

## Existing-data Docker acceptance

Use the same persistent SQLite volume and the original saved Agent. The checker
will not create an Agent, chat or fixtures. Keep the original data volume during
restart and keep provider/retrieval settings identical between runs.

```bash
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_runtime_configuration --base-url http://frontend --agent-id 1 \
  --expected-provider ollama --expected-chat-model qwen2.5:7b \
  --expected-planner-model qwen2.5:7b --expected-memory-mode semantic --expected-vector-cache true &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_ollama_diagnostics --base-url http://frontend --agent-id 1 \
  --expected-provider ollama --require-installed
```

For restart, run `docker compose -f docker-compose.yml down`, then repeat the
same block without `--build`. Do not add `-v`: the original volume is required.
Expected checks are message search 10/10, runtime configuration 8/8 and model
diagnostics 8/8. Each preserves SQLite records, vectors and retained checkpoints,
with zero new conversations/messages/chat executions. The configuration digest
stays equal to its previous result. If inventory stays unchanged, diagnostics
digests must also match before/after restart.

Model diagnostics acceptance reads the inventory twice (global and Agent scope)
and settings once. With `--require-installed`, unreachable or missing required
models make it fail with a redacted report. Inspect the diagnostic panel and
local installation before retrying; the checker does not repair or seed data.

`make ollama-diagnostics-check` performs the required-installation check for
Agent 1. Override `OLLAMA_DIAGNOSTICS_AGENT_ID` for another saved Agent.
For Mock, set `OLLAMA_DIAGNOSTICS_ARGS='--expected-provider mock'`.

## Reference

Ollama's model inventory endpoint:
<https://docs.ollama.com/api/tags> (checked 2026-10-11).
