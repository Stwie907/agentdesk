import { useEffect, useRef, useState } from "react";
import { downloadConversationAttachment, type ConversationExportFormat } from "../api/conversationExport";
import { ApiError } from "../api/executions";
import type { MessageContext } from "../api/messageContext";
import { getMessageContextExport } from "../api/messageContextExport";

type Props = { context: MessageContext; disabled: boolean };

export function MessageContextExport({ context, disabled }: Props) {
  const [busy, setBusy] = useState<ConversationExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const writing = useRef(false);
  const currentContext = useRef(context); currentContext.current = context;
  const unavailable = useRef(disabled); unavailable.current = disabled;

  function cancel() { generation.current += 1; controller.current?.abort(); writing.current = false; }

  useEffect(() => {
    cancel(); setBusy(null); setError(null); setNotice(null);
    return cancel;
  }, [context, disabled]);

  async function exportFile(format: ConversationExportFormat) {
    if (disabled || writing.current) return;
    cancel();
    const current = generation.current;
    const source = context;
    const request = new AbortController(); controller.current = request;
    writing.current = true; setBusy(format); setError(null); setNotice(null);
    const valid = () => generation.current === current && !request.signal.aborted &&
      !unavailable.current && currentContext.current === source;
    try {
      const file = await getMessageContextExport(source, format, request.signal);
      if (!valid()) return;
      downloadConversationAttachment(file);
      setNotice(`Downloaded ${file.filename} with ${file.messageCount} displayed saved messages.`);
    } catch (cause) {
      if (valid()) setError(cause instanceof ApiError ? (cause.status === 404 ?
        "This saved message context is no longer available. Reload message context or search again." : cause.message) :
        "Unable to export message context. Your context and drafts were kept. Try again.");
    } finally {
      if (valid()) { writing.current = false; setBusy(null); }
    }
  }

  return <div role="group" aria-label="Export displayed message context" aria-busy={busy !== null}>
    <p>Download these displayed saved messages. For an importable backup, use Export JSON for the complete conversation.</p>
    <button type="button" disabled={disabled || busy !== null} onClick={() => void exportFile("json")}>
      {busy === "json" ? "Exporting context JSON..." : "Export context JSON"}
    </button>
    <button type="button" disabled={disabled || busy !== null} onClick={() => void exportFile("markdown")}>
      {busy === "markdown" ? "Exporting context Markdown..." : "Export context Markdown"}
    </button>
    {error !== null && <p role="alert">{error}</p>}
    {notice !== null && <p role="status">{notice}</p>}
  </div>;
}
