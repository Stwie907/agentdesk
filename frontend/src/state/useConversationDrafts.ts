import { useEffect, useRef, useState } from "react";
import type { Conversation } from "../types/conversations";
import {
  clearAgentDrafts, draftPreferenceKey, readConversationDraft, readDraftPreference,
  removeConversationDraft, writeConversationDraft, writeDraftPreference, type ConversationDraft,
} from "./conversationDraftStorage";

type Fields = Pick<ConversationDraft, "message" | "renameTitle">;

export function useConversationDrafts(agentId: number) {
  const [initial] = useState(() => readDraftPreference(agentId));
  const [enabled, setEnabled] = useState(initial.value);
  const [error, setError] = useState(initial.error);
  const enabledRef = useRef(enabled);
  const memory = useRef(new Map<number, ConversationDraft>());

  useEffect(() => {
    function changed(event: StorageEvent) {
      if (event.key !== null && event.key !== draftPreferenceKey(agentId)) return;
      try { if (event.storageArea && event.storageArea !== window.localStorage) return; } catch { return; }
      const preference = readDraftPreference(agentId);
      enabledRef.current = preference.value;
      setEnabled(preference.value);
      setError(preference.error);
    }
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, [agentId]);

  function remember(row: Conversation, fields: Fields, save = true) {
    const draft = { ...fields, baseTitle: row.title, conversationCreatedAt: row.created_at };
    memory.current.set(row.id, draft);
    if (save && enabledRef.current) setError(writeConversationDraft(agentId, row.id, draft).error);
  }

  function restore(row: Conversation): ConversationDraft | null {
    const cached = memory.current.get(row.id);
    if (cached?.conversationCreatedAt === row.created_at) return cached;
    memory.current.delete(row.id);
    if (!enabledRef.current) return null;
    const saved = readConversationDraft(row);
    if (saved.error) setError(saved.error);
    if (saved.value) memory.current.set(row.id, saved.value);
    return saved.value;
  }

  function forget(conversationId: number) {
    memory.current.delete(conversationId);
    const result = removeConversationDraft(agentId, conversationId);
    if (result.error) setError(result.error);
  }

  function commitSaved(row: Conversation, fields: Partial<Fields>) {
    if (enabledRef.current) return;
    const saved = readConversationDraft(row);
    if (saved.error) setError(saved.error);
    if (saved.value) setError(writeConversationDraft(agentId, row.id,
      { ...saved.value, ...fields, baseTitle: row.title }).error);
  }

  function toggle(next: boolean) {
    const preference = writeDraftPreference(agentId, next);
    if (next && !preference.value) { setError(preference.error); return; }
    enabledRef.current = next;
    setEnabled(next);
    let failure = preference.error;
    if (next) {
      for (const [id, draft] of memory.current) {
        const result = writeConversationDraft(agentId, id, draft);
        if (result.error) failure = result.error;
      }
    }
    setError(failure);
  }

  function clearSaved(): boolean {
    enabledRef.current = false;
    setEnabled(false);
    const result = clearAgentDrafts(agentId);
    setError(result.error);
    return result.value;
  }

  return { enabled, error, remember, restore, forget, commitSaved, toggle, clearSaved };
}
