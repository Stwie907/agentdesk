import { type FormEvent, useEffect, useRef, useState } from "react";
import { importConversation, readConversationImport, type ConversationImportResult, type PreparedConversationImport } from "../api/conversationImport";
import { ApiError } from "../api/executions";

type Props = {
  agentId: number; disabled: boolean;
  onStart: () => boolean; onFinish: () => void; onImported: (result: ConversationImportResult) => void;
};

export function ConversationImport({ agentId, disabled, onStart, onFinish, onImported }: Props) {
  const [preview, setPreview] = useState<PreparedConversationImport | null>(null);
  const [reading, setReading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const active = useRef(true);
  const generation = useRef(0);
  const inProgress = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; generation.current += 1; };
  }, []);

  async function selectFile(file: File | undefined) {
    const current = ++generation.current;
    setPreview(null); setError(null); setNotice(null); setReading(!!file);
    if (!file) return;
    try {
      const next = await readConversationImport(file);
      if (active.current && current === generation.current) setPreview(next);
    } catch (cause) {
      if (active.current && current === generation.current) setError(cause instanceof ApiError ? cause.message : "Unable to read this backup. Choose the JSON file again.");
    } finally {
      if (active.current && current === generation.current) setReading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || reading || preview === null || inProgress.current || !onStart()) return;
    inProgress.current = true; setBusy(true); setError(null); setNotice(null);
    try {
      const result = await importConversation(agentId, preview);
      if (!active.current) return;
      setNotice(`Imported “${result.conversation.title}” as conversation ${result.conversation.id} with ${result.message_count} saved messages. Use conversation title search to open it.`);
      setPreview(null);
      if (input.current) input.current.value = "";
      onImported(result);
    } catch (cause) {
      if (active.current) setError(cause instanceof ApiError ? cause.message : "Unable to import conversation. Reload conversations to check whether it was saved before trying again.");
    } finally {
      inProgress.current = false;
      onFinish();
      if (active.current) setBusy(false);
    }
  }

  return <form aria-label="Import conversation backup" onSubmit={(event) => void submit(event)} aria-busy={reading || busy}>
    <label htmlFor="conversation-import-file">Conversation JSON backup</label>
    <input ref={input} id="conversation-import-file" type="file" accept=".json,application/json" disabled={disabled || busy}
      onChange={(event) => { if (!disabled && !inProgress.current) void selectFile(event.target.files?.[0]); }} />
    <p>Import a JSON backup into Agent {agentId} as a new conversation. Your selected chat, loaded messages, and drafts stay available.</p>
    {reading && <p role="status">Reading backup...</p>}
    {preview && <div>
      <p style={{ overflowWrap: "anywhere" }}>Backup title: {preview.title.length > 200 ? preview.title.slice(0, 200) + "…" : preview.title}</p>
      <p>{preview.messageCount} saved messages. Destination: Agent {agentId}.</p>
      <p>Confirm to create a separate conversation with the original message text and timestamps.</p>
    </div>}
    <button type="submit" disabled={disabled || reading || busy || preview === null}>{busy ? "Importing..." : "Confirm import as new conversation"}</button>
    <button type="button" disabled={disabled || busy || (!preview && !reading && !error)} onClick={() => {
      generation.current += 1; setPreview(null); setReading(false); setError(null); setNotice(null);
      if (input.current) input.current.value = "";
    }}>Clear import file</button>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status" style={{ overflowWrap: "anywhere" }}>{notice}</p>}
  </form>;
}
