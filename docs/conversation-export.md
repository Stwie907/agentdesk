# Complete conversation exports

Select a saved conversation under **Conversation Chat**, then choose **Export JSON**
or **Export Markdown**. The browser downloads `conversation-ID.json` or
`conversation-ID.md`. The attachment includes every saved message in timestamp/ID
order, including history that has not been loaded with **Load older messages**.
Unsent chat, rename, and creation drafts remain on the page and are not exported.

JSON schema version 1 contains `schema_version`, `conversation`, `message_count`,
and `messages`. Conversation metadata and each message retain their IDs, Agent or
conversation scope, content, role, and creation time. There is no generated export
time, so unchanged records produce identical UTF-8 bytes after restart.
Markdown includes the same metadata and renders titles, roles, and message
contents as literal fenced text. Embedded Markdown fences and HTML remain text;
original newlines, Unicode, and trailing whitespace are preserved. This format
prioritizes an accurate saved transcript over rendering embedded rich Markdown.

The API is `GET /conversations/{conversation_id}/export?agent_id=ID&format=json`.
The Agent parameter is required. `format` defaults to `json`; `markdown` is the
other supported value. Invalid parameters return 422. A missing, deleted, or
foreign conversation returns 404. Scope checks use the existing local data model
and do not add authentication. The API reads conversation metadata and messages
in one bounded SQL statement for a consistent snapshot during concurrent writes.

Exports allow at most 10,000 messages and 10 MiB of encoded UTF-8 data. Exceeding
either limit returns 413 with a readable error; it never returns a partial
attachment. Empty conversations produce valid files with zero messages. Filenames
use only the numeric conversation ID, so title punctuation cannot alter download
paths or headers. Responses use `Cache-Control: no-store` and `nosniff`.

The workbench checks attachment metadata and validates JSON scope, count, IDs,
timestamps, and ordering before starting a download. Repeated clicks are blocked
while an export is pending. Changing the Agent or selected conversation cancels
the old request and discards late responses. Export failures retain loaded history
and drafts for an explicit retry. An off-page active conversation remains
exportable. Export is disabled during chat/management writes and delete confirmation.

## Docker acceptance

Keep the existing Ollama/semantic/vector-cache settings, with Docker running.
From the repository root in Windows Git Bash or a Unix shell:

```sh
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_conversation_export --base-url http://frontend
```

Equivalent checker target: `make conversation-export-check`.
The first run prepares three isolated conversations and 26 messages. The main
fixture has 25 messages, including Chinese, code fences, HTML, CRLF, and trailing
whitespace. No chat execution or model request is needed. The eight checks compare
both formats with the full saved transcript, verify an empty conversation,
confirm Agent isolation and validation, and demonstrate that a 20-message page
still exports all 25 saved messages.

A separate `/data/conversation-export-acceptance.json` records source identities,
all SQLite table fingerprints, six attachment SHA-256 values, and the hashes of
earlier acceptance checkpoint files. Initial preparation adds only fixture
conversations/messages and this checkpoint. Original records and cached vectors
remain intact.

Keep the initial/restart pair idle: do not chat, rename, or edit/delete records
between these commands. Preserve the named volume:

```sh
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_conversation_export \
  --base-url http://frontend --verify-persistence
```

Both runs should report `status: passed`, `checks_passed: 8`,
`saved_message_count: 25`, `latest_page_count: 20`, and both formats verified.
After restart, `persistence_verified`, `checkpoint_reused`, and `read_only` are
true; all creation counts are zero and every export hash is unchanged.
Missing/changed records, cached vectors, exported bytes, or checkpoint evidence
fail without repair. Successful checkpoint reuse is also read-only. Normal
activity after this pair changes its strict saved baseline.

Then search conversation titles for `AgentDeskConversationExport`, select the
Chinese-titled fixture, and enter an unsent chat draft. Before loading older
messages, download both formats. JSON should contain 25 messages even though the
page shows 20. Markdown should contain all original Chinese and embedded code
text. The draft and loaded-page count should stay unchanged. Exporting the
**Empty** fixture should download a valid zero-message file.

No migration, dependency, paid API, or chat-provider change is required.
