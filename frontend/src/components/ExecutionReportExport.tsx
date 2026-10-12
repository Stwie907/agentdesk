import { useState } from "react";
import type { ExecutionInspection } from "../types/executions";
import { createExecutionReport, downloadExecutionReport, type ExecutionReportFormat } from "../utils/executionReport";

export function ExecutionReportExport({ inspection, disabled }: {
  inspection: ExecutionInspection; disabled: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function exportReport(format: ExecutionReportFormat) {
    if (disabled) return;
    setError(null); setNotice(null);
    try {
      const file = createExecutionReport(inspection, format);
      downloadExecutionReport(file);
      setNotice(`Download requested: ${file.filename}`);
    } catch {
      setError("Unable to export this execution report. Reload the execution and try again. Reports are limited to 10 MiB; no partial file was downloaded.");
    }
  }

  return <section aria-label="Export execution report">
    <p>Download the currently displayed execution, trace, snapshot and replay history. Running tasks may change after this read.</p>
    <p>Reports contain saved inputs and tool results. Review them before sharing.</p>
    <button type="button" disabled={disabled} onClick={() => exportReport("json")}>Export JSON</button>
    <button type="button" disabled={disabled} onClick={() => exportReport("markdown")}>Export Markdown</button>
    {error !== null && <p role="alert">{error}</p>}
    {notice !== null && <p role="status">{notice}</p>}
  </section>;
}
