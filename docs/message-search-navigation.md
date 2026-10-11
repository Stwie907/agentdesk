# Open a saved search result in its original conversation

Under **Conversation Chat**, search in **Search all Agent conversations** and
choose **Open message ID in chat** on a result. The UI selects that result's
original conversation, focuses **Located saved message in chat**, and loads its
saved context. Default context includes up to three messages before and after
the selected message, with original IDs, roles, timestamps, and full text.

## Scope and behaviour

- The client reads `GET /conversations/{conversation_id}?agent_id={agent_id}` and
  `GET /conversations/{conversation_id}/messages/{message_id}?agent_id={agent_id}`
  before changing selection. It verifies Agent/conversation/message identities
  and the saved role, timestamp, and preview against the full body. A refreshed
  saved title is used for the target conversation.
- A result outside the current title page becomes the selected conversation
  without changing the title query or page. Conversation selection is optional
  before the first navigation.
- A different conversation loads its latest 20 messages using the existing
  cursor API. The located context is a separate saved excerpt. Opening an older
  message does not merge context rows into the chat transcript or fetch every
  history page. **Load older messages** remains available.
- Opening another result in the already selected conversation retains its
  loaded older pages. A target already in the loaded transcript is marked.
- **Close located message** closes the excerpt and keeps the selected chat and
  its drafts. Context controls and JSON/Markdown downloads retain their existing
  validation and filenames.
- Navigation uses read-only scoped APIs, makes no model/embedding call, and
  preserves Inspector selection. It adds no backend endpoint, migration, or
  dependency. FastAPI, React/TypeScript/Vite, SQLite, local Ollama qwen2.5:7b chat,
  and zero paid APIs remain the project constraints.

## Draft lifetime

Within the currently selected Agent, unsent **Chat message** and **Conversation
title** drafts are retained separately for each conversation. Returning through
search navigation or the ordinary **Conversation** selector restores exact text,
including whitespace. A conversation with no rename edits uses its fresh saved
title. The **New conversation title**, title-search draft, and Agent-search
controls remain available during navigation.

These are browser session drafts, not SQLite records or persistent backups.
Changing Agent or reloading the browser starts a fresh draft session. Successful
sends clear the sent chat draft; successful renames update that conversation's
rename draft; deletion removes the deleted conversation's drafts. Existing
write-failure draft retention continues to apply.

## Pending requests and errors

Duplicate navigation clicks are blocked. **Cancel opening message**, changes to
the Agent query/role/size, clearing results, manual conversation selection, data
reloads, write/delete locks, Agent changes, and unmounting invalidate pending
navigation. Cancellation is checked after both scoped reads even if transport
returns a late response. Existing preview/context inspection also cancels a
pending navigation. A late response cannot switch selection or create a download.
An older title-page response cannot replace a newer navigation selection or its
refreshed saved title.

A network error, missing saved record, changed message, or foreign scope retains
the current chat and all drafts; retry **Open message ID in chat** explicitly.
Closing located context, changing conversation, data invalidation, writes, or
Agent changes cancels pending context reads/downloads. Changing an Agent search
query after completed navigation keeps the currently opened chat context.

## Retained HTTP evidence before manual navigation

This frontend milestone reuses the successful Agent message search checkpoint
`/data/agent-message-search-acceptance.json` and its original predecessor files.
Both checks below use `--verify-persistence`: neither creates or replaces an
acceptance file. Finish the Agent search initial/restart pair first if that
checkpoint is missing. Keep existing evidence when a check reports changes;
verification does not repair or regenerate it.

From the repository root, retaining local Ollama configuration and the original
database volume, rebuild and verify:

```bash
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence
```

Expect `status: passed`, `checks_passed: 10`, `persistence_verified: true`, and
`checkpoint_reused: true`. Keep `response_sha256` and `source_checkpoint_sha256`.
Original 25 saved/20 loaded messages, original conversation/message IDs, 57 prior
responses including 18 context attachments, four downloads, and zero new
conversation/message/execution records remain verified. Matching counts depend
on saved history; use the actual report rather than hard-coded fixture IDs.

Immediately recreate services without normal writes between the pair:

```bash
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence
```

Expect the same ten passing checks, original IDs, and both digests. Checkpoints,
SQLite rows, and cached vectors stay unchanged. Existing CI still runs the full
frontend suite/build and Agent search initial/restart acceptance. This HTTP
checker verifies saved data and API behaviour; browser navigation and draft
restoration are checked below and in frontend regression tests.

## Exact browser checks after the idle HTTP pair

1. Open `http://localhost:5173`. Select the original **Demo Agent** in the top
   **Agent** dropdown, using `agent_id` from the acceptance report.
2. Under **Conversation Chat**, choose the report's `original_conversation_id`
   in **Conversation**. Use **Conversations per page** 20 or **Next conversations**
   if its title is outside the first page. Confirm **20 messages loaded**.
3. Type `Main chat draft - do not send` in **Chat message**, `Main rename draft`
   in **Conversation title**, and `Create draft` in **New conversation title**.
   Leave the Send, Rename, and Create buttons untouched.
4. Find **Search all Agent conversations** above **Conversation title search**.
   In **Agent message content search**, enter `turn 01` with a space. Leave
   **Agent message role** at **All roles** and click **Search Agent messages**.
5. On the result matching `original_conversation_id` and `older_message_id`,
   click **Open message ID in chat**. For the previously reported local records,
   this is normally **Open message 90 in chat**, opening conversation 16.
   **Located message ID in conversation ID** receives focus. The original oldest
   message's default context shows four messages; the loaded chat stays at 20.
   Its chat/rename drafts remain exact because this opens the same conversation.
6. Inside **Located saved message in chat**, click **Export context JSON** and
   **Export context Markdown**. Download filenames identify the selected original
   conversation/message. Use **Close located message** and confirm chat/drafts stay.
7. Search `中文` in **Agent message content search**. Set **Agent search results
   per page** to 50, then click **Search Agent messages** again. Use **Next Agent
   matching messages** if needed to find `other_conversation_id/other_message_id`
   from the report (previously conversation 10/message 18).
8. Click that result's **Open message ID in chat**. **Conversation** changes to
   the other conversation and located context identifies its actual scope. Type
   `Other chat draft - do not send` and `Other rename draft` into its chat/title
   fields. Export both context formats and verify their conversation/message IDs.
9. To return, search `turn 01` explicitly and open the original older result
   again. The main chat and rename drafts from step 3 must reappear, and
   **New conversation title** still contains `Create draft`. Reopen the other
   result and check its separate drafts. Inspector selection must stay unchanged.
10. Repeat with a result outside the current title filter/page; the target should
    remain selected through **Current conversation**. With browser network
    throttling, start opening a result, then choose **Cancel opening message**,
    edit the Agent query, or select another conversation. A late reply must not
    change selection. Close located context during a download and check that no
    late file appears. These browser checks require separate manual evidence.
