import { type FormEvent, useEffect, useRef, useState } from "react";

import { getSavedMessage, searchConversationMessages, type MessageRoleFilter, type MessageSearchItem, type MessageSearchPage } from "../api/messageSearch";
import { ApiError } from "../api/executions";
import type { ConversationMessage } from "../types/conversations";

type Props = { conversationId: number; agentId: number; disabled: boolean; revision: number };

function Preview({ item }: { item: MessageSearchItem }) {
  const text = [...item.snippet];
  return <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
    {item.truncated_before && "…"}{text.slice(0, item.match_start).join("")}
    <mark>{text.slice(item.match_start, item.match_end).join("")}</mark>
    {text.slice(item.match_end).join("")}{item.truncated_after && "…"}
  </p>;
}

export function ConversationMessageSearch({ conversationId, agentId, disabled, revision }: Props) {
  const [draft, setDraft] = useState("");
  const [role, setRole] = useState<MessageRoleFilter>(null);
  const [limit, setLimit] = useState(10);
  const [page, setPage] = useState<MessageSearchPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationMessage | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const generation = useRef(0);
  const searchRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const searching = useRef(false);
  const reading = useRef(false);

  function cancel() {
    generation.current += 1;
    searchRequest.current?.abort(); detailRequest.current?.abort();
    searching.current = false; reading.current = false;
  }

  function clearResults() {
    cancel(); setPage(null); setLoading(false); setError(null);
    setDetail(null); setDetailId(null); setDetailError(null);
  }

  useEffect(() => {
    clearResults();
    return cancel;
  }, [conversationId, agentId, revision]);

  useEffect(() => {
    if (disabled) clearResults();
  }, [disabled]);

  async function search(offset = 0) {
    const query = draft.trim();
    if (disabled || searching.current || !query || [...query].length > 200) return;
    cancel();
    const current = generation.current;
    const controller = new AbortController(); searchRequest.current = controller;
    searching.current = true; setLoading(true); setError(null); setPage(null);
    setDetail(null); setDetailId(null); setDetailError(null);
    try {
      const result = await searchConversationMessages(conversationId, agentId, query, role, limit, offset, controller.signal);
      if (generation.current === current) setPage(result);
    } catch (failure) {
      if (generation.current === current) setError(failure instanceof ApiError ? failure.message : "Unable to search saved messages. Your drafts were kept. Search again to retry.");
    } finally {
      if (generation.current === current) { searching.current = false; setLoading(false); }
    }
  }

  async function read(item: MessageSearchItem) {
    if (disabled || searching.current || reading.current) return;
    detailRequest.current?.abort();
    const current = generation.current;
    const controller = new AbortController(); detailRequest.current = controller;
    reading.current = true; setDetail(null); setDetailId(item.id); setDetailError(null);
    try {
      const result = await getSavedMessage(conversationId, agentId, item.id, controller.signal);
      if (result.role !== item.role || result.created_at !== item.created_at) throw new ApiError(502, "The saved message changed. Search again before opening it.");
      if (generation.current === current && !controller.signal.aborted) setDetail(result);
    } catch (failure) {
      if (generation.current === current && !controller.signal.aborted) setDetailError(failure instanceof ApiError && failure.status === 404 ?
        "This saved message is no longer available. Search again to refresh the results." :
        failure instanceof ApiError ? failure.message : "Unable to load the full message. Your drafts were kept. Choose Read full message to retry.");
    } finally {
      if (generation.current === current && !controller.signal.aborted) { reading.current = false; setDetailId(null); }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void search(); }

  return <section aria-labelledby="message-search-heading" aria-busy={loading || detailId !== null}>
    <h3 id="message-search-heading">Search saved messages</h3>
    <p>Search the complete saved history, including messages outside the loaded page. Matching is literal.</p>
    <form aria-label="Search conversation messages" onSubmit={submit}>
      <label htmlFor="message-search-query">Message content search</label>
      <input id="message-search-query" value={draft} maxLength={400} disabled={disabled}
        onChange={(event) => { setDraft(event.target.value); clearResults(); }} />
      <label htmlFor="message-search-role">Message role</label>
      <select id="message-search-role" value={role ?? ""} disabled={disabled}
        onChange={(event) => { setRole((event.target.value || null) as MessageRoleFilter); clearResults(); }}>
        <option value="">All roles</option><option value="user">User</option><option value="assistant">Assistant</option>
        <option value="system">System</option><option value="tool">Tool</option>
      </select>
      <label htmlFor="message-search-limit">Search results per page</label>
      <select id="message-search-limit" value={limit} disabled={disabled}
        onChange={(event) => { setLimit(Number(event.target.value)); clearResults(); }}>
        {[5, 10, 20, 50].map((size) => <option key={size} value={size}>{size}</option>)}
      </select>
      <button type="submit" disabled={disabled || loading || !draft.trim() || [...draft.trim()].length > 200}>
        {loading ? "Searching messages..." : "Search messages"}
      </button>
      <button type="button" disabled={disabled || (!draft && page === null && error === null)}
        onClick={() => { setDraft(""); clearResults(); }}>Clear message search</button>
    </form>
    {[...draft.trim()].length > 200 && <p role="alert">Use a message search query of 1 to 200 characters.</p>}
    {error !== null && <p role="alert">{error}</p>}
    {page !== null && <>
      <p role="status">Showing {page.items.length ? page.offset + 1 : 0}–{page.items.length ? page.offset + page.items.length : 0} of {page.total} matching messages.</p>
      {page.items.length === 0 && <p>No saved messages match this search. Search again to refresh changed history.</p>}
      <nav aria-label="Message search pages">
        <button type="button" disabled={disabled || loading || page.offset === 0}
          onClick={() => void search(Math.max(0, page.offset - limit))}>Previous matching messages</button>
        <button type="button" disabled={disabled || loading || !page.has_more}
          onClick={() => void search(page.offset + limit)}>Next matching messages</button>
      </nav>
      <ol aria-label="Message search results">
        {page.items.map((item) => <li key={item.id}>
          <p><strong>{item.role}</strong> · Message {item.id} · {item.created_at}</p>
          <Preview item={item} />
          <button type="button" disabled={disabled || detailId !== null}
            onClick={() => void read(item)}>Read full message {item.id}</button>
        </li>)}
      </ol>
    </>}
    {detailId !== null && <p role="status">Loading full message {detailId}...</p>}
    {detailError !== null && <p role="alert">{detailError}</p>}
    {detail !== null && <section aria-label="Full saved message">
      <h4>Full message {detail.id}</h4>
      <p>{detail.role} · {detail.created_at}</p>
      <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{detail.content}</p>
      <button type="button" onClick={() => setDetail(null)}>Close full message</button>
    </section>}
  </section>;
}
