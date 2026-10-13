import { validateExecutionMemoryContext } from "../api/memoryEvidence";
import type { MemoryEvidenceExportState, MemoryEvidenceItem } from "../types/memoryEvidence";
import type { ExecutionInspection } from "../types/executions";

export type ExecutionReportFormat = "json" | "markdown";
export const MAX_EXECUTION_REPORT_BYTES = 10 * 1024 * 1024;

/** Serialize only the fields displayed by the existing inspection endpoints. */
export function createExecutionReport(
  inspection: ExecutionInspection,
  format: ExecutionReportFormat,
  capturedAt = new Date().toISOString(),
  memoryState?: MemoryEvidenceExportState,
) {
  const source = inspection.execution;
  if (!Number.isSafeInteger(source.id) || source.id <= 0 ||
      inspection.trace.some((event) => event.execution_id !== source.id) ||
      (inspection.snapshot !== null && inspection.snapshot.execution_id !== source.id) ||
      inspection.replays.some((replay) => replay.replay_of_execution_id !== source.id)) {
    throw new Error("The inspection contains data for another execution. Reload it before exporting.");
  }
  const execution = (row: typeof source) => ({
    id: row.id, agent_id: row.agent_id, status: row.status,
    input: row.input, output: row.output, retry_count: row.retry_count,
    failure_type: row.failure_type, failure_message: row.failure_message,
    replay_of_execution_id: row.replay_of_execution_id, created_at: row.created_at,
  });
  const memory = memoryState ?? {
    execution_id: source.id, agent_id: source.agent_id, input: source.input,
    status: "not_loaded", evidence: null,
  };
  if (memory.execution_id !== source.id || memory.agent_id !== source.agent_id || memory.input !== source.input ||
      !["not_loaded", "loading", "unavailable", "loaded", "failed"].includes(memory.status) ||
      (memory.status === "loaded" ? memory.evidence === null : memory.evidence !== null)) {
    throw new Error("The memory evidence does not match this execution. Reload it before exporting.");
  }
  const body = validateExecutionMemoryContext({
    execution_id: source.id, available: memory.status === "loaded", evidence: memory.evidence,
  }, source.id, source.agent_id, source.input);
  const facts = body.evidence;
  const item = (row: MemoryEvidenceItem) => ({
    memory_id: row.memory_id, scope: row.scope, scope_id: row.scope_id, content: row.content,
    created_at: row.created_at, score: row.score, matched_terms: [...row.matched_terms], similarity: row.similarity,
  });
  const memoryRetrieval = {
    execution_id: source.id, agent_id: source.agent_id, status: memory.status,
    evidence: facts === null ? null : {
      version: facts.version, agent_id: facts.agent_id, user_id: facts.user_id, query: facts.query,
      limit: facts.limit, recorded_at: facts.recorded_at, requested_mode: facts.requested_mode,
      mode: facts.mode, provider: facts.provider, model: facts.model,
      min_similarity: facts.min_similarity, fallback_reason: facts.fallback_reason,
      agent_memories: facts.agent_memories.map(item), shared_memories: facts.shared_memories.map(item),
      context: facts.context,
    },
  };
  const snapshot = inspection.snapshot;
  const report = {
    schema_version: 2,
    source: "displayed_execution_inspection",
    captured_at: capturedAt,
    consistency: "Existing endpoints are read separately; this is not an atomic database backup.",
    execution: execution(source),
    trace: inspection.trace.map((event) => ({
      id: event.id, execution_id: event.execution_id, event: event.event,
      step_index: event.step_index, tool: event.tool, error: event.error,
      message: event.message, created_at: event.created_at,
    })),
    snapshot: snapshot === null ? null : {
      id: snapshot.id, execution_id: snapshot.execution_id,
      snapshot_version: snapshot.snapshot_version, input_snapshot: snapshot.input_snapshot,
      plan_snapshot: snapshot.plan_snapshot, output_snapshot: snapshot.output_snapshot,
      created_at: snapshot.created_at,
    },
    replays: inspection.replays.map(execution),
    memory_retrieval: memoryRetrieval,
  };
  // Use a fence longer than any backtick run in saved text. User content stays
  // inside a literal block, including HTML and Markdown headings.
  const literal = (value: unknown) => {
    const body = JSON.stringify(value, null, 2);
    const runs = body.match(/`+/g) ?? [];
    const longest = runs.reduce((length, run) => Math.max(length, run.length), 0);
    const fence = "`".repeat(Math.max(3, longest + 1));
    return `${fence}json\n${body}\n${fence}`;
  };
  const content = format === "json" ? JSON.stringify(report, null, 2) + "\n" : [
    `# AgentDesk execution ${source.id}`,
    "Report schema: 2. Source: the currently displayed saved execution inspection.",
    `Captured at: ${capturedAt}`,
    report.consistency,
    "This report may contain saved user inputs, tool results and captured memory content. Review it before sharing.",
    "## Execution", literal(report.execution),
    "## Runtime V4 trace",
    report.trace.length === 0 ? "No Runtime V4 trace events." : literal(report.trace),
    "## Snapshot",
    report.snapshot === null ? "No snapshot available." : literal(report.snapshot),
    "## Captured memory retrieval", literal(report.memory_retrieval),
    "## Replay history",
    report.replays.length === 0 ? "No replay executions." : literal(report.replays),
    "",
  ].join("\n\n");
  const size = new TextEncoder().encode(content).byteLength;
  if (size > MAX_EXECUTION_REPORT_BYTES) {
    throw new Error("The execution report exceeds 10 MiB. No partial report was downloaded.");
  }
  return {
    content,
    filename: `execution-${source.id}.${format === "json" ? "json" : "md"}`,
    mime: format === "json" ? "application/json;charset=utf-8" : "text/markdown;charset=utf-8",
  };
}

export function downloadExecutionReport(file: ReturnType<typeof createExecutionReport>) {
  const url = URL.createObjectURL(new Blob([file.content], { type: file.mime }));
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = file.filename;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
