# Keep conversation drafts on this browser

Under **Conversation Chat**, enable **Keep this Agent's drafts on this browser**.
The preference defaults to off and is separate for each Agent. While enabled,
edits to **Chat message** and **Conversation title** are saved immediately,
including exact Unicode, newlines and whitespace. Drafts already typed in visited
conversations are included when saving is enabled. Current page edits take
precedence over older browser copies.

## Restore and clear

After reloading, re-select the original Agent in the top dropdown, then choose
the original **Conversation**, or use **Open message ID in chat** on its saved
search result. Server-scoped reads validate the conversation before its draft
is restored. Message search and navigation retain their existing cancellation,
context, downloads and title-page behaviour. Restoration does not submit chat,
rename, create a conversation, extract memory or call a model.

Each stored record requires schema version 1, matching Agent/conversation IDs
and the conversation's original `created_at` value. Message/title length bounds
match the existing controls. A reused ID, foreign scope, unknown version,
malformed JSON or oversized record is ignored. An unedited title follows the
fresh saved title; an unfinished rename retains its exact text.

Turning saving off keeps existing browser copies but stops restoration and
ordinary draft saves. Enabling it again saves current page drafts ahead of those
copies. **Clear saved drafts for this Agent** opens a confirmation. Confirmation
turns saving off and removes only that Agent's version-1 draft records. Current
page text and other Agents' copies are kept. Reload after clearing to verify
that the old drafts do not return. A failed or partial clear is reported.

Successful completed sends clear only that conversation's chat draft and retain
its rename draft. Successful renames update its title/base-title copy and retain
chat text. These lifecycle updates also update an existing browser copy while
saving is off, without creating a new copy. Successful deletion or a scoped 404
on selection reload removes that conversation's copy. Failed requests and
non-completed executions retain drafts. Existing late-result guards after an
Agent change/unmount also apply to browser copies; inspect saved server state
before retrying a request that completed in an old panel.

Storage refusal, quota exhaustion or malformed data never blocks ordinary
session drafts. A warning explains when a reload may return an older saved
copy. There is no background retry or eviction. Strict Mode mounting/restoration
does not rewrite browser data. Another tab changing this Agent's saving
preference updates the setting without replacing open text. Draft text in open
tabs is not merged; the latest successful save of a conversation wins.

## Browser scope

Drafts use this browser's `localStorage` for the current origin: protocol, host
and port. Use the same browser/profile and `http://localhost:5173` for both runs;
`http://127.0.0.1:5173`, another port or another browser has separate storage.
Changing the SQLite database while keeping browser data cannot restore a draft
to a newly created conversation with a different `created_at` value.

Creation/title-search/Agent-message-search drafts, selections, loaded history,
located context and Inspector state are not persisted by this feature. Browser
drafts are separate from SQLite, complete JSON backups and Markdown exports.
FastAPI, React/TypeScript/Vite, SQLite, local Ollama qwen2.5:7b and zero paid APIs
remain the project stack. No backend, migration, dependency or workflow change
is required.

## Retained HTTP acceptance before browser edits

Use the original database volume and local Ollama settings. Finish the Agent
message search initial/restart pair first if its checkpoint does not exist.
From the repository root, rebuild and reuse that evidence:

```bash
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --build --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence
```

Immediately recreate services without normal server writes between the pair:

```bash
docker compose -f docker-compose.yml down &&
LLM_PROVIDER=ollama MEMORY_RETRIEVAL_MODE=semantic MEMORY_VECTOR_CACHE_ENABLED=true \
docker compose -f docker-compose.yml \
  up --detach --wait --wait-timeout 180 backend frontend &&
docker compose -f docker-compose.yml exec -T backend \
  python -m app.check_agent_message_search --base-url http://frontend --verify-persistence
```

Both reports must show `status: passed`, `checks_passed: 10`,
`persistence_verified: true` and `checkpoint_reused: true`, with the same original
IDs, `response_sha256` and `source_checkpoint_sha256`. Original rows, vectors and
predecessor checkpoints are retained; there are zero new conversation/message/
execution records. This existing checker verifies saved APIs and data, while
browser storage requires the steps below. Keep missing/changed evidence for
inspection rather than recreating fixtures or deleting the volume.

## Exact browser acceptance

1. Open `http://localhost:5173` in the same browser throughout. Choose the
   report's original Agent in the top **Agent** dropdown.
2. Under **Conversation Chat**, choose `original_conversation_id` in
   **Conversation**. If its title is off-page, set **Conversations per page** to
   20 or use **Next conversations**. Leave Send, Rename and Delete untouched.
3. Enable **Keep this Agent's drafts on this browser** below **Conversation**.
   Enter `  Main draft - do not send  ` in **Chat message** and `Main title draft`
   in **Conversation title**. Enter a separate value in **New conversation title**.
4. In **Search all Agent conversations**, search `中文` using **Agent message
   content search** and set **Agent search results per page** to 50. Click
   **Search Agent messages**, find `other_conversation_id/other_message_id`,
   then **Open message ID in chat**. Prior reports normally identify conversation
   10/message 18; use the current report's original IDs.
5. Enter `Other draft - do not send` and `Other title draft` into that
   conversation's chat/title fields. Reload the browser with Ctrl+R.
6. Re-select the same Agent. Its saving checkbox must remain checked.
   Re-select the two original conversations; each must restore only its own
   exact chat/title text. New-conversation and search fields start fresh. No
   automatic selection, sending or renaming occurs.
7. For the original older result, enter `turn 01` with a space in **Agent message
   content search** and click **Search Agent messages**. Open the result matching
   `original_conversation_id/older_message_id` (normally conversation 16/message
   90). Verify located context and restored main drafts together. Inspector
   selection stays unchanged through this navigation.
8. Select a different Agent in the top dropdown. Its checkbox is independent;
   it must not display the original Agent's text. Return to the original Agent,
   re-select its original conversation and verify its drafts return.
9. Turn saving off, edit the main chat draft, and turn it on again. The latest
   current text must stay. Reload, re-select its scope and check that text.
10. Click **Clear saved drafts for this Agent**, then **Cancel clearing saved
    drafts**; the saving checkbox and text stay. Repeat and choose **Confirm
    clear saved drafts**. Saving turns off, current fields stay, and reloading/
    re-selecting the same Agent/conversation no longer restores those copies.

The steps above make only browser edits and existing GET requests, preserving
the idle HTTP evidence. Screenshot the restored main/other drafts and confirmed
clear results separately. Sending, renaming or deleting is covered by frontend
regression tests; testing those server writes manually should use a disposable
conversation after retained-evidence acceptance.
