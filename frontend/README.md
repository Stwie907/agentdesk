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
