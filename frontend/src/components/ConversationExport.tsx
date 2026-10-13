import { useEffect, useRef, useState } from "react";
import { downloadConversationAttachment, getConversationExport, type ConversationExportFormat } from "../api/conversationExport";
import { ApiError } from "../api/executions";

type Props = { conversationId: number; agentId: number; disabled: boolean };

export function ConversationExport({ conversationId, agentId, disabled }: Props) {
  const [busy, setBusy] = useState<ConversationExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const active = useRef(true);
  const inProgress = useRef(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; controller.current?.abort(); };
  }, []);

  async function exportFile(format: ConversationExportFormat) {
    if (disabled || inProgress.current) return;
    inProgress.current = true;
    setBusy(format);
    setError(null);
    setNotice(null);
    controller.current = new AbortController();
    try {
      const file = await getConversationExport(conversationId, agentId, format, controller.current.signal);
      if (!active.current) return;
      downloadConversationAttachment(file);
      setNotice(`Downloaded ${file.filename} with ${file.messageCount} saved messages.`);
    } catch (cause) {
      if (active.current) setError(cause instanceof ApiError ?
        (cause.status === 404 ? "Conversation not found for this Agent. Reload conversations." : cause.message) :
        "Unable to export conversation. Your loaded messages and drafts were kept. Try again.");
    } finally {
      inProgress.current = false;
      if (active.current) setBusy(null);
    }
  }

  return <div role="group" aria-label="Export conversation">
    <p>Export includes all saved messages, including earlier history. Unsent drafts stay on this page.</p>
    <button type="button" disabled={disabled || busy !== null} onClick={() => void exportFile("json")}>
      {busy === "json" ? "Exporting JSON..." : "Export JSON"}
    </button>
    <button type="button" disabled={disabled || busy !== null} onClick={() => void exportFile("markdown")}>
      {busy === "markdown" ? "Exporting Markdown..." : "Export Markdown"}
    </button>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
  </div>;
}
