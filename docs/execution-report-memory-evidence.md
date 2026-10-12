# Captured memory evidence in execution reports

Issue #163 extends the existing browser-local JSON and Markdown reports with
captured memory evidence. It reuses the existing memory-context endpoint and
its validation. No backend route, model call or database change is added.

## Controls

1. Load an existing execution in **Runtime V4 Execution Inspector**.
2. The export area initially says memory evidence is not loaded.
3. To include saved evidence, click the existing **Show memory retrieval** button
   immediately below the export area. Wait for the captured facts or absence/error.
4. Use **Export JSON** or **Export Markdown** in the execution report area.
   The conversation backup area has different controls with the same names.

No memory read is performed on initial inspection or export. Only an explicit
Show/Refresh memory retrieval request reads the saved execution capture. It does
not rerun keyword search, semantic retrieval, inference or embeddings.

## Report schema version 2

Version 2 preserves the meaning and fields of `execution`, `trace`, `snapshot`
and `replays` from version 1 and adds `memory_retrieval`. Previously downloaded
version 1 files remain version 1; they have no memory field and must be treated
as evidence not exported, not as evidence unavailable. New consumers should
branch on `schema_version` and accept versions 1 and 2 as appropriate. AgentDesk
has no execution-report importer. Stored snapshot and evidence versions remain 1;
no database migration is needed.

`memory_retrieval` has `execution_id`, `agent_id`, `status` and `evidence`.

| Status | Meaning | Evidence |
| --- | --- | --- |
| `not_loaded` | No explicit saved-evidence read for the currently displayed execution scope. | `null` |
| `loading` | An explicit saved-evidence read is still pending at export time. | `null` |
| `unavailable` | A successful response confirmed that no capture was recorded. | `null` |
| `loaded` | Captured evidence was successfully read and validated. This includes a recorded empty context. | Captured object |
| `failed` | The saved-evidence read failed or returned invalid data. Absence is not inferred. | `null` |

Export during an evidence read remains possible and records `loading`; it does
not wait, issue another request or include an earlier result. Refreshing evidence
clears old export evidence immediately. Retry can replace `failed` with a newly
validated `loaded` or `unavailable` state.

Loaded evidence retains its version, Agent/user scope, trimmed query, capture
time, limit, requested/actual retrieval modes, embedding provider/model, similarity
threshold, fallback reason, Agent/shared memories and exact Runtime context.
Each memory retains its ID, scope, content, creation time, keyword score/terms
and cosine similarity. Scores are serialized at their original precision.

Only allowlisted fields are serialized. Raw read errors, response bodies and
unrelated metadata are excluded. Saved memory text and captured fallback reasons
remain original data, so review them before sharing. Markdown keeps the memory
object inside a safe JSON fence, including Unicode, multiline content and HTML.
The existing 10 MiB UTF-8 limit includes the memory section; oversized exports
fail without truncation.

## Scope and lifecycle

Evidence is bound to execution ID, Agent ID and exact saved input. Existing
validators also check query, owner scopes, score/order rules and rendered context.
Switching executions, changing scoped inspection input/Agent, or unmounting the
panel prevents late evidence responses from updating the current report. Loading
an execution anew starts unread; refreshing inspection with an unchanged scope
can retain already captured evidence. No automatic evidence read is introduced.

The report is a serialization of displayed inspection and explicit saved-evidence
read state, not an atomic database snapshot. These endpoints are read separately.
The outer `captured_at` is browser export time; `evidence.recorded_at` is the
historical Runtime capture time. Later edits/deletions of live memories must not
be substituted for the execution's captured evidence.

## Browser acceptance

Preserve needed drafts with **Keep this Agent's drafts on this browser** before
Ctrl+F5. Select Agent 1 and conversation 16; enter `Memory report title draft`
and `Memory report chat draft` without saving/sending.

1. Load an existing execution, such as 116. Export once before clicking Show
   memory retrieval; JSON has schema version 2 and status `not_loaded`.
2. Click **Show memory retrieval**. If facts are displayed, export both formats:
   `status=loaded`, matching captured scope/modes/context and memory content.
   A recorded empty context is still `loaded`.
3. If the execution has no saved capture, export still succeeds with
   `status=unavailable`. Choose another existing execution with recorded evidence
   for the loaded-state check; do not create a new task solely for acceptance.
4. Switch to a different execution. Before its explicit evidence read, export
   should say `not_loaded` and contain none of the previous captured memory.
5. Return to chat and confirm conversation and exact drafts remain.
6. Recreate frontend without deleting volumes. Reload the same saved execution,
   explicitly load memory evidence, and compare the two formats and both rounds.
   For unchanged captures, all five data sections match. Export time differs.

The existing read-only search/configuration/model checks verify preserved records,
vectors and 14 retained checkpoints. Do not run a Mock fixture initializer against
the user's retained Ollama database merely to produce new evidence.

## Automated validation

From `frontend`: `npm test` and `npm run build`.
Tests cover the five states, empty captures, semantic precision, keyword fallback,
shared memory, scope and query validation, late responses/unmounts, safe Markdown,
size limits, unchanged original report sections, zero additional export requests,
and exact workbench draft preservation. Windows browser acceptance is separate.
