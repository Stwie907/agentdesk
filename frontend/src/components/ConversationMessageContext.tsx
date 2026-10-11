import { useEffect, useRef, useState } from "react";

import { ApiError } from "../api/executions";
import { getMessageContext, type MessageContext } from "../api/messageContext";
import type { MessageSearchItem } from "../api/messageSearch";

type Props = {
  conversationId: number; agentId: number; message: MessageSearchItem; disabled: boolean; onClose: () => void;
};

export function ConversationMessageContext({ conversationId, agentId, message, disabled, onClose }: Props) {
  const [before, setBefore] = useState(3);
  const [after, setAfter] = useState(3);
  const [context, setContext] = useState<MessageContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);
  const reading = useRef(false);

  function cancel() {
    generation.current += 1; request.current?.abort(); reading.current = false;
  }

  function clear() {
    cancel(); setContext(null); setLoading(false); setError(null);
  }

  async function load(earlier: number, later: number) {
    if (disabled || reading.current) return;
    cancel();
    const current = generation.current;
    const controller = new AbortController(); request.current = controller;
    reading.current = true; setLoading(true); setContext(null); setError(null);
    try {
      const result = await getMessageContext(conversationId, agentId, message.id, earlier, later, controller.signal);
      const anchor = result.items[result.anchor_index];
      if (anchor.role !== message.role || anchor.created_at !== message.created_at) {
        throw new ApiError(502, "The selected saved message changed. Search again before reading its context.");
      }
      if (generation.current === current && !controller.signal.aborted) setContext(result);
    } catch (failure) {
      if (generation.current === current && !controller.signal.aborted) setError(failure instanceof ApiError && failure.status === 404 ?
        "This saved message is no longer available. Search again to refresh the results." :
        failure instanceof ApiError ? failure.message : "Unable to load message context. Your drafts were kept. Reload message context to retry.");
    } finally {
      if (generation.current === current && !controller.signal.aborted) { reading.current = false; setLoading(false); }
    }
  }

  useEffect(() => {
    setBefore(3); setAfter(3);
    const current = generation.current;
    let active = true;
    // A cancelled effect (including React Strict Mode's first setup) must not
    // start a duplicate read before the explicit result selection settles.
    void Promise.resolve().then(() => { if (active && generation.current === current) void load(3, 3); });
    return () => { active = false; cancel(); };
  }, [conversationId, agentId, message.id]);

  useEffect(() => { if (disabled) clear(); }, [disabled]);

  return <section aria-label="Saved message context" aria-busy={loading}>
    <h4>Context around message {message.id}</h4>
    <p>Read saved messages before and after this result in time order. All roles are included.</p>
    <label htmlFor={`message-context-before-${message.id}`}>Messages before selected</label>
    <select id={`message-context-before-${message.id}`} value={before} disabled={disabled}
      onChange={(event) => { setBefore(Number(event.target.value)); clear(); }}>
      {[0, 1, 3, 5, 10].map((count) => <option key={count} value={count}>{count}</option>)}
    </select>
    <label htmlFor={`message-context-after-${message.id}`}>Messages after selected</label>
    <select id={`message-context-after-${message.id}`} value={after} disabled={disabled}
      onChange={(event) => { setAfter(Number(event.target.value)); clear(); }}>
      {[0, 1, 3, 5, 10].map((count) => <option key={count} value={count}>{count}</option>)}
    </select>
    <button type="button" disabled={disabled || loading} onClick={() => void load(before, after)}>
      {loading ? "Loading message context..." : "Reload message context"}
    </button>
    <button type="button" onClick={() => { cancel(); onClose(); }}>Close message context</button>
    {error !== null && <p role="alert">{error}</p>}
    {context !== null && <>
      <p role="status">Showing {context.anchor_index} earlier messages, the selected message, and {context.items.length - context.anchor_index - 1} later messages.</p>
      {context.has_more_before && <p>Earlier saved messages remain outside this context.</p>}
      {context.has_more_after && <p>Later saved messages remain outside this context.</p>}
      <ol aria-label="Surrounding saved messages">
        {context.items.map((row) => <li key={row.id} aria-current={row.id === message.id ? "true" : undefined}>
          <p><strong>{row.id === message.id ? "Selected message" : "Saved message"} {row.id}</strong> · {row.role} · {row.created_at}</p>
          <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.content}</p>
        </li>)}
      </ol>
    </>}
  </section>;
}
