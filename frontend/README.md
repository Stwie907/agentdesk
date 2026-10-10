# AgentDesk Frontend

React and TypeScript execution workbench for AgentDesk. It supports task
submission, execution history, filters, pagination, execution inspection,
structured traces, snapshots, replay, cancellation, retry, and automatic refresh.
The Agent Memory panel lists, adds, edits, deletes, and previews relevant persistent
memories for the Agent selected in the task form.

## Requirements

- Node.js 24.15 or later, below Node.js 25.
- npm 11 or later.

## Local development

From `frontend/`:

```sh
npm ci
npm run dev
```

Open the Local URL printed by Vite, normally `http://localhost:5173`.
Start the [backend](../backend/README.md) in a separate terminal. Vite proxies
`/agents`, `/executions`, `/memories`, and `/conversations` to
`http://127.0.0.1:8000`. If those requests report
`ECONNREFUSED` or status `502`, confirm that the backend completed startup.

## Conversation Chat

Select an Agent in the task form. Under **Conversation Chat**, enter a title of
1 to 200 characters and select **Create conversation**, or choose an existing
conversation. Its saved messages load in order. Enter a **Chat message** of
1 to 4000 characters and select **Send message** to continue the same history.

For example, send `My name is Tom`, followed by `I like Python`. Existing rules
save an Agent name/preference and refresh **Agent Memory** after each returned
execution. Questions such as `What do I like about Python?` do not create a new
preference. Each returned execution also opens in the Inspector and refreshes
execution history. One-off **Submit Task** continues to use its existing endpoint.

Select a conversation to edit **Conversation title** and choose **Rename
conversation**. The title allows 1 to 200 trimmed characters. Its ID, transcript,
selection, and chat draft are retained after a successful rename.

**Delete conversation** opens an inline confirmation with the title and ID.
**Cancel delete** makes no request; **Confirm delete** removes the conversation
and messages, then clears the selection and chat draft. Agent memories and
execution inspection remain available. Writes and selection are disabled while
a mutation is pending; other writes are also disabled during confirmation.
Rename/delete responses are checked for the selected conversation and Agent.

Writes are guarded against repeated clicks. A failed request retains its draft;
reload conversations/messages to check what was saved before retrying. A failed
execution retains the chat draft and opens its inspection. A transcript load
failure disables sending until recovery. Switching Agents resets the panel and
ignores old responses. A conversation change resets the chat draft.

Conversation and memory data use the same SQLite volume. Mock responses remain
fixed, while previous history and relevant memories reach the existing Runtime.
Ollama uses that context for generated replies. No paid service is added.

### Title search and paging

The panel uses the scoped `/conversations/page` endpoint to load 10 newest
conversations initially. **Conversation title search** applies a trimmed title
fragment only on **Search conversations**. A blank query or **Clear conversation
search** lists all titles for that Agent. Matching is literal, with ASCII English
case ignored and Chinese fragments supported. Message contents are not searched.

**Conversations per page** offers 5, 10, 20, and 50. **Previous conversations**
and **Next conversations** respect the returned count and page boundaries.
Search and size changes reset the offset. A failed page blocks writes until an
explicit successful retry. Scoped response validation rejects wrong metadata,
foreign rows, duplicate IDs, and inconsistent totals or boundaries.

The active chat lives separately from the page. Searching or paging keeps its
transcript and all drafts; an off-page selection is shown under **Current
conversation** with an explanatory message. Explicitly selecting another chat
clears its chat draft. Reload verifies an off-page selection; only a scoped 404
clears it, while other errors retain drafts and block writes.

Create clears the search and selects the new conversation on the first page.
Rename refreshes a filtered list without losing the selected transcript.
Delete reloads and fills the page, or returns to the preceding available page.
Browse controls are locked during writes and deletion confirmation. Agent
changes reset the panel and invalidate late page and write responses.

## Agent Memory

Select an Agent in the task form. Its memories load below that form. Enter, for
example, `I prefer concise Python answers.` and select **Save memory**. Content
must be non-blank and at most 2000 characters after trimming. Saving the same
content reuses the existing memory; a canonical `User's name is ...` entry follows
the backend's existing name replacement policy.

**Reload memories** loads the latest records, including changes made through
other API clients. **Delete memory** requires inline confirmation and sends the
selected Agent ID. A failed write retains the draft or record and is not retried
automatically. Switching Agents clears drafts and ignores responses from the
previous selection.

Memories use the existing backend SQLite database. In Mock mode, Runtime logs
can confirm relevant memory retrieval, but the reply remains the fixed `[MOCK]`
message. Use the existing local Ollama provider for model-generated replies.

### Edit saved memory

Select **Edit memory** beside a saved row. **Edited memory content** starts with
the original text. Enter 1–2000 trimmed characters, then **Save changes**.
**Cancel editing** sends no request; an unfinished add-memory draft is retained.
An unchanged draft cannot be submitted. Saving keeps the Memory ID and creation
time and clears the old retrieval preview without automatically searching again.

Only one record is edited at a time. Other writes and reloads wait until editing
ends; chat-triggered refreshes are deferred so they cannot erase the draft.
Requests include the selected Agent and the original saved content. Duplicate
or stale-content conflicts keep both the saved row and edit draft. Copy any draft
you want to retain, cancel editing, and reload to review the current record.
Failed requests are not retried automatically. Switching Agents starts independent
state and ignores both late success and late failure responses.

### Memory retrieval preview

Enter `Python` or `机器学习` in **Memory search query** and select **Search
memories**. The trimmed query allows 1 to 500 characters. **Result limit** offers
1, 3, 5, 10, or 20, with 5 selected initially. A search starts only on submission,
after the selected Agent's memory list has loaded; typing does not send requests.

Results show saved content, the Memory ID, **Keyword matches**, and **Matched
text**. This uses Runtime's shared keyword ranking. Scores count distinct
matching terms, and Chinese matches use character fragments; they are not
semantic confidence scores. An empty result does not clear the saved memory list.

Search sends a read-only GET and creates no chat message, execution, or memory.
Changing the preview limit does not change Runtime's default limit of 5.
Query/limit changes invalidate previous requests and results. Saving, deleting,
reloading, or refreshing memories after chat clears the preview while retaining
its draft and limit. Switching Agents resets both and ignores late responses.
Errors preserve the draft and require an explicit **Search memories** retry.
Returned scope, query, limits, ordering, scores, and match evidence are validated
before display. Content renders as plain text.

## Shared User Memory

Select an Agent, then **Show shared memories**. The panel starts collapsed and
fetches only after it is opened. Its owner label shows the resolved username/User
ID. Save a shared preference, then switch to another Agent of the same user:
the same record ID is visible. Another owner's Agents load a separate list.
Switching Agents resets drafts, edits, confirmations, and search state; late
responses from the previous selection are ignored.

Shared content permits 1–2000 trimmed characters. Exact duplicates reuse the row.
Editing sends original `expected_content` and both Agent/User scopes; saves keep
ID/time. **Cancel shared editing** makes no request and retains an add draft.
Blank, unchanged, or overlong edits are disabled. Writes and reloads wait while
saving. Failures preserve the draft; copy it before canceling and reloading.

**Delete shared memory** explains that deletion affects all Agents of the owner
and requires confirmation. **Shared memory search query** allows 1–500 characters
and returns up to five keyword-ranked matches. Searches run only on submission;
query changes, edits, and reloads invalidate stale responses. Response validation
rejects mismatched owners, identities, timestamps, queries, duplicates, and scores.

The existing Agent Memory panel and automatic extraction remain independent.
Save facts in this panel explicitly to share them. Vite and Nginx both proxy
`/user-memories` to FastAPI, including GET, POST, PATCH, and DELETE.

## Optional semantic previews

Select **Semantic (local embeddings)** in **Memory search method** or **Shared
memory search method**. The query and limit are sent to the scoped semantic
endpoint only after submission. Keyword is the initial selection.

Semantic results show **Cosine similarity**, the embedding provider/model, and
the server's Runtime memory mode. Mock results explicitly show **Mock fixture
vectors**. For Mock, save `I prefer concise answers.` and query `Keep it brief.`;
the Chinese pair is `我喜欢简洁的回答。` / `请用简短的方式解释。`. Ollama mode
supports general queries through the configured local embedding model.

Changing the method, query, limit, Agent, or saved-memory revision invalidates
older results. Embedding failures keep the query/method and show the server error;
retry is explicit. The client rejects non-finite/out-of-range similarity, wrong
scopes, metadata, duplicate IDs, and inconsistent ranking.

Preview selection is independent of Runtime configuration. Set the backend's
`MEMORY_RETRIEVAL_MODE=semantic` to use semantic retrieval during chat. The panel
shows the current server mode so users can distinguish these settings.

## Tests and production build

```sh
npm test
npm run build
```

## Docker Compose

From the repository root:

```sh
sh deployment/start-demo.sh
```

This builds the frontend and backend, waits for health, and initializes a
`Demo Agent` in Mock mode. Open `http://localhost:5173`.

The production container serves the Vite build with Nginx. `nginx.conf` forwards
API paths to the `backend:8000` Compose service, preserving paths and query
strings. It provides a `/healthz` endpoint for the frontend container and forwards
`/health` to the backend. The static workbench and API share the same browser
origin; the browser does not need to resolve Docker service names.

See [the Docker Compose guide](../docs/docker-compose-demo.md) for normal Ollama
mode, persistence, smoke checks, shutdown, and troubleshooting.

### Load older saved messages

The selected conversation initially requests its latest 20 messages using the
scoped `/conversations/{id}/messages/page` route. Messages display in ascending
timestamp/ID order. **Load older messages** prepends the next page and keeps the
chat, rename, and new-conversation drafts. The counter shows loaded messages
and whether earlier history is available. No full transcript fetch is needed
for this panel; legacy API callers and Runtime context keep their full history.

Older loads keep already rendered messages visible, block duplicate requests
and chat/management writes while loading, and support an explicit retry after
failure. Invalid scope, duplicate IDs, ordering, cursors, or overlapping
responses are rejected before they can enter the transcript. Timestamp checks
preserve microseconds. Conversation/Agent changes and **Reload messages**
ignore stale older responses. Reload keeps the unsent chat draft and returns
to the latest 20; a completed chat also refreshes that latest page. Conversation
title search/paging preserves already loaded older messages for the active chat.

## Download complete conversations

**Export JSON** and **Export Markdown** download the selected conversation's
complete saved transcript, including history outside the loaded 20-message page.
Unsent chat, rename, and creation drafts remain on the page. JSON downloads retain
structured IDs, roles, timestamps, and content; Markdown treats original text
literally, including Chinese, HTML, and embedded code fences.

Both buttons are disabled during an export or chat/management write and delete
confirmation. Failed exports preserve drafts and loaded history for retry.
Switching Agent/conversation cancels the request and suppresses late downloads.
Off-page selected conversations remain exportable. The client checks attachment
headers and validates JSON scope, count, ordering, timestamps, and message IDs
before creating a short-lived browser download URL. The existing frontend proxy
handles this API; no new dependency is required.

See [export acceptance and limits](../docs/conversation-export.md), including
manual validation of full history without loading earlier messages.
