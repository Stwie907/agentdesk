# Execution report exports

Issue #161 adds browser-local exports from the existing Runtime V4 Inspector.
FastAPI, storage, routes, model configuration and dependencies are unchanged.

## Use

1. Choose **执行 Inspector** in the sidebar.
2. Enter an existing **Execution ID** and click **Load Execution**, or select a
   record from execution history. No task submission is needed.
3. Optionally click **Refresh execution** to read newer persisted information.
4. Click **Export JSON** or **Export Markdown** in **Export execution report**.
   Downloads are named `execution-<id>.json` and `execution-<id>.md`.

The browser reports that the download was requested; it cannot confirm where
it was saved. Controls are unavailable during inspection loading or manual
refresh/replay/cancel/retry. A missing execution or failed inspection read has
no export controls. A valid execution without a snapshot can still be exported.
Late inspection/action responses cannot replace a newer execution selection.

## JSON schema version 1

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`; separate from the persisted snapshot version. |
| `source` | `displayed_execution_inspection`. |
| `captured_at` | Browser UTC ISO time when serialization starts. |
| `consistency` | Explanation that separate existing reads are not an atomic backup. |
| `execution` | Saved ID, Agent ID, status, input/output, retry count, failure type/message, replay parent and creation time. |
| `trace` | Displayed structured trace events with their IDs, execution scope, step/tool/error, message and creation time. Empty array if no events exist. |
| `snapshot` | Displayed saved snapshot metadata, version and original input/plan/output strings, or `null` if unavailable. |
| `replays` | Displayed saved replay executions; empty array if none exist. |

Only these known fields are serialized. User strings are retained without
truncation, including Unicode, whitespace, HTML and multiline results. Snapshot
plan strings remain original strings: malformed legacy JSON is not reinterpreted
or repaired by the export. JSON nulls and empty strings remain distinct.

Markdown uses literal JSON code blocks for these same four data sections,
with fences longer than any backtick sequence in their saved content. This
keeps user headings, Markdown and HTML inside literal blocks. Null snapshots
and empty trace/replay arrays have explicit text instead. Both files are UTF-8.

## Content limits and scope

Each serialized report is limited to 10 MiB in UTF-8. Oversized reports are
rejected rather than truncated. Serialization or download errors stay within
the export controls and allow retry. Temporary download links are removed and
object URLs are released after the browser has time to start reading them.

The export serializes already loaded state synchronously; it makes no additional
HTTP request, inference, embeddings, replay, installation or database write.
Inspection reads still use the existing endpoints. Those reads happen separately;
active tasks can change between reads and after export. The capture timestamp
is not a transactional database timestamp. For newer data, refresh before export.
Reports are for review and debugging, not importable conversation backups or
restorable database backups. Memory retrieval evidence is not included.

Saved inputs and tool results may contain user information. The controls remind
users to review reports before sharing; original user strings are not redacted.

## Verification

Run from `frontend`:

```sh
npm test
npm run build
```

Automated coverage checks content preservation, schema, unavailable data,
foreign execution rejection, Markdown fences, size limits, download cleanup,
browser errors, stale loads/refresh/actions, and unchanged conversation/drafts.
The existing frontend suite covers normal Inspector actions and polling.

For browser acceptance on Windows:

1. Select Agent 1 and conversation 16. Enter unsaved title `Report title draft`
   and unsent chat `Report chat draft`. Do not rename or send.
2. Load an existing completed execution in Inspector. Export both formats.
3. Open JSON in a text editor and verify `schema_version: 1`, execution ID,
   status and output agree with Inspector. Check Markdown's corresponding
   sections; missing snapshot is allowed when Inspector also shows none.
4. Return to Conversation Chat: Agent, conversation and both drafts remain.
5. Load a different existing execution and export again. The new filenames
   and `execution.id` match the newly displayed execution.
6. Retain downloaded files. Recreate the frontend container without deleting
   volumes, reload the page after preserving drafts if desired, then repeat
   exports of the same saved record. Data sections match if the stored record
   has not changed; `captured_at` will differ and file digests need not match.

Existing search/configuration/model acceptance checks can be rerun after frontend
recreation to confirm the retained records and checkpoint bytes. This feature
adds no backend command and does not require model inference for acceptance.
