import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  createConversation, deleteConversation, getConversationMessages, getConversations,
  renameConversation, sendConversationMessage,
} from "../api/conversations";
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
  const [selectedId, setSelectedId] = useState("");
  const [title, setTitle] = useState("");
  const [renameTitle, setRenameTitle] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listLoaded, setListLoaded] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [messagesLoaded, setMessagesLoaded] = useState(false);
  const [listKey, setListKey] = useState(0);
  const [messageKey, setMessageKey] = useState(0);
  const [pending, setPending] = useState<"create" | "chat" | "rename" | "delete" | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const mounted = useRef(true);
  const writeInProgress = useRef(false);
  const selectedConversation = conversations.find((row) => String(row.id) === selectedId);
  const conversationId = selectedConversation?.id ?? null;

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
    setLoadingList(true);
    setListLoaded(false);
    setListError(null);
    async function load() {
      try {
        const rows = await getConversations(agentId);
        if (!cancelled) {
          setConversations(rows);
          setSelectedId((current) => rows.some((row) => String(row.id) === current) ? current : "");
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
  }, [agentId, listKey]);

  useEffect(() => {
    let cancelled = false;
    setMessages([]);
    setMessagesLoaded(false);
    setMessageError(null);
    setLoadingMessages(conversationId !== null);
    if (conversationId === null) return;
    async function load() {
      try {
        const rows = await getConversationMessages(conversationId!, agentId);
        if (!cancelled) {
          setMessages(rows);
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
        setConversations((rows) => [...rows, saved]);
        setSelectedId(String(saved.id));
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

  const managementDisabled = pending !== null || confirmDelete || loadingList || !listLoaded || conversationId === null;
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
        setConversations((rows) => rows.map((row) => row.id === saved.id ? saved : row));
        setRenameTitle(saved.title);
        setNotice(`Conversation ${saved.id} renamed.`);
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
        setSelectedId("");
        setMessage("");
        setMessages([]);
        setMessagesLoaded(false);
        setLoadingMessages(false);
        setMessageError(null);
        setNotice(`Conversation ${conversationId} deleted. Agent memories and execution history were kept.`);
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
    <div aria-busy={pending !== null || loadingList || loadingMessages}>
      <p>Conversations for Agent {agentId}</p>
      <button type="button" disabled={loadingList || pending !== null || confirmDelete} onClick={() => setListKey((key) => key + 1)}>
        Reload conversations
      </button>
      {loadingList && <p role="status">Loading conversations...</p>}
      {listError !== null && <p role="alert">{listError}</p>}
      {listLoaded && conversations.length === 0 && <p>No conversations for this Agent.</p>}
      <form onSubmit={(event) => void handleCreate(event)}>
        <label htmlFor="conversation-title">New conversation title</label>
        <input id="conversation-title" value={title} maxLength={200}
          disabled={loadingList || !listLoaded || pending !== null || confirmDelete}
          onChange={(event) => { setTitle(event.target.value); setWriteError(null); }} />
        <button type="submit" disabled={loadingList || !listLoaded || pending !== null || confirmDelete || !title.trim() || title.trim().length > 200}>
          {pending === "create" ? "Creating..." : "Create conversation"}
        </button>
      </form>
      <label htmlFor="conversation-select">Conversation</label>
      <select id="conversation-select" value={selectedId}
        disabled={loadingList || !listLoaded || pending !== null || confirmDelete || conversations.length === 0}
        onChange={(event) => { setSelectedId(event.target.value); setMessage(""); setNotice(null); setWriteError(null); }}>
        <option value="">Select a conversation</option>
        {conversations.map((row) => <option key={row.id} value={row.id}>{row.title} (ID: {row.id})</option>)}
      </select>
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
      <button type="button" disabled={conversationId === null || loadingMessages || pending !== null || confirmDelete}
        onClick={() => setMessageKey((key) => key + 1)}>Reload messages</button>
      {conversationId === null && <p>Create or select a conversation to send a message.</p>}
      {conversationId !== null && loadingMessages && <p role="status">Loading messages...</p>}
      {conversationId !== null && messageError !== null && <p role="alert">{messageError}</p>}
      {conversationId !== null && messagesLoaded && messages.length === 0 && <p>No messages in this conversation.</p>}
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
