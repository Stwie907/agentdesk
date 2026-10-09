import { useEffect, useRef, useState } from "react";

import { getExecutionMemoryContext } from "../api/memoryEvidence";
import type { ExecutionMemoryContext, MemoryEvidenceItem } from "../types/memoryEvidence";

type Props = { executionId: number; agentId: number; input: string };

function CapturedMemories({ rows, name }: { rows: MemoryEvidenceItem[]; name: string }) {
  return <section aria-label={name}>
    <h4>{name}</h4>
    {rows.length === 0 ? <p>No {name.toLowerCase()} loaded.</p> : <ol>
      {rows.map(row => <li key={row.memory_id}>
        <p><strong>Memory #{row.memory_id}</strong> — {row.scope === "agent" ? "Agent" : "User"} #{row.scope_id}</p>
        <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.content}</p>
        <p>{row.similarity === null
          ? `Keyword score: ${row.score}; matched terms: ${row.matched_terms.join(", ") || "none"}`
          : `Cosine similarity: ${row.similarity.toFixed(6)}`}</p>
        <p>Memory created at: {row.created_at}</p>
      </li>)}
    </ol>}
  </section>;
}

export function MemoryRetrievalPanel({ executionId, agentId, input }: Props) {
  const [result, setResult] = useState<ExecutionMemoryContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [opened, setOpened] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const version = useRef(0);
  const inFlight = useRef(false);

  useEffect(() => {
    version.current += 1;
    inFlight.current = false;
    setResult(null); setError(null); setOpened(false); setLoading(false);
    return () => { version.current += 1; };
  }, [executionId, agentId, input]);

  async function load() {
    if (inFlight.current) return;
    inFlight.current = true;
    const requestVersion = ++version.current;
    setOpened(true); setLoading(true); setError(null); setResult(null);
    try {
      const body = await getExecutionMemoryContext(executionId, agentId, input);
      if (version.current === requestVersion) setResult(body);
    } catch (requestError) {
      if (version.current === requestVersion) {
        setError(requestError instanceof Error ? requestError.message : "Unable to load memory retrieval evidence.");
      }
    } finally {
      if (version.current === requestVersion) {
        inFlight.current = false; setLoading(false);
      }
    }
  }

  const facts = result?.evidence ?? null;
  return <section aria-labelledby="memory-retrieval-heading">
    <h3 id="memory-retrieval-heading">Memory retrieval</h3>
    <button type="button" onClick={() => void load()} disabled={loading}>
      {loading ? "Loading memory retrieval..." : opened ? "Refresh memory retrieval" : "Show memory retrieval"}
    </button>
    {error !== null && <p role="alert">{error}</p>}
    {result !== null && !result.available && <p>
      No memory retrieval evidence was recorded for this execution. Older executions, plan replays,
      and executions that have not reached retrieval may have no evidence. Refresh after an active execution finishes.
    </p>}
    {facts !== null && <>
      <p>Captured for this execution. Later memory edits or deletions do not change this record.</p>
      <dl>
        <dt>Requested mode</dt><dd>{facts.requested_mode}</dd>
        <dt>Used mode</dt><dd>{facts.mode}</dd>
        <dt>Captured at</dt><dd>{facts.recorded_at}</dd>
        <dt>Retrieval query</dt><dd>{facts.query || "Empty query"}</dd>
        <dt>Limit per scope</dt><dd>{facts.limit}</dd>
        <dt>Embedding provider</dt><dd>{facts.provider ?? "None"}</dd>
        <dt>Embedding model</dt><dd>{facts.model ?? "None"}</dd>
        {facts.min_similarity !== null && <><dt>Minimum similarity</dt><dd>{facts.min_similarity}</dd></>}
      </dl>
      {facts.provider === "mock" && <p>Mock similarity uses fixed test vectors.</p>}
      {facts.fallback_reason !== null && <p role="status">Keyword fallback: {facts.fallback_reason}</p>}
      {facts.context === "" && <p>No memories were loaded.</p>}
      <CapturedMemories rows={facts.agent_memories} name="Agent memories" />
      <CapturedMemories rows={facts.shared_memories} name="Shared user memories" />
      <details><summary>Memory context sent to Runtime</summary>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{facts.context || "Empty memory context"}</pre>
      </details>
    </>}
  </section>;
}
