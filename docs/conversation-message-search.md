# Search complete saved conversation history

Select a conversation and use **Message content search** to find saved messages,
including history outside the latest 20-message page. Search results and full
message details are separate from the chat transcript. They retain the current
selection, loaded chat history, title filter, and unsent drafts.

## API and matching

- `GET /conversations/{conversation_id}/messages/search?agent_id=ID&query=TEXT`.
- Require a destination Agent scope and a trimmed, nonblank query of 1–200 Unicode
  characters. NUL is rejected. There is no blank-query full-transcript download.
- Literal substring matching ignores ASCII English case. Chinese, emoji, quotes,
  backslashes, percent signs, and underscores are literal text. Non-ASCII case
  remains distinct; this is not semantic retrieval, tokenization, or translation.
- Optional `role=user|assistant|system|tool`; omission includes every stored role,
  including custom roles in imported archives.
- `limit=1..50`, default 10; nonnegative `offset`, default 0. Return total count,
  `has_more`, and newest-first results ordered by timestamp, then message ID.
- Each preview contains at most 240 Unicode characters around the first match,
  code-point `match_start`/`match_end` offsets, and truncation flags.
- `GET /conversations/{conversation_id}/messages/{message_id}?agent_id=ID` reads
  one full message on explicit request, preserving its original content and time.
- Both endpoints disable caching. Missing/foreign conversations or message IDs
  return 404, including a message from another conversation of the same Agent.
  Invalid parameters return 422. No migration or dependency is required.

Pagination reflects current saved history. New activity in another client can
shift offsets; search again to refresh the count and first page. Requests load
only a bounded page of matched rows, plus a database count. The search uses the
existing SQLite tables without a new index or FTS extension; a large transcript
still requires scanning its content for an arbitrary substring.

## Workbench behavior

Typing, changing **Message role**, and changing **Search results per page** clear
old results without automatically searching. **Search messages** submits a GET.
**Previous matching messages** and **Next matching messages** browse that search.
**Read full message ID** displays a separate plain-text detail view; it does not
load older chat pages or change the active conversation.

Queries count emoji as Unicode characters. Previews highlight the match without
splitting an emoji. HTML, Markdown, code fences, CRLF, and trailing whitespace are
displayed as literal text. Failed requests retain search/chat drafts and need an
explicit retry. There is no automatic request on mount or after typing.

Query, role, page-size, Agent/conversation, history revision, and mutation changes
abort/invalidate old requests. Writes and deletion confirmation lock the search.
Reloading, importing, title filtering, or chat updates clear stale results while
retaining the search draft and filters. Choosing another conversation/Agent starts
a fresh search panel. Search and detail requests never run chat, extract memories,
generate embeddings, or call Ollama.

## Initial local Ollama acceptance

Use the existing completed JSON import checkpoint from Issue #142. The checker
reads its original main, empty, and foreign conversation IDs and all 50 message
IDs; it creates no fixture records. Do not rerun older strict snapshot checkers
after new manual activity. Their original evidence files remain retained.

After synchronizing develop and replacing the delivered files:

```sh
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_message_search --base-url http://frontend
```

Equivalent with the running Mock demo: `make message-search-check`.
The checker must access the same persistent SQLite database as the running API.

Expect nine passed checks, 25 complete messages, 20 messages in the loaded latest
page, 25 Chinese-query matches, 13 user matches, and 12 assistant matches. It reads
an original older message outside that loaded page. Initial and reused runs report
`read_only: true`, and zero new conversations, messages, or chat executions.

The first run writes only its new `conversation-message-search-acceptance.json`
beside SQLite (`/data` in Docker). Every original SQLite row/vector and every older
acceptance file must remain unchanged. The checkpoint records actual search,
detail, and six original export response hashes. It also keeps the hash of the
original import checkpoint. Normal reuse leaves this new file byte-identical.

The old import check's full-database fingerprint is not used as the new baseline:
normal activity before this milestone is allowed. Its original fixture records
and six exports must still match. The new checkpoint snapshots all current rows.

## Immediate restart verification

Keep the first/restart pair idle: no chat, import, rename, delete, other checker
writes, or other-client changes between them. Recreate services without deleting
the SQLite volume:

```sh
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_message_search --base-url http://frontend --verify-persistence
```

Expect nine passed checks, `persistence_verified: true`, `checkpoint_reused: true`,
`read_only: true`, zero created records, and identical response/source hashes.
Missing restart evidence fails before HTTP; changed records, response digests,
source/previous checkpoint bytes, or scoped results fail without overwriting
evidence or repairing records. A new normal run without its own checkpoint starts
a new baseline using the retained import records; it never recreates DB fixtures.

CI finishes the old import initial/restart pair, runs search acceptance, recreates
services, and verifies this new evidence, in that order.

## Manual browser acceptance

After both command checks pass:

1. Select `Demo Agent` and the original main `AgentDeskConversationImport-*` chat.
   Keep only its latest 20 messages loaded.
2. Keep unsent chat, rename, new-title, and title-search drafts on the workbench.
3. Enter `中文备份` in **Message content search**. Typing must make no request.
   Select **Search messages**: 25 matches should appear across three 10-row pages.
4. On the last result page choose **Read full message** for the original oldest
   message. Its code fence, Chinese/emoji, and literal `<script>` text appear in
   the separate detail view. The chat still has 20 loaded messages and all drafts.
5. Select **Assistant** under **Message role** and explicitly search again:
   expect 12 matches. Try `%` or `_`: expect zero because those characters occur
   in the title rather than the message text.
6. Search/clear/retry without sending chat. Confirm the selection, title filter,
   and drafts remain intact. Switch Agent: results and details must reset.

Keep FastAPI, React/TypeScript/Vite, SQLite, local Ollama `qwen2.5:7b` chat,
local embeddings, and zero paid APIs.
