# Conversation JSON backup import

Import an existing AgentDesk version-1 JSON export into the selected Agent as a
new conversation. The backup's original text, roles, timestamps, and complete
history remain available under fresh local conversation/message IDs. The selected
chat, loaded history, active title filter, and all drafts stay on the workbench.

## Scope and limits

- `POST /conversations/import?agent_id=ID`, with an `application/json` body.
- A successful 201 response contains `schema_version`, `conversation`, and
  `message_count` and disables caching.
- Accept only the complete version-1 JSON export structure. Markdown is a readable
  transcript and cannot be imported.
- Up to 10,000 messages and 10 MiB of actual UTF-8 request bytes. The Nginx proxy
  uses the same 10 MiB limit.
- The selected Agent is the destination. Source Agent/conversation/message IDs
  remain archive metadata and do not select existing local records.
- Preserve original naive UTC timestamps with up to six fractional digits and
  timestamp/source-ID order. Null legacy titles become `Imported untitled conversation`.
- Validate the entire file before writes. Reject duplicate JSON keys, unsupported
  versions, extra fields, count mismatches, foreign/duplicate/out-of-order messages,
  invalid UTF-8, lone surrogates, invalid timestamps, and non-integer IDs.
- Save the new conversation and all messages in one transaction; failed writes
  roll back partial inserts. No migration or dependency change is required.
- Preserve original conversations, memories, cached vectors, execution logs,
  snapshots, and replay history. Import does not run chat, call a model, extract
  memories, or execute the imported text.

Each explicit import creates another copy. The API is not idempotent. If the
connection fails after submission, reload conversations and inspect the imported
title before retrying. A submitted request keeps its original destination even if
you switch Agent; the frontend suppresses its late notification. Archives contain
conversation history, not execution/replay data or Agent memories.

## Local Ollama initial acceptance

Run against the existing initialized demo, after synchronizing develop and replacing
the delivered files. Keep the SQLite volume and existing acceptance checkpoints.
Complete older milestone restart pairs before adding these new import fixtures.

```sh
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_conversation_import --base-url http://frontend
```

Equivalent against the running services: `make conversation-import-check`.
The checker uses the existing `Demo Agent` and `MCP Order Agent` for scope tests.
It works under the existing Mock configuration too. Import/export makes no model
request under either provider, so these checks need no embedding generation.

Expected initial evidence:

- `status: passed`, `checks_passed: 8`.
- Three new fixture conversations and 50 new saved messages, zero chat executions.
- The main and foreign histories each contain 25 messages; the empty history has zero.
- The main latest page contains 20 messages, and complete exports contain all 25.
- `large_upload_bytes` is greater than 1 MiB: a padded valid empty backup traverses
  Nginx without adding large message content to the workbench.
- A real export/import round trip retains all roles, literal Chinese/emoji/HTML/code
  fences, CRLF, trailing whitespace, and microsecond timestamps.
- Invalid backup probes save no records. All original rows and vectors remain
  unchanged, and all earlier acceptance files remain byte-identical.
- Save `conversation-import-acceptance.json` beside SQLite (`/data` in Docker).

## Immediate restart verification

Keep the initial/restart pair idle: no chatting, imports, edits, deletions, or other
acceptance writes between them. Recreate services without deleting the volume:

```sh
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_conversation_import \
  --base-url http://frontend --verify-persistence
```

Expect eight passed checks, `persistence_verified: true`, `checkpoint_reused: true`,
`read_only: true`, and zero new conversations/messages/chat executions. Original
local IDs, every SQLite record/vector, previous checkpoint bytes, and all six
JSON/Markdown export hashes must remain unchanged. Successful normal checkpoint
reuse is also read-only. Missing/changed evidence fails without repair; existing
marked fixtures without their checkpoint cannot be recreated by a normal run.

Subsequent normal activity changes this full-database snapshot by design. Preserve
the original checkpoint as evidence rather than rewriting it. CI completes the
export restart check, runs initial import acceptance, then recreates services and
verifies the imports, so earlier strict snapshots are verified before new writes.

## Manual browser acceptance

After both command checks pass:

1. Select `Demo Agent` and the main `AgentDeskConversationImport-*` conversation.
2. Keep only the latest 20 messages loaded. Enter an unsent chat draft, a rename
   draft, and a new-conversation title draft.
3. Choose **Export JSON** and keep the downloaded backup.
4. Select that file under **Conversation JSON backup**. Confirm the preview reports
   25 saved messages and the current destination Agent. File selection alone must
   leave the conversation list unchanged.
5. Select **Confirm import as new conversation** once. Confirm a new conversation
   ID, the original current selection, 20 loaded messages, and all unchanged drafts.
6. Search for the imported title and explicitly select the new ID. Load earlier
   messages and compare all 25 with the source, or export it again and compare roles,
   text, and timestamps. Its generated IDs differ from the original.
7. Choose a Markdown file or malformed JSON: confirmation must remain unavailable.
   A failed server validation retains the preview and drafts for an explicit retry.

Keep local Ollama `qwen2.5:7b` chat, local embeddings, FastAPI, React/TypeScript/Vite,
SQLite, and zero paid APIs.
