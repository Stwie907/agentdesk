# Export a displayed saved-message context

Search saved messages and choose **Read surrounding messages ID**. When its
context is loaded, choose **Export context JSON** or **Export context Markdown**.
The download contains these complete saved messages in chronological order,
including the selected message and neighbours of every role. It can include an
older search result outside the latest 20 messages loaded in the chat.

Each side defaults to three neighbours. Select 0, 1, 3, 5, or 10 under the two
count controls, then choose **Reload message context** before exporting that
range. Zero/zero exports the selected message alone. Ten/ten exports at most 21
messages. Fewer messages are returned at the start or end of saved history.

The selected conversation, loaded chat, search results, title filter, Inspector,
and unsent chat/rename/create drafts remain available. Downloads start only
after a click and successful validation. Failed exports retain context and
drafts; retry explicitly. Duplicate/simultaneous format requests are guarded.
Count/search/scope/revision changes, reloading, closing, disabling, and unmounting
cancel pending requests. A late response cannot start a stale download.

These files are excerpts. For an importable backup, use the complete conversation's
**Export JSON**. Context JSON has a distinct export kind and is rejected by the
existing full-conversation import endpoint without creating records.

## API and attachment contract

`GET /conversations/{conversation_id}/messages/{message_id}/context/export`

| Parameter | Contract |
| --- | --- |
| `conversation_id`, `message_id` | Positive signed 64-bit SQLite path IDs. |
| `agent_id` | Required positive signed 64-bit ID; must own the conversation. |
| `before`, `after` | Independent integer counts from 0 to 10; each defaults to 3. |
| `format` | `json` or `markdown`; JSON is the default. |

The endpoint reuses the existing scoped context window. The anchor appears once
at `anchor_index`, and timestamps/IDs determine order. Each neighbour query uses
`LIMIT requested_count + 1`; the anchor lookup is also bounded. Existing search,
context, message pages, full-conversation exports/imports, and chat remain available.

Attachments use UTF-8 and a safe filename:
`conversation-ID-message-ID-context.json` or `.md`.
They include `Content-Disposition: attachment`, `Cache-Control: no-store`,
`X-Content-Type-Options: nosniff`, `X-Conversation-ID`, `X-Agent-ID`,
`X-Anchor-Message-ID`, `X-Message-Count`, `X-Context-Export-Kind`, and
`X-Context-Export-Schema-Version`.

JSON has four fields: `export_kind: "agentdesk.message_context"`,
`schema_version: 1`, `message_count`, and `context`. The context is the complete
existing context response, including identities, requested counts, anchor index,
remaining-history flags, and original message fields. It contains no export-time
clock value, so unchanged saved context produces deterministic bytes.

Markdown includes the same scope, range, anchor, flags, and count metadata.
Each complete original role/content is inside a `text` fence longer than any
backtick run in that value. The selected message has its own marker. Unicode,
HTML-looking text, code fences, microseconds, empty/custom roles, empty contents,
CRLF, and trailing spaces are preserved in the attachment.

Invalid/missing scope, IDs, counts, or format return 422. Missing/deleted/foreign
anchors, including another conversation of the same Agent, return 404.
Attachments larger than 10 MiB of UTF-8 bytes return 413; no partial attachment
is returned. Message count is bounded, while individual contents remain complete.

The browser validates headers, UTF-8, the 10 MiB bound, schema/context metadata,
and all contents against the displayed context before starting the download.
JSON uses the shared strict context validator; Markdown must match the complete
expected literal excerpt. A valid but changed saved window produces a client-side
409 error asking for **Reload message context**. Direct API exports read current
saved history; the endpoint does not add a frozen historical snapshot.

No database migration, dependency, chat execution, memory extraction, embedding,
or model request is added. Keep FastAPI, React/TypeScript/Vite, SQLite, local
Ollama `qwen2.5:7b` chat, local embeddings, and zero paid APIs.

## Initial and restart acceptance

Finish the earlier import, message-search, and context acceptance pairs first.
Keep their original `conversation-import-acceptance.json`,
`conversation-message-search-acceptance.json`, and
`conversation-message-context-acceptance.json` beside the persistent SQLite DB,
with all other original checkpoint files and fixture records.

The new checker reuses original import IDs and verifies 30 earlier search/detail/
full-export hashes plus nine original context hashes. It requests nine context
windows in both formats: 18 attachments. All HTTP requests are GET, including
scope/validation probes. Both runs create zero conversations, messages, or chat
executions. Initial acceptance writes only
`conversation-message-context-export-acceptance.json`.

From the repository root using the existing local Ollama configuration:

```bash
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_message_context_export --base-url http://frontend
```

Expected: `status: passed`, `checks_passed: 10`, saved/loaded counts 25/20,
oldest/newest/middle/maximum context counts 4/4/7/21, nine windows, 18 attachment
responses (nine per format), 39 preserved earlier responses, `read_only: true`,
and zero created records. Keep the reported original conversation/older-message
IDs, `attachment_sha256`, and `source_checkpoint_sha256`.

Immediately recreate both services without normal writes between the two runs:

```bash
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_message_context_export --base-url http://frontend --verify-persistence
```

Retain the volume. Restart must reuse identical attachment/source digests, original
fixture IDs, SQLite records and cached vectors, source checkpoints, all earlier
checkpoint files, and its own checkpoint bytes. `persistence_verified` and
`checkpoint_reused` must be true. Missing own verification evidence or missing
source checkpoints fails before HTTP; changed saved evidence fails without repair.

Unrelated activity before this milestone can become its new complete SQLite
baseline while the original fixtures and 39 response hashes remain intact.
After initial acceptance keep the pair idle. Older global-snapshot checkers may
predate normal activity: do not regenerate their files or rerun them to establish
this milestone. The new checker replays their actual response hashes directly.
If its own checkpoint is removed, a normal initial run can establish a new
read-only baseline; `--verify-persistence` is required to prove the original one.

`make message-context-export-check` checks an existing Mock demo. CI performs
the initial/restart pair after verifying the original surrounding-message pair.

## Manual browser acceptance

Perform these after the automated initial/restart pair:

1. Select the original main conversation reported by the checker. Search `turn 01`,
   open its older unloaded result, and confirm four context messages while the
   chat still has 20 loaded messages. Put distinct text in chat, rename, create,
   and title-filter drafts. Download both formats and confirm all drafts/search/
   selection/loaded messages remain available.
2. Inspect JSON's export kind, selected ID, anchor index, flags, complete roles,
   text, and timestamps. Inspect Markdown's selected marker and literal script/
   code-fence text. The four context messages are an excerpt of the saved 25.
3. Set zero/zero, reload, and export one selected message. Select a middle result,
   set ten/ten, reload, and export 21 messages. Assistant-filtered search can still
   export neighbouring user messages. Complete-conversation JSON export remains
   available for importable backups.
4. During a pending export, edit counts/search or close/switch context. Its late
   response must not trigger a download. After a network error, displayed context
   and drafts remain, with an explicit retry. Reload if another client changed
   saved content before exporting.
