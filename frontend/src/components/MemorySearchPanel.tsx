import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/executions";
import { searchMemories } from "../api/memories";
import type { MemorySearchResponse } from "../types/memories";

type Props = { agentId: number; revision: string; disabled: boolean };

export function MemorySearchPanel({ agentId, revision, disabled }: Props) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(5);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ data: MemorySearchResponse; revision: string } | null>(null);
  const [error, setError] = useState<{ message: string; revision: string } | null>(null);
  const mounted = useRef(true);
  const version = useRef(0);
  const activeRequest = useRef<number | null>(null);
  const latest = useRef({ revision, disabled });
  latest.current = { revision, disabled };

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  function invalidate() {
    version.current += 1;
    activeRequest.current = null;
    setPending(false);
    setResult(null);
    setError(null);
  }

  useEffect(() => { invalidate(); }, [revision, disabled]);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (disabled || activeRequest.current !== null || !trimmed || trimmed.length > 500) return;
    const requestVersion = ++version.current;
    const requestedRevision = revision;
    activeRequest.current = requestVersion;
    setPending(true);
    setResult(null);
    setError(null);
    const current = () => mounted.current && version.current === requestVersion &&
      latest.current.revision === requestedRevision && !latest.current.disabled;
    try {
      const data = await searchMemories(agentId, trimmed, limit);
      if (current()) setResult({ data, revision: requestedRevision });
    } catch (failure) {
      if (current()) setError({ revision: requestedRevision, message: failure instanceof ApiError ? failure.message :
        "Unable to search memories. Try Search memories again." });
    } finally {
      if (mounted.current && activeRequest.current === requestVersion) {
        activeRequest.current = null;
        setPending(false);
      }
    }
  }

  const shown = !disabled && result?.revision === revision ? result.data : null;
  return (
    <section aria-labelledby="memory-search-heading" aria-busy={pending}>
      <h3 id="memory-search-heading">Memory retrieval preview</h3>
      <p>Preview relevant memories using the same keyword rules as Runtime. The default limit is 5.</p>
      <form onSubmit={(event) => void handleSearch(event)}>
        <label htmlFor="memory-search-query">Memory search query</label>
        <input id="memory-search-query" value={query} maxLength={500} disabled={disabled}
          placeholder="Example: Python or 机器学习"
          onChange={(event) => { setQuery(event.target.value); invalidate(); }} />
        <label htmlFor="memory-search-limit">Result limit</label>
        <select id="memory-search-limit" value={limit} disabled={disabled}
          onChange={(event) => { setLimit(Number(event.target.value)); invalidate(); }}>
          {[1, 3, 5, 10, 20].map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        <button type="submit" disabled={disabled || pending || !query.trim() || query.trim().length > 500}>
          {pending ? "Searching..." : "Search memories"}
        </button>
      </form>
      <p>Search reads saved memories. It does not send a chat message or change the Runtime limit.</p>
      {pending && !disabled && <p role="status">Searching saved memories...</p>}
      {!disabled && error?.revision === revision && <p role="alert">{error.message}</p>}
      {shown !== null && <>
        <p role="status">{shown.results.length} relevant {shown.results.length === 1 ? "memory" : "memories"} found.</p>
        {shown.results.length === 0 ? <p>No relevant memories found.</p> :
          <ol aria-label="Memory search results">
            {shown.results.map((row) => <li key={row.memory.id}>
              <p>Memory {row.memory.id} · Keyword matches: {row.score}</p>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.memory.content}</p>
              <p>Matched text: {row.matched_terms.join(", ")}</p>
            </li>)}
          </ol>}
      </>}
    </section>
  );
}
