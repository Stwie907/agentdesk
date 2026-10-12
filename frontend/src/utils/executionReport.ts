import type { ExecutionInspection } from "../types/executions";

export type ExecutionReportFormat = "json" | "markdown";
export const MAX_EXECUTION_REPORT_BYTES = 10 * 1024 * 1024;

/** Serialize only the fields displayed by the existing inspection endpoints. */
export function createExecutionReport(
  inspection: ExecutionInspection,
  format: ExecutionReportFormat,
  capturedAt = new Date().toISOString(),
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
  const snapshot = inspection.snapshot;
  const report = {
    schema_version: 1,
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
    "Report schema: 1. Source: the currently displayed saved execution inspection.",
    `Captured at: ${capturedAt}`,
    report.consistency,
    "This report may contain saved user inputs and tool results. Review it before sharing.",
    "## Execution", literal(report.execution),
    "## Runtime V4 trace",
    report.trace.length === 0 ? "No Runtime V4 trace events." : literal(report.trace),
    "## Snapshot",
    report.snapshot === null ? "No snapshot available." : literal(report.snapshot),
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
