import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/executions";
import { deleteMemory, getAgentMemories, saveMemory, updateMemory } from "../api/memories";
import type { Memory } from "../types/memories";
import { MemorySearchPanel } from "./MemorySearchPanel";

export function MemoryPanel({ agentId, refreshKey = 0 }: { agentId: number | null; refreshKey?: number }) {
  return (
    <section aria-labelledby="memory-heading">
      <h2 id="memory-heading">Agent Memory</h2>
      {agentId === null ? (
        <p>Select an Agent above to view or manage its saved memories.</p>
      ) : (
        // A new Agent gets independent drafts, request guards, and load state.
        <AgentMemories key={agentId} agentId={agentId} refreshKey={refreshKey} />
      )}
    </section>
  );
}

function AgentMemories({ agentId, refreshKey }: { agentId: number; refreshKey: number }) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [searchKey, setSearchKey] = useState(0);
  const [editing, setEditing] = useState<{ memory: Memory; draft: string } | null>(null);
  const mounted = useRef(true);
  const writeInProgress = useRef(false);
  const previousRefreshKey = useRef(refreshKey);

  // Defer a chat-triggered refresh until a manual memory write has finished.
  useEffect(() => {
    if (!busy && editing === null && refreshKey !== previousRefreshKey.current) {
      previousRefreshKey.current = refreshKey;
      setReloadKey((key) => key + 1);
    }
  }, [busy, editing, refreshKey]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoaded(false);
    setError(null);
    setStatus(null);
    setConfirmId(null);
    async function load() {
      try {
        const rows = await getAgentMemories(agentId);
        if (!cancelled) {
          setMemories(rows);
          setLoaded(true);
        }
      } catch (failure) {
        if (!cancelled) {
          setError(failure instanceof ApiError ? failure.message : "Unable to load memories.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [agentId, reloadKey]);

  const disabled = loading || busy || !loaded;

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = content.trim();
    if (disabled || editing !== null || writeInProgress.current || !trimmed || trimmed.length > 2000) return;
    writeInProgress.current = true;
    setBusy(true);
    setSearchKey((key) => key + 1);
    setError(null);
    setStatus(null);
    setConfirmId(null);
    try {
      const saved = await saveMemory(agentId, trimmed);
      if (mounted.current) {
        setMemories((rows) => rows.some((row) => row.id === saved.id)
          ? rows.map((row) => row.id === saved.id ? saved : row)
          : [...rows, saved]);
        setContent("");
        setStatus(`Memory ${saved.id} saved.`);
      }
    } catch (failure) {
      if (mounted.current) {
        setError(failure instanceof ApiError ? failure.message :
          "Unable to save memory. Reload memories to check whether it was saved before trying again.");
      }
    } finally {
      writeInProgress.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  async function handleDelete(memoryId: number) {
    if (disabled || editing !== null || writeInProgress.current || confirmId !== memoryId) return;
    writeInProgress.current = true;
    setBusy(true);
    setSearchKey((key) => key + 1);
    setError(null);
    setStatus(null);
    try {
      await deleteMemory(memoryId, agentId);
      if (mounted.current) {
        setMemories((rows) => rows.filter((row) => row.id !== memoryId));
        setConfirmId(null);
        setStatus(`Memory ${memoryId} deleted.`);
      }
    } catch (failure) {
      if (mounted.current) {
        setError(failure instanceof ApiError ? failure.message :
          "Unable to delete memory. Reload memories to check its current state before trying again.");
      }
    } finally {
      writeInProgress.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || editing === null || writeInProgress.current) return;
    const trimmed = editing.draft.trim();
    if (!trimmed || trimmed.length > 2000 || trimmed === editing.memory.content) return;
    writeInProgress.current = true;
    setBusy(true);
    setSearchKey((key) => key + 1);
    setError(null);
    setStatus(null);
    try {
      const saved = await updateMemory(editing.memory, trimmed);
      if (mounted.current) {
        setMemories((rows) => rows.map((row) => row.id === saved.id ? saved : row));
        setEditing(null);
        setStatus(`Memory ${saved.id} updated.`);
      }
    } catch (failure) {
      if (mounted.current) {
        setError(failure instanceof ApiError ? failure.message :
          "Unable to update memory. Keep your draft, then cancel editing and reload to check what was saved.");
      }
    } finally {
      writeInProgress.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <div aria-busy={loading || busy}>
      <p>Memories for Agent {agentId}</p>
      <button type="button" disabled={loading || busy || editing !== null}
        onClick={() => setReloadKey((key) => key + 1)}>
        Reload memories
      </button>
      {loading && <p role="status">Loading memories...</p>}
      {error !== null && <p role="alert">{error}</p>}
      {status !== null && <p role="status">{status}</p>}
      <form onSubmit={(event) => void handleSave(event)}>
        <label htmlFor="memory-content">Memory content</label>
        <div>
          <textarea id="memory-content" rows={3} maxLength={2000}
            placeholder="Example: I prefer concise answers."
            value={content} disabled={disabled || editing !== null}
            onChange={(event) => { setContent(event.target.value); setStatus(null); }} />
        </div>
        <p>Up to 2000 characters. Exact duplicates reuse the existing memory.</p>
        <button type="submit" disabled={disabled || editing !== null || !content.trim() || content.trim().length > 2000}>
          Save memory
        </button>
      </form>
      <MemorySearchPanel agentId={agentId} disabled={disabled}
        revision={JSON.stringify([reloadKey, refreshKey, searchKey])} />
      {loaded && memories.length === 0 && <p>No saved memories for this Agent.</p>}
      {loaded && memories.length > 0 && (
        <ul aria-label="Saved memories">
          {memories.map((memory) => (
            <li key={memory.id}>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{memory.content}</p>
              <p>Memory {memory.id} · Created {memory.created_at.replace("T", " ")}</p>
              {editing?.memory.id === memory.id ? (
                <form aria-label={`Edit memory ${memory.id}`} onSubmit={(event) => void handleEdit(event)}>
                  <label htmlFor={`edit-memory-${memory.id}`}>Edited memory content</label>
                  <div>
                    <textarea id={`edit-memory-${memory.id}`} rows={3} maxLength={2000}
                      value={editing.draft} disabled={disabled}
                      onChange={(event) => setEditing({ ...editing, draft: event.target.value })} />
                  </div>
                  <p>Up to 2000 characters. Saving keeps this memory's ID and creation time.</p>
                  <button type="submit" disabled={disabled || !editing.draft.trim() ||
                    editing.draft.trim().length > 2000 || editing.draft.trim() === editing.memory.content}>
                    Save changes
                  </button>
                  <button type="button" disabled={disabled}
                    onClick={() => { setEditing(null); setError(null); setStatus(null); }}>Cancel editing</button>
                </form>
              ) : (
                <button type="button" disabled={disabled || editing !== null}
                  onClick={() => {
                    setEditing({ memory: { ...memory }, draft: memory.content });
                    setConfirmId(null); setError(null); setStatus(null);
                  }}>Edit memory {memory.id}</button>
              )}
              {confirmId === memory.id ? (
                <>
                  <p>Delete memory {memory.id}?</p>
                  <button type="button" disabled={disabled}
                    onClick={() => void handleDelete(memory.id)}>Confirm delete</button>
                  <button type="button" disabled={disabled}
                    onClick={() => setConfirmId(null)}>Keep memory</button>
                </>
              ) : (
                <button type="button" disabled={disabled || editing !== null}
                  onClick={() => setConfirmId(memory.id)}>Delete memory {memory.id}</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
