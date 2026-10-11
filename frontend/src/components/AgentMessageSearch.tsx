import { type FormEvent, useEffect, useRef, useState } from "react";

import { searchAgentMessages, type AgentMessageSearchItem, type AgentMessageSearchPage } from "../api/agentMessageSearch";
import { ApiError } from "../api/executions";
import { getSavedMessage, type MessageRoleFilter } from "../api/messageSearch";
import { getMessageNavigationTarget, type MessageNavigationTarget } from "../api/messageNavigation";
import type { ConversationMessage } from "../types/conversations";
import { ConversationMessageContext } from "./ConversationMessageContext";

type Props = {
  agentId: number; disabled: boolean; revision: number; navigationRevision?: number;
  onOpenMessage?: (target: MessageNavigationTarget) => boolean;
};

export function AgentMessageSearch({ agentId, disabled, revision, navigationRevision = 0, onOpenMessage }: Props) {
  const [draft, setDraft] = useState("");
  const [role, setRole] = useState<MessageRoleFilter>(null);
  const [limit, setLimit] = useState(10);
  const [page, setPage] = useState<AgentMessageSearchPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationMessage | null>(null);
  const [detailItem, setDetailItem] = useState<AgentMessageSearchItem | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [contextMessage, setContextMessage] = useState<AgentMessageSearchItem | null>(null);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const navigationGeneration = useRef(0);
  const navigationRequest = useRef<AbortController | null>(null);
  const opening = useRef(false);
  const generation = useRef(0);
  const searchRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const searching = useRef(false);
  const reading = useRef(false);
  const scope = useRef({ agentId, disabled, revision, navigationRevision, onOpenMessage });
  const evidence = useRef({ agentId, revision });
  scope.current = { agentId, disabled, revision, navigationRevision, onOpenMessage };
  const visible = !disabled && evidence.current.agentId === agentId && evidence.current.revision === revision;

  function cancelOpen() {
    navigationGeneration.current += 1; navigationRequest.current?.abort(); opening.current = false;
  }

  function cancel() {
    generation.current += 1; searchRequest.current?.abort(); detailRequest.current?.abort();
    searching.current = false; reading.current = false;
    cancelOpen();
  }

  function clearResults() {
    cancel(); setPage(null); setLoading(false); setError(null);
    setDetail(null); setDetailItem(null); setDetailId(null); setDetailError(null); setContextMessage(null);
    setOpeningId(null); setOpenError(null);
  }

  function active(current: number, controller: AbortController) {
    return current === generation.current && !controller.signal.aborted && !scope.current.disabled &&
      scope.current.agentId === agentId && scope.current.revision === revision;
  }

  useEffect(() => { clearResults(); return cancel; }, [agentId, revision]);
  useEffect(() => { setDraft(""); setRole(null); setLimit(10); }, [agentId]);
  useEffect(() => { if (disabled) clearResults(); }, [disabled]);
  useEffect(() => { cancelOpen(); setOpeningId(null); setOpenError(null); }, [navigationRevision]);

  async function search(offset = 0) {
    const query = draft.trim();
    if (disabled || searching.current || !query || [...query].length > 200) return;
    clearResults();
    evidence.current = { agentId, revision };
    const current = generation.current;
    const controller = new AbortController(); searchRequest.current = controller;
    searching.current = true; setLoading(true);
    try {
      const result = await searchAgentMessages(agentId, query, role, limit, offset, controller.signal);
      if (active(current, controller)) setPage(result);
    } catch (failure) {
      if (active(current, controller)) setError(failure instanceof ApiError ? failure.message :
        "Unable to search Agent messages. Your drafts were kept. Search again to retry.");
    } finally {
      if (active(current, controller)) { searching.current = false; setLoading(false); }
    }
  }

  async function read(item: AgentMessageSearchItem) {
    if (disabled || searching.current || reading.current) return;
    cancelOpen(); setOpeningId(null); setOpenError(null);
    setContextMessage(null); detailRequest.current?.abort();
    const current = generation.current;
    const controller = new AbortController(); detailRequest.current = controller;
    reading.current = true; setDetail(null); setDetailItem(item); setDetailId(item.id); setDetailError(null);
    try {
      const result = await getSavedMessage(item.conversation_id, agentId, item.id, controller.signal);
      if (result.role !== item.role || result.created_at !== item.created_at) {
        throw new ApiError(502, "The saved message changed. Search Agent messages again before opening it.");
      }
      if (active(current, controller)) setDetail(result);
    } catch (failure) {
      if (active(current, controller)) setDetailError(failure instanceof ApiError && failure.status === 404 ?
        "This saved message is no longer available. Search Agent messages again to refresh the results." :
        failure instanceof ApiError ? failure.message : "Unable to load the full message. Your drafts were kept. Choose Read full Agent message to retry.");
    } finally {
      if (active(current, controller)) { reading.current = false; setDetailId(null); }
    }
  }

  async function openMessage(item: AgentMessageSearchItem) {
    if (disabled || !onOpenMessage || searching.current || opening.current) return;
    cancelOpen(); detailRequest.current?.abort(); reading.current = false;
    setDetail(null); setDetailItem(null); setDetailId(null); setDetailError(null); setContextMessage(null);
    const current = generation.current, navigation = navigationGeneration.current;
    const controller = new AbortController(); navigationRequest.current = controller;
    opening.current = true; setOpeningId(item.id); setOpenError(null);
    function currentRequest() {
      return active(current, controller) && navigation === navigationGeneration.current &&
        scope.current.navigationRevision === navigationRevision && !!scope.current.onOpenMessage;
    }
    try {
      const target = await getMessageNavigationTarget(agentId, item, controller.signal);
      if (currentRequest() && !scope.current.onOpenMessage!(target)) {
        throw new ApiError(409, "Finish the current conversation action before opening another saved message.");
      }
    } catch (failure) {
      if (currentRequest()) setOpenError(failure instanceof ApiError && failure.status === 404 ?
        "This saved conversation or message is no longer available. Search Agent messages again to refresh the results." :
        failure instanceof ApiError ? failure.message : "Unable to open this conversation. Your current chat and drafts were kept. Choose Open message in chat to retry.");
    } finally {
      if (currentRequest()) { opening.current = false; setOpeningId(null); }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void search(); }

  return <section aria-labelledby="agent-message-search-heading" aria-busy={loading || detailId !== null || openingId !== null}>
    <h3 id="agent-message-search-heading">Search all Agent conversations</h3>
    <p>Search saved message content across all conversations for Agent {agentId}. You do not need to select a conversation. Reading results keeps your current chat and drafts.</p>
    <form aria-label="Search Agent conversation messages" onSubmit={submit}>
      <label htmlFor="agent-message-search-query">Agent message content search</label>
      <input id="agent-message-search-query" value={draft} maxLength={400} disabled={disabled}
        onChange={(event) => { setDraft(event.target.value); clearResults(); }} />
      <label htmlFor="agent-message-search-role">Agent message role</label>
      <select id="agent-message-search-role" value={role ?? ""} disabled={disabled}
        onChange={(event) => { setRole((event.target.value || null) as MessageRoleFilter); clearResults(); }}>
        <option value="">All roles</option><option value="user">User</option><option value="assistant">Assistant</option>
        <option value="system">System</option><option value="tool">Tool</option>
      </select>
      <label htmlFor="agent-message-search-limit">Agent search results per page</label>
      <select id="agent-message-search-limit" value={limit} disabled={disabled}
        onChange={(event) => { setLimit(Number(event.target.value)); clearResults(); }}>
        {[5, 10, 20, 50].map((size) => <option key={size} value={size}>{size}</option>)}
      </select>
      <button type="submit" disabled={disabled || loading || !draft.trim() || [...draft.trim()].length > 200}>
        {loading ? "Searching Agent messages..." : "Search Agent messages"}
      </button>
      <button type="button" disabled={disabled || (!draft && page === null && error === null)}
        onClick={() => { setDraft(""); clearResults(); }}>Clear Agent message search</button>
    </form>
    {[...draft.trim()].length > 200 && <p role="alert">Use an Agent message search query of 1 to 200 characters.</p>}
    {visible && error !== null && <p role="alert">{error}</p>}
    {visible && page !== null && <>
      <p role="status">Showing {page.items.length ? page.offset + 1 : 0}–{page.items.length ? page.offset + page.items.length : 0} of {page.total} matching Agent messages.</p>
      {page.items.length === 0 && <p>No saved messages match for this Agent. Search again to refresh changed history.</p>}
      <nav aria-label="Agent message search pages">
        <button type="button" disabled={disabled || loading || page.offset === 0}
          onClick={() => void search(Math.max(0, page.offset - limit))}>Previous Agent matching messages</button>
        <button type="button" disabled={disabled || loading || !page.has_more}
          onClick={() => void search(page.offset + limit)}>Next Agent matching messages</button>
      </nav>
      <ol aria-label="Agent message search results">
        {page.items.map((item) => {
          const text = [...item.snippet];
          return <li key={item.id}>
            <p style={{ overflowWrap: "anywhere" }}><strong>Conversation {item.conversation_id}: {item.conversation_title}</strong></p>
            <p>{item.role} · Message {item.id} · {item.created_at}</p>
            <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{item.truncated_before && "…"}
              {text.slice(0, item.match_start).join("")}<mark>{text.slice(item.match_start, item.match_end).join("")}</mark>
              {text.slice(item.match_end).join("")}{item.truncated_after && "…"}</p>
            <button type="button" disabled={disabled || detailId !== null}
              onClick={() => void read(item)}>Read full Agent message {item.id}</button>
            <button type="button" disabled={disabled || detailId !== null || contextMessage?.id === item.id}
              onClick={() => { cancelOpen(); setOpeningId(null); setOpenError(null);
                setDetail(null); setDetailItem(null); setDetailError(null); setContextMessage(item); }}>Read Agent message context {item.id}</button>
            {onOpenMessage && <button type="button" disabled={disabled || openingId !== null}
              onClick={() => void openMessage(item)}>Open message {item.id} in chat</button>}
          </li>;
        })}
      </ol>
    </>}
    {visible && detailId !== null && <p role="status">Loading full Agent message {detailId}...</p>}
    {visible && detailError !== null && <p role="alert">{detailError}</p>}
    {visible && openingId !== null && <>
      <p role="status">Opening conversation for message {openingId}...</p>
      <button type="button" onClick={() => { cancelOpen(); setOpeningId(null); setOpenError(null); }}>Cancel opening message</button>
    </>}
    {visible && openError !== null && <p role="alert">{openError}</p>}
    {visible && contextMessage !== null && <section aria-label="Agent search message context">
      <p>Conversation {contextMessage.conversation_id}: {contextMessage.conversation_title}</p>
      <ConversationMessageContext key={`agent-context-${contextMessage.conversation_id}-${contextMessage.id}`}
        conversationId={contextMessage.conversation_id} agentId={agentId} message={contextMessage} disabled={disabled}
        onClose={() => setContextMessage(null)} />
    </section>}
    {visible && detail !== null && detailItem !== null && <section aria-label="Full Agent saved message">
      <h4>Full message {detail.id} from conversation {detail.conversation_id}</h4>
      <p>Conversation title: {detailItem.conversation_title}</p>
      <p>{detail.role} · {detail.created_at}</p>
      <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{detail.content}</p>
      <button type="button" onClick={() => { setDetail(null); setDetailItem(null); }}>Close full Agent message</button>
    </section>}
  </section>;
}
