import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  compareConversationMessages, createConversation, deleteConversation, getConversation, getConversationMessagePage, getConversationPage,
  renameConversation, sendConversationMessage,
} from "../api/conversations";
import { ConversationExport } from "./ConversationExport";
import { ConversationImport } from "./ConversationImport";
import { ConversationMessageSearch } from "./ConversationMessageSearch";
import { ApiError } from "../api/executions";
import type { Conversation, ConversationMessage } from "../types/conversations";

type Props = {
  agentId: number | null;
  onActivity: (agentId: number, executionId: number) => void;
};

export function ConversationPanel({ agentId, onActivity }: Props) {
  return (
    <section aria-labelledby="conversation-heading">
      <h2 id="conversation-heading">Conversation Chat</h2>
      {agentId === null ? <p>Select an Agent above to start or continue a conversation.</p> :
        <AgentConversations key={agentId} agentId={agentId} onActivity={onActivity} />}
    </section>
  );
}

function AgentConversations({ agentId, onActivity }: { agentId: number; onActivity: Props["onActivity"] }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [searchDraft, setSearchDraft] = useState("");
  const [browse, setBrowse] = useState({ query: "", limit: 10, offset: 0 });
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [title, setTitle] = useState("");
  const [renameTitle, setRenameTitle] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listLoaded, setListLoaded] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [messagesLoaded, setMessagesLoaded] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderError, setOlderError] = useState<string | null>(null);
  const [nextBeforeId, setNextBeforeId] = useState<number | null>(null);
  const [listKey, setListKey] = useState(0);
  const [messageKey, setMessageKey] = useState(0);
  const [pending, setPending] = useState<"create" | "chat" | "rename" | "delete" | "import" | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mounted = useRef(true);
  const writeInProgress = useRef(false);
  const selectedRef = useRef<Conversation | null>(null);
  const validateSelection = useRef(false);
  const messageGeneration = useRef(0);
  const olderInProgress = useRef(false);
  const selectedId = selectedConversation === null ? "" : String(selectedConversation.id);
  const conversationId = selectedConversation?.id ?? null;

  function chooseConversation(row: Conversation | null) {
    selectedRef.current = row;
    setSelectedConversation(row);
  }

  function refreshList(validateCurrent = false) {
    validateSelection.current = validateCurrent;
    setLoadingList(true);
    setListLoaded(false);
    setListKey((key) => key + 1);
  }

  function changeBrowse(next: typeof browse) {
    setLoadingList(true);
    setListLoaded(false);
    setListError(null);
    setBrowse(next);
    setListKey((key) => key + 1);
  }

  useEffect(() => {
    setRenameTitle(selectedConversation?.title ?? "");
    setConfirmDelete(false);
  }, [conversationId]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const current = selectedRef.current;
    const validateCurrent = validateSelection.current;
    validateSelection.current = false;
    setLoadingList(true);
    setListLoaded(false);
    setListError(null);
    async function load() {
      try {
        const page = await getConversationPage(agentId, browse.query, browse.limit, browse.offset);
        if (cancelled) return;
        if (browse.offset > 0 && browse.offset >= page.total) {
          validateSelection.current = validateCurrent;
          setBrowse((previous) => ({ ...previous, offset: page.total === 0 ? 0 : Math.floor((page.total - 1) / browse.limit) * browse.limit }));
          return;
        }
        let selected = page.items.find((row) => row.id === current?.id) ?? current;
        if (validateCurrent && current && !page.items.some((row) => row.id === current.id)) {
          try { selected = await getConversation(current.id, agentId); }
          catch (error) {
            if (!(error instanceof ApiError) || error.status !== 404) throw error;
            selected = null;
          }
        }
        if (!cancelled) {
          setConversations(page.items);
          setTotal(page.total);
          setHasMore(page.has_more);
          if (selectedRef.current?.id === current?.id) {
            chooseConversation(selected);
            if (current && selected === null) {
              setMessage("");
              setNotice("The selected conversation was removed. Choose another conversation.");
            }
          }
          setListLoaded(true);
        }
      } catch (error) {
        if (!cancelled) setListError(error instanceof ApiError ? error.message : "Unable to load conversations.");
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [agentId, browse.query, browse.limit, browse.offset, listKey]);

  useEffect(() => {
    let cancelled = false;
    messageGeneration.current += 1;
    olderInProgress.current = false;
    setLoadingOlder(false);
    setOlderError(null);
    setNextBeforeId(null);
    setMessages([]);
    setMessagesLoaded(false);
    setMessageError(null);
    setLoadingMessages(conversationId !== null);
    if (conversationId === null) return;
    async function load() {
      try {
        const page = await getConversationMessagePage(conversationId!, agentId);
        if (!cancelled) {
          setMessages(page.items);
          setNextBeforeId(page.next_before_id);
          setMessagesLoaded(true);
        }
      } catch (error) {
        if (!cancelled) setMessageError(error instanceof ApiError ? error.message :
          "Unable to load messages. Use Reload messages to check the saved conversation before sending again.");
      } finally {
        if (!cancelled) setLoadingMessages(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [agentId, conversationId, messageKey]);

  async function loadOlderMessages() {
    if (conversationId === null || nextBeforeId === null || loadingMessages || !messagesLoaded ||
        pending !== null || confirmDelete || olderInProgress.current) return;
    const generation = messageGeneration.current;
    const anchor = messages[0];
    if (!anchor || anchor.id !== nextBeforeId) return;
    olderInProgress.current = true;
    setLoadingOlder(true);
    setOlderError(null);
    try {
      const page = await getConversationMessagePage(conversationId, agentId, 20, nextBeforeId);
      if (!mounted.current || generation !== messageGeneration.current || selectedRef.current?.id !== conversationId) return;
      const existing = new Set(messages.map((row) => row.id));
      if (page.items.some((row) => existing.has(row.id) || compareConversationMessages(row, anchor) >= 0)) {
        throw new ApiError(502, "The server returned overlapping history. Reload messages before continuing.");
      }
      setMessages((rows) => [...page.items, ...rows]);
      setNextBeforeId(page.next_before_id);
    } catch (error) {
      if (mounted.current && generation === messageGeneration.current) {
        setOlderError(error instanceof ApiError ? error.message : "Unable to load older messages. Your loaded messages and draft were kept. Try again.");
      }
    } finally {
      if (mounted.current && generation === messageGeneration.current) {
        olderInProgress.current = false;
        setLoadingOlder(false);
      }
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (writeInProgress.current || confirmDelete || loadingList || !listLoaded || !title.trim() || title.trim().length > 200) return;
    writeInProgress.current = true;
    setPending("create");
    setWriteError(null);
    setNotice(null);
    try {
      const saved = await createConversation(agentId, title);
      if (mounted.current) {
        chooseConversation(saved);
        setSearchDraft("");
        changeBrowse({ ...browse, query: "", offset: 0 });
        setTitle("");
        setMessage("");
        setNotice(`Conversation ${saved.id} created.`);
      }
    } catch (error) {
      if (mounted.current) setWriteError(error instanceof ApiError ? error.message :
        "Unable to create conversation. Reload conversations to check whether it was created before trying again.");
    } finally {
      writeInProgress.current = false;
      if (mounted.current) setPending(null);
    }
  }

  const managementDisabled = pending !== null || confirmDelete || loadingList || !listLoaded || loadingOlder || conversationId === null;
  const chatDisabled = managementDisabled || loadingMessages || !messagesLoaded;

  function managementError(error: unknown, action: string): string {
    if (error instanceof ApiError && error.status === 404) {
      return "Conversation not found for this Agent. Reload conversations to refresh the list.";
    }
    if (error instanceof ApiError && error.status === 422) return error.message;
    return `Unable to ${action} conversation. Reload conversations to check its saved state before trying again.`;
  }

  async function handleRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (managementDisabled || writeInProgress.current || conversationId === null ||
        !renameTitle.trim() || renameTitle.trim().length > 200 || renameTitle.trim() === selectedConversation?.title) return;
    writeInProgress.current = true;
    setPending("rename");
    setWriteError(null);
    setNotice(null);
    try {
      const saved = await renameConversation(conversationId, agentId, renameTitle);
      if (mounted.current) {
        chooseConversation(saved);
        setConversations((rows) => rows.map((row) => row.id === saved.id ? saved : row));
        setRenameTitle(saved.title);
        setNotice(`Conversation ${saved.id} renamed.`);
        if (browse.query) refreshList();
      }
    } catch (error) {
      if (mounted.current) setWriteError(managementError(error, "rename"));
    } finally {
      writeInProgress.current = false;
      if (mounted.current) setPending(null);
    }
  }

  async function handleDelete() {
    if (!confirmDelete || writeInProgress.current || pending !== null || loadingList || !listLoaded || conversationId === null) return;
    writeInProgress.current = true;
    setPending("delete");
    setWriteError(null);
    setNotice(null);
    try {
      await deleteConversation(conversationId, agentId);
      if (mounted.current) {
        setConversations((rows) => rows.filter((row) => row.id !== conversationId));
        chooseConversation(null);
        setMessage("");
        setMessages([]);
        setMessagesLoaded(false);
        setLoadingMessages(false);
        setMessageError(null);
        setNotice(`Conversation ${conversationId} deleted. Agent memories and execution history were kept.`);
        refreshList();
      }
    } catch (error) {
      if (mounted.current) setWriteError(managementError(error, "delete"));
    } finally {
      writeInProgress.current = false;
      if (mounted.current) {
        setPending(null);
        setConfirmDelete(false);
      }
    }
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (chatDisabled || writeInProgress.current || conversationId === null || !message.trim() || message.trim().length > 4000) return;
    writeInProgress.current = true;
    setPending("chat");
    setWriteError(null);
    setNotice(null);
    try {
      const reply = await sendConversationMessage(conversationId, agentId, message);
      if (mounted.current) {
        if (reply.status === "completed") setMessage("");
        setNotice(`Execution ${reply.execution_id} returned with status: ${reply.status}.` +
          (reply.status === "completed" ? "" : " Inspect the execution before sending another message."));
        setMessageKey((key) => key + 1);
        onActivity(agentId, reply.execution_id);
      }
    } catch (error) {
      if (mounted.current) setWriteError(error instanceof ApiError ? error.message :
        "Unable to send message. Reload messages to check whether it was saved before sending again.");
    } finally {
      writeInProgress.current = false;
      if (mounted.current) setPending(null);
    }
  }

  return (
    <div aria-busy={pending !== null || loadingList || loadingMessages || loadingOlder}>
      <p>Conversations for Agent {agentId}</p>
      <form onSubmit={(event) => {
        event.preventDefault();
        if (loadingList || pending !== null || confirmDelete || searchDraft.trim().length > 200) return;
        changeBrowse({ ...browse, query: searchDraft.trim(), offset: 0 });
      }}>
        <label htmlFor="conversation-search">Conversation title search</label>
        <input id="conversation-search" value={searchDraft} maxLength={200}
          disabled={loadingList || pending !== null || confirmDelete}
          onChange={(event) => setSearchDraft(event.target.value)} />
        <button type="submit" disabled={loadingList || pending !== null || confirmDelete || searchDraft.trim().length > 200}>
          Search conversations
        </button>
        <button type="button" disabled={loadingList || pending !== null || confirmDelete || (!searchDraft && !browse.query)}
          onClick={() => {
            setSearchDraft("");
            if (browse.query) changeBrowse({ ...browse, query: "", offset: 0 });
          }}>Clear conversation search</button>
      </form>
      <label htmlFor="conversation-page-size">Conversations per page</label>
      <select id="conversation-page-size" value={browse.limit} disabled={loadingList || pending !== null || confirmDelete}
        onChange={(event) => changeBrowse({ ...browse, limit: Number(event.target.value), offset: 0 })}>
        {[5, 10, 20, 50].map((size) => <option key={size} value={size}>{size}</option>)}
      </select>
      <button type="button" disabled={loadingList || pending !== null || confirmDelete} onClick={() => refreshList(true)}>
        Reload conversations
      </button>
      {loadingList && <p role="status">Loading conversations...</p>}
      {listError !== null && <p role="alert">{listError}</p>}
      {listLoaded && total === 0 && <p>{browse.query ? "No conversations match this title search." : "No conversations for this Agent."}</p>}
      {listLoaded && <p>Showing {total === 0 ? 0 : browse.offset + 1}–{browse.offset + conversations.length} of {total} conversations.
        {browse.query && <> Title contains “{browse.query}”.</>}</p>}
      <nav aria-label="Conversation pages">
        <button type="button" disabled={loadingList || !listLoaded || pending !== null || confirmDelete || browse.offset === 0}
          onClick={() => changeBrowse({ ...browse, offset: Math.max(0, browse.offset - browse.limit) })}>Previous conversations</button>
        <button type="button" disabled={loadingList || !listLoaded || pending !== null || confirmDelete || !hasMore}
          onClick={() => changeBrowse({ ...browse, offset: browse.offset + browse.limit })}>Next conversations</button>
      </nav>
      <form onSubmit={(event) => void handleCreate(event)}>
        <label htmlFor="conversation-title">New conversation title</label>
        <input id="conversation-title" value={title} maxLength={200}
          disabled={loadingList || !listLoaded || pending !== null || confirmDelete}
          onChange={(event) => { setTitle(event.target.value); setWriteError(null); }} />
        <button type="submit" disabled={loadingList || !listLoaded || pending !== null || confirmDelete || !title.trim() || title.trim().length > 200}>
          {pending === "create" ? "Creating..." : "Create conversation"}
        </button>
      </form>
      <ConversationImport agentId={agentId} disabled={loadingList || !listLoaded || pending !== null || confirmDelete || loadingOlder}
        onStart={() => {
          if (writeInProgress.current || pending !== null || confirmDelete || loadingList || !listLoaded || loadingOlder) return false;
          writeInProgress.current = true; setPending("import"); return true;
        }}
        onFinish={() => { writeInProgress.current = false; if (mounted.current) setPending(null); }}
        onImported={() => { if (mounted.current) refreshList(); }} />
      <label htmlFor="conversation-select">Conversation</label>
      <select id="conversation-select" value={selectedId}
        disabled={loadingList || !listLoaded || pending !== null || confirmDelete || (conversations.length === 0 && !selectedConversation)}
        onChange={(event) => {
          chooseConversation(conversations.find((row) => String(row.id) === event.target.value) ??
            (event.target.value === selectedId ? selectedConversation : null));
          setMessage(""); setNotice(null); setWriteError(null);
        }}>
        <option value="">Select a conversation</option>
        {selectedConversation && !conversations.some((row) => row.id === conversationId) &&
          <optgroup label="Current conversation">
            <option value={selectedConversation.id}>{selectedConversation.title} (ID: {selectedConversation.id})</option>
          </optgroup>}
        {conversations.map((row) => <option key={row.id} value={row.id}>{row.title} (ID: {row.id})</option>)}
      </select>
      {listLoaded && selectedConversation && !conversations.some((row) => row.id === conversationId) &&
        <p>Your current conversation is outside these results. Its messages and unsent draft stay selected.</p>}
      {conversationId !== null && (
        <div>
          <form onSubmit={(event) => void handleRename(event)}>
            <label htmlFor="conversation-rename-title">Conversation title</label>
            <input id="conversation-rename-title" value={renameTitle} maxLength={200} disabled={managementDisabled}
              onChange={(event) => { setRenameTitle(event.target.value); setWriteError(null); }} />
            <button type="submit" disabled={managementDisabled || !renameTitle.trim() || renameTitle.trim().length > 200 ||
                renameTitle.trim() === selectedConversation?.title}>
              {pending === "rename" ? "Renaming..." : "Rename conversation"}
            </button>
          </form>
          <button type="button" disabled={managementDisabled} onClick={() => {
            setConfirmDelete(true); setWriteError(null); setNotice(null);
          }}>Delete conversation</button>
          {confirmDelete && (
            <div role="group" aria-labelledby="conversation-delete-prompt">
              <p id="conversation-delete-prompt">Delete “{selectedConversation?.title}” (ID: {conversationId})?</p>
              <p>Its saved messages will be removed. Agent memories and execution history will stay available.</p>
              <button type="button" disabled={pending !== null} onClick={() => void handleDelete()}>
                {pending === "delete" ? "Deleting..." : "Confirm delete"}
              </button>
              <button type="button" disabled={pending !== null} onClick={() => setConfirmDelete(false)}>Cancel delete</button>
            </div>
          )}
        </div>
      )}
      {conversationId !== null && <ConversationExport key={conversationId} conversationId={conversationId} agentId={agentId}
        disabled={pending !== null || confirmDelete} />}
      {conversationId !== null && <ConversationMessageSearch key={`message-search-${conversationId}`} conversationId={conversationId} agentId={agentId}
        disabled={pending !== null || confirmDelete || loadingList || !listLoaded}
        revision={messageKey} />}
      <button type="button" disabled={conversationId === null || loadingMessages || pending !== null || confirmDelete}
        onClick={() => setMessageKey((key) => key + 1)}>Reload messages</button>
      {conversationId === null && <p>Create or select a conversation to send a message.</p>}
      {conversationId !== null && loadingMessages && <p role="status">Loading messages...</p>}
      {conversationId !== null && messageError !== null && <p role="alert">{messageError}</p>}
      {conversationId !== null && olderError !== null && <p role="alert">{olderError}</p>}
      {conversationId !== null && messagesLoaded && messages.length === 0 && <p>No messages in this conversation.</p>}
      {conversationId !== null && messagesLoaded && messages.length > 0 && (
        <div>
          <p>{messages.length} messages loaded. {nextBeforeId === null ? "All saved messages are loaded." : "Earlier messages are available."}</p>
          <button type="button" disabled={nextBeforeId === null || loadingOlder || loadingMessages || pending !== null || confirmDelete}
            onClick={() => void loadOlderMessages()}>{loadingOlder ? "Loading older messages..." : "Load older messages"}</button>
          <p>Reload messages returns to the latest 20 messages and keeps your unsent draft.</p>
        </div>
      )}
      {conversationId !== null && messagesLoaded && messages.length > 0 && (
        <ol aria-label="Conversation messages">
          {messages.map((row) => <li key={row.id}>
            <p><strong>{row.role}</strong> · Message {row.id}</p>
            <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{row.content}</p>
          </li>)}
        </ol>
      )}
      <form onSubmit={(event) => void handleSend(event)}>
        <label htmlFor="conversation-message">Chat message</label>
        <div><textarea id="conversation-message" rows={3} maxLength={4000} value={message}
          disabled={chatDisabled} placeholder="Example: I like Python."
          onChange={(event) => { setMessage(event.target.value); setWriteError(null); }} /></div>
        <button type="submit" disabled={chatDisabled || !message.trim() || message.trim().length > 4000}>
          {pending === "chat" ? "Sending..." : "Send message"}
        </button>
      </form>
      <p>This conversation saves its messages. Phrases such as “My name is Tom” or “I like Python” save an Agent memory.</p>
      {pending === "chat" && <p role="status">Waiting for the Agent to finish...</p>}
      {writeError !== null && <p role="alert">{writeError}</p>}
      {notice !== null && <p role="status">{notice}</p>}
    </div>
  );
}
