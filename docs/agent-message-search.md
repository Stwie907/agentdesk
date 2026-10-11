# Search saved messages across an Agent's conversations

**Search all Agent conversations** appears under **Conversation Chat**, directly
above **Conversation title search**. Select an Agent in the top task form first.
A conversation selection is optional. This searches saved message content across
all conversations belonging to that Agent.

## API contract

`GET /agents/{agent_id}/messages/search`

| Parameter | Contract |
| --- | --- |
| `agent_id` | Required positive signed 64-bit SQLite path ID; a missing Agent returns 404. |
| `query` | Literal content fragment of 1 to 200 characters; surrounding whitespace is trimmed and NUL is rejected. |
| `role` | Omit for every saved role, or use `user`, `assistant`, `system`, or `tool`. |
| `limit` | 1 to 50, default 10. |
| `offset` | 0 to the signed 64-bit maximum, default 0. |

Invalid parameters return 422. English ASCII letters ignore case; Chinese and
other non-ASCII characters match literally. Percent signs, underscores, quotes,
backslashes, and code/script-looking text are ordinary text rather than patterns.
Titles do not participate in content matching. Empty and beyond-final pages are
successful empty results; a missing Agent is an explicit 404.

The response includes `agent_id`, normalized `query`, `role`, `limit`, `offset`,
`total`, `has_more`, and `items`. Each item preserves message ID, conversation ID,
role, and timestamp, and adds its actual `agent_id` and saved `conversation_title`.
It carries a preview of at most 240 Unicode characters, code-point match positions,
and truncation flags. Previews do not replace complete saved content.

Results are newest first by `created_at, id`, including timestamp ties across
conversations. An Agent lookup, scoped count, and bounded joined page avoid
per-conversation queries or Python filtering of every transcript in the API.
Responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
Offset pagination reads current saved history rather than a frozen snapshot;
normal concurrent writes can change later pages, so explicitly search again.

Full message, surrounding context, and context downloads reuse the existing
conversation-scoped endpoints, passing the result's conversation ID and current
Agent. Another Agent cannot appear in the requested Agent's result set. This
follows the local workbench scope and does not add authentication. No migration,
dependency, chat, memory extraction, embedding, or model call is added.

## First use in the browser

1. Open `http://localhost:5173`. In the top **Agent** dropdown select your existing
   demo Agent, normally **Demo Agent (ID: 1)**.
2. Under **Conversation Chat**, find **Search all Agent conversations**. Enter
   `turn 01` in **Agent message content search**, including the space. Leave
   **Agent message role** at **All roles**, then click **Search Agent messages**.
   This uses the Agent message field, separate from title and memory search.
3. Results show **Conversation ID: title**, message ID, role, timestamp, and the
   highlighted literal match. Identify the original imported result using
   `older_message_id` and `original_conversation_id` from the acceptance report.
4. Click **Read full Agent message ID** to inspect complete text. Click **Read
   Agent message context ID** to load neighbours. The original oldest imported
   message shows four messages with the default three-per-side counts.
5. After context loads, click **Export context JSON**, then **Export context
   Markdown**. Filenames identify the result's conversation and selected message.
   These remain excerpts; complete-conversation **Export JSON** remains the
   importable backup format.

All actions submit explicitly. Editing query, role, or size clears stale results
and pending detail/context/download requests without submitting a new search.
Errors preserve drafts and allow explicit retries. Another Agent starts a new
Agent search. Saved-data writes and reloads invalidate old evidence; ordinary
conversation title browsing retains Agent results and displayed context.

## Initial and restart acceptance

Retain original JSON import, message-search, surrounding-context, and context-export
fixtures and checkpoints beside the persistent SQLite database:

- `conversation-import-acceptance.json`
- `conversation-message-search-acceptance.json`
- `conversation-message-context-acceptance.json`
- `conversation-message-context-export-acceptance.json`

If a required source is missing, finish that milestone's initial/restart pair
first. The preceding context-export milestone must have written its checkpoint.
Do not regenerate an existing file merely to satisfy a later check, or rerun old
full-database snapshot checks after unrelated normal writes. This checker verifies
their original response bytes directly.

Existing bilingual fixture messages must span at least two conversations of the
main Agent. Earlier message-pagination/export/import acceptance leaves these
records. The checker creates no new fixture, message, conversation, or execution.
Its first successful run writes only `agent-message-search-acceptance.json`.

From the repository root, retaining your local Ollama configuration:

```bash
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend
```

Expect `status: passed`, `checks_passed: 10`, at least two matching conversations,
original 25 saved/20 loaded messages and the original older message ID, 57 preserved
prior responses including 18 context attachments, four validated cross-conversation
context downloads, and zero created records. Matching message/response counts
depend on retained local history. Keep `response_sha256` and `source_checkpoint_sha256`.

Immediately recreate both services with the SQLite volume retained and without
normal writes between the pair:

```bash
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence
```

Restart must pass ten checks with identical digests, original fixture IDs, records,
vectors, and all previous checkpoints. `persistence_verified` and `checkpoint_reused`
must be true. Missing verification/source files fail before HTTP. Changed records,
files, or saved response evidence fail without repair. Unrelated normal activity
before the first new check can become its baseline when original fixtures and all
57 prior response hashes remain intact.

`make agent-message-search-check` targets an existing Mock demo. CI runs this pair
after the earlier context-export pair. Chat remains local Ollama `qwen2.5:7b`;
this read-only feature itself makes zero model requests.

## Remaining browser checks after the idle automated pair

1. Before searching, select the report's original conversation in **Conversation**.
   If it is outside the first ten titles, set **Conversations per page** to 20 or
   use **Next conversations**. Confirm **20 messages loaded**. Enter distinct
   drafts in **Chat message**, **Conversation title**, **New conversation title**,
   and **Conversation title search**, without submitting those forms.
2. Search `中文` in **Agent message content search**. Use **Agent search results
   per page** and **Next Agent matching messages** to find a result in the report's
   `other_conversation_id`. Read its full message/context and export both formats.
   Confirm the **Conversation** selection, 20-message transcript, four drafts,
   and Inspector selection are retained. Downloads must identify the other
   conversation rather than the active chat.
3. Set **Agent message role** to **Assistant**, then click **Search Agent messages**.
   Results match the role; context may include neighbouring user messages. Set
   both context count controls to 0, click **Reload message context**, and export
   one message. For a middle imported result, set both counts to 10, reload, and
   export 21 messages.
4. During a pending context download, change the Agent query, role, size, close
   context, or switch Agent. A late response must not download a file. Retry
   network failures explicitly. Saved titles, queries, roles, and contents render
   as literal text.
5. Search a title-only phrase in **Agent message content search** to check that
   titles are metadata. Existing **Conversation title search** and the selected
   conversation's **Message content search** remain separate controls.
