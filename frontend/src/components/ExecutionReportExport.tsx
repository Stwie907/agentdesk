import { useState } from "react";
import type { MemoryEvidenceExportState } from "../types/memoryEvidence";
import type { ExecutionInspection } from "../types/executions";
import { createExecutionReport, downloadExecutionReport, type ExecutionReportFormat } from "../utils/executionReport";

export function ExecutionReportExport({ inspection, disabled, memoryState }: {
  inspection: ExecutionInspection; disabled: boolean; memoryState?: MemoryEvidenceExportState;
}) {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function exportReport(format: ExecutionReportFormat) {
    if (disabled) return;
    setError(null); setNotice(null);
    try {
      const file = createExecutionReport(inspection, format, undefined, memoryState);
      downloadExecutionReport(file);
      setNotice(`Download requested: ${file.filename}`);
    } catch {
      setError("Unable to export this execution report. Reload the execution and try again. Reports are limited to 10 MiB; no partial file was downloaded.");
    }
  }

  const memoryStatus = memoryState?.status ?? "not_loaded";
  const memoryNotice = {
    not_loaded: "Not loaded. Use Show memory retrieval below to include captured evidence.",
    loading: "Loading. An export now records loading with no captured evidence.",
    unavailable: "No evidence was recorded for this execution.",
    loaded: "Included: captured memory evidence for this execution.",
    failed: "Read failed. An export now records failure with no captured evidence.",
  }[memoryStatus];

  return <section aria-label="Export execution report">
    <p>Download the currently displayed execution, trace, snapshot and replay history. Running tasks may change after this read.</p>
    <p>Reports contain saved inputs, tool results and captured memory content. Review them before sharing.</p>
    <p>Memory evidence: {memoryNotice}</p>
    <button type="button" disabled={disabled} onClick={() => exportReport("json")}>Export JSON</button>
    <button type="button" disabled={disabled} onClick={() => exportReport("markdown")}>Export Markdown</button>
    {error !== null && <p role="alert">{error}</p>}
    {notice !== null && <p role="status">{notice}</p>}
  </section>;
}
