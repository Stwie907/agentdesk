import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/executions";
import { deleteUserMemory, getUserMemories, saveUserMemory, searchUserMemories, updateUserMemory } from "../api/userMemories";
import type { UserMemory, UserMemoryList, UserMemorySearch } from "../types/userMemories";
import { searchSemanticUserMemories, type SemanticSearch } from "../api/semanticMemories";

export function UserMemoryPanel({ agentId }: { agentId: number | null }) {
  const [opened, setOpened] = useState(false);
  return <section aria-labelledby="user-memory-heading">
    <h2 id="user-memory-heading">Shared User Memory</h2>
    <p>Saved here, a memory is available to all Agents belonging to the same user.</p>
    {agentId === null ? <p>Select an Agent above to manage shared user memories.</p> : !opened ?
      <button type="button" onClick={() => setOpened(true)}>Show shared memories</button> : <UserMemories key={agentId} agentId={agentId} />}
  </section>;
}

function UserMemories({ agentId }: { agentId: number }) {
  const [context, setContext] = useState<UserMemoryList | null>(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<{ memory: UserMemory; draft: string } | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [search, setSearch] = useState<UserMemorySearch | SemanticSearch<UserMemory> | null>(null);
  const [searchMode, setSearchMode] = useState<"keyword" | "semantic">("keyword");
  const [searchError, setSearchError] = useState<string | null>(null);
  const active = useRef(true);
  const writing = useRef(false);
  const searchRequest = useRef(0);
  const searchInProgress = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setContext(null); setError(null); setStatus(null); setConfirmId(null);
    void getUserMemories(agentId).then(value => {
      if (!cancelled) setContext(value);
    }).catch(failure => {
      if (!cancelled) setError(failure instanceof ApiError ? failure.message : "Unable to load shared memories.");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [agentId, reload]);
  const disabled = loading || busy || context === null;

  function clearSearch() {
    searchRequest.current += 1;
    searchInProgress.current = false;
    setSearch(null); setSearchError(null); setSearching(false);
  }

  async function write(operation: "save" | "edit" | "delete", event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (disabled || writing.current || context === null) return;
    if (operation === "save" && editing !== null) return;
    if (operation === "delete" && (editing !== null || confirmId === null)) return;
    const content = (operation === "edit" ? editing?.draft ?? "" : draft).trim();
    if (operation !== "delete" && (!content || content.length > 2000)) return;
    if (operation === "edit" && (!editing || content === editing.memory.content)) return;
    writing.current = true; setBusy(true); setError(null); setStatus(null); clearSearch();
    try {
      if (operation === "delete") {
        await deleteUserMemory(agentId, context.user_id, confirmId!);
        if (active.current) {
          setContext({ ...context, memories: context.memories.filter(row => row.id !== confirmId) });
          setStatus(`Shared memory ${confirmId} deleted.`); setConfirmId(null);
        }
      } else {
        const saved = operation === "edit" ? await updateUserMemory(agentId, editing!.memory, content)
          : await saveUserMemory(agentId, context.user_id, content);
        if (active.current) {
          setContext({ ...context, memories: context.memories.some(row => row.id === saved.id)
            ? context.memories.map(row => row.id === saved.id ? saved : row) : [...context.memories, saved] });
          if (operation === "edit") setEditing(null); else setDraft("");
          setConfirmId(null); setStatus(`Shared memory ${saved.id} ${operation === "edit" ? "updated" : "saved"}.`);
        }
      }
    } catch (failure) {
      if (active.current) setError(failure instanceof ApiError ? failure.message :
        "Unable to change shared memory. Keep your draft and reload to check what was saved before trying again.");
    } finally {
      writing.current = false;
      if (active.current) setBusy(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (disabled || searchInProgress.current || !trimmed || trimmed.length > 500 || !context) return;
    searchInProgress.current = true;
    const request = ++searchRequest.current;
    setSearching(true); setSearch(null); setSearchError(null);
    try {
      const result = searchMode === "semantic" ? await searchSemanticUserMemories(agentId, context.user_id, trimmed)
        : await searchUserMemories(agentId, context.user_id, trimmed);
      if (active.current && request === searchRequest.current) setSearch(result);
    } catch (failure) {
      if (active.current && request === searchRequest.current) setSearchError(failure instanceof ApiError ? failure.message : "Unable to search shared memories.");
    } finally {
      if (active.current && request === searchRequest.current) { searchInProgress.current = false; setSearching(false); }
    }
  }

  return <div aria-busy={loading || busy}>
    <>
      <button type="button" disabled={loading || busy || editing !== null} onClick={() => { clearSearch(); setReload(value => value + 1); }}>Reload shared memories</button>
      {loading && <p role="status">Loading shared memories...</p>}
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      {context && <p>Shared memories for {context.username} (User {context.user_id})</p>}
      <form onSubmit={event => void write("save", event)}>
        <label htmlFor="shared-memory-content">Shared memory content</label>
        <div><textarea id="shared-memory-content" rows={3} maxLength={2000} value={draft} disabled={disabled || editing !== null}
          onChange={event => setDraft(event.target.value)} /></div>
        <p>Up to 2000 characters. Exact duplicates reuse the saved shared memory.</p>
        <button type="submit" disabled={disabled || editing !== null || !draft.trim() || draft.trim().length > 2000}>Save shared memory</button>
      </form>
      <form onSubmit={event => void handleSearch(event)}>
        <label htmlFor="shared-memory-mode">Shared memory search method</label>
        <select id="shared-memory-mode" value={searchMode} disabled={disabled}
          onChange={event => { setSearchMode(event.target.value as "keyword" | "semantic"); clearSearch(); }}>
          <option value="keyword">Keyword</option>
          <option value="semantic">Semantic (local embeddings)</option>
        </select>
        <label htmlFor="shared-memory-query">Shared memory search query</label>
        <input id="shared-memory-query" maxLength={500} value={query} disabled={disabled}
          onChange={event => { setQuery(event.target.value); clearSearch(); }} />
        <button type="submit" disabled={disabled || searching || !query.trim() || query.trim().length > 500}>Search shared memories</button>
      </form>
      {searching && <p role="status">Searching shared memories...</p>}
      {searchError && <p role="alert">{searchError}</p>}
      {search && <div>
        {"provider" in search && <p>{search.provider === "mock" ? "Mock fixture vectors" : "Ollama semantic vectors"}
          {" · Model: "}{search.model}{" · Runtime memory mode: "}{search.runtime_mode}</p>}
        {"provider" in search && <p>Cosine similarity measures how close the text vectors are. Runtime uses server configuration.</p>}
        <p>{search.results.length} relevant shared memories found.</p>
        <ol aria-label="Shared memory search results">{search.results.map(result => <li key={result.memory.id}>
          <p>Shared memory {result.memory.id} · {"similarity" in result ? `Cosine similarity: ${result.similarity.toFixed(3)}` : `Keyword matches: ${result.score}`}</p>
          <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{result.memory.content}</p>
          {"matched_terms" in result && <p>Matched text: {result.matched_terms.join(", ")}</p>}
        </li>)}</ol></div>}
      {context?.memories.length === 0 && <p>No shared memories for this user.</p>}
      {context && context.memories.length > 0 && <ul aria-label="Saved shared memories">{context.memories.map(memory => <li key={memory.id}>
        <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{memory.content}</p>
        <p>Shared memory {memory.id} · Created {memory.created_at.replace("T", " ")}</p>
        {editing?.memory.id === memory.id ? <form aria-label={`Edit shared memory ${memory.id}`} onSubmit={event => void write("edit", event)}>
          <label htmlFor="shared-memory-edit">Edited shared memory content</label>
          <div><textarea id="shared-memory-edit" rows={3} maxLength={2000} value={editing.draft} disabled={disabled}
            onChange={event => setEditing({ ...editing, draft: event.target.value })} /></div>
          <button type="submit" disabled={disabled || !editing.draft.trim() || editing.draft.trim().length > 2000 || editing.draft.trim() === memory.content}>Save shared changes</button>
          <button type="button" disabled={disabled} onClick={() => { setEditing(null); setError(null); }}>Cancel shared editing</button>
        </form> : <button type="button" disabled={disabled || editing !== null} onClick={() => {
          setEditing({ memory: { ...memory }, draft: memory.content }); setConfirmId(null); setError(null); setStatus(null);
        }}>Edit shared memory {memory.id}</button>}
        {confirmId === memory.id ? <div>
          <p>Delete shared memory {memory.id} for all Agents belonging to this user?</p>
          <button type="button" disabled={disabled} onClick={() => void write("delete")}>Confirm shared delete</button>
          <button type="button" disabled={disabled} onClick={() => setConfirmId(null)}>Keep shared memory</button>
        </div> : <button type="button" disabled={disabled || editing !== null} onClick={() => { setConfirmId(memory.id); setError(null); setStatus(null); }}>Delete shared memory {memory.id}</button>}
      </li>)}</ul>}
    </>
  </div>;
}
