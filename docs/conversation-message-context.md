# Surrounding context for saved conversation messages

Search the complete saved history, then choose **Read surrounding messages ID**
beside a result. A separate region shows the selected message and nearby turns
in chronological order, including messages outside the loaded chat page.
All roles are included. Text is literal, and the selected message is marked.

The active conversation, loaded chat, search results, title filter, and unsent
chat/rename/create drafts remain available. Each side defaults to three messages.
Choose 0, 1, 3, 5, or 10 under **Messages before selected** and **Messages after
selected**, then choose **Reload message context**. Count changes clear stale
context without an automatic request. **Close message context** leaves the
search results available. Failures preserve drafts and allow an explicit retry.

## API contract

`GET /conversations/{conversation_id}/messages/{message_id}/context`

| Parameter | Contract |
| --- | --- |
| `conversation_id`, `message_id` | Positive signed 64-bit SQLite path IDs. |
| `agent_id` | Required positive signed 64-bit ID; must own the conversation. |
| `before`, `after` | Independent integer counts from 0 to 10; each defaults to 3. |

Response fields: `conversation_id`, `agent_id`, `anchor_message_id`, `before`,
`after`, `anchor_index`, `has_more_before`, `has_more_after`, and `items`.
Items contain complete original message identities, roles, content, and timestamps.
They are strictly ascending by `(created_at, id)`. The anchor appears exactly
once at `anchor_index`. Missing or foreign anchors, including another conversation
of the same Agent, return 404. Invalid identities/counts or omitted Agent scope
return 422. Responses use `Cache-Control: no-store` and `nosniff`.

Each neighbour SQL query is limited to its count plus one row; at most 21 messages
are returned. A zero count still reports whether messages exist on that side.
Full contents can be large, so the bound is on messages rather than text bytes.
Reads reflect current history; reload context after another client changes it.
No migration, dependency, chat, memory extraction, embedding, or paid API is added.
Ollama chat remains `qwen2.5:7b`.

## Initial and restart acceptance

Keep the original `conversation-import-acceptance.json` and
`conversation-message-search-acceptance.json`, their 25-message fixtures, and
all earlier checkpoints beside SQLite. Finish their initial/restart pairs first.
The new checker reuses their original IDs and 30 search/detail/export hashes.
It makes only GET requests and creates zero database records in both runs.
Initial acceptance writes only `conversation-message-context-acceptance.json`.

From the repository root with the existing local Ollama setup:

```bash
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
  docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_message_context --base-url http://frontend
```

Expected: `status: passed`, `checks_passed: 9`, saved/loaded counts 25/20,
older/newest/middle/maximum context counts 4/4/7/21, nine context responses,
30 preserved responses, `read_only: true`, and zero created conversations,
messages, or chat executions. Original records, cached vectors, and prior files
remain unchanged. Keep the reported conversation/older-message IDs and digests.

Immediately restart without chatting, editing, importing, or other writes:

```bash
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
  docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_message_context --base-url http://frontend --verify-persistence
```

Keep the SQLite volume. Restart must reuse the same IDs, digests, records, and
checkpoint bytes, with `persistence_verified` and `checkpoint_reused` true.
Missing or changed records, vectors, responses, or source/prior checkpoints fail
without repair or replacing evidence. Missing context evidence with
`--verify-persistence` fails before HTTP. Missing import/search evidence also
fails before HTTP, including on the initial run.

Unrelated activity before this new milestone is allowed while original fixtures
and response evidence remain intact; it becomes part of the new SQLite baseline.
Activity after initial acceptance changes that strict baseline. Do not rerun old
full-database snapshot checkers after later milestones or normal writes. Their
original files remain preserved. If the context checkpoint is removed, a normal
initial run can establish a new read-only baseline; use `--verify-persistence`
to prove retention of the original evidence.

For an existing running Mock demo, `make message-context-check` runs the same
checker. CI performs its initial/restart pair after message-search persistence.

## Manual browser acceptance

Complete the automated pair first, then open `http://localhost:5173`:

1. Select the reported original conversation and confirm only 20 chat messages
   are loaded. Enter chat, rename, new-title, and title-search drafts.
2. Search `turn 01` and choose **Read surrounding messages** for the reported
   older ID. Expect four complete messages with the first marked as selected.
   Literal `<script>` text must display without executing.
3. Confirm the chat still has 20 loaded messages and all drafts/selection remain.
   Close context; the search results remain available.
4. Search `中文备份` with the Assistant filter and open context for an assistant
   result. The context includes neighbouring user turns as well.
5. Select zero messages before and after, then explicitly reload: only the anchor
   remains. A middle anchor with 10 on each side returns at most 21 messages.
6. Change the search/counts, close context, or switch conversation/Agent while
   loading. Late results must not reappear. Retry a failed read explicitly.
