import type { Conversation } from "../types/conversations";

export type ConversationDraft = {
  message: string;
  renameTitle: string;
  baseTitle: string;
  conversationCreatedAt: string;
};

type Result<T> = { value: T; error: string | null };
const PREFIX = "agentdesk:conversation-drafts:v1:";
const MAX_RECORD_LENGTH = 64 * 1024;
const unavailable = "Browser storage could not be updated. Your drafts remain in this page; a reload may restore an older copy.";
const invalid = "A saved browser draft could not be restored. Your current page drafts were kept.";

function validId(id: number): boolean { return Number.isSafeInteger(id) && id > 0; }

export function draftPreferenceKey(agentId: number): string { return `${PREFIX}${agentId}:enabled`; }
export function conversationDraftKey(agentId: number, conversationId: number): string {
  return `${PREFIX}${agentId}:conversation:${conversationId}`;
}

export function readDraftPreference(agentId: number): Result<boolean> {
  if (!validId(agentId)) return { value: false, error: invalid };
  try {
    const raw = window.localStorage.getItem(draftPreferenceKey(agentId));
    return raw === null || raw === "false" || raw === "true" ?
      { value: raw === "true", error: null } : { value: false, error: invalid };
  } catch { return { value: false, error: unavailable }; }
}

export function writeDraftPreference(agentId: number, enabled: boolean): Result<boolean> {
  if (!validId(agentId)) return { value: false, error: invalid };
  try {
    window.localStorage.setItem(draftPreferenceKey(agentId), String(enabled));
    return { value: true, error: null };
  } catch { return { value: false, error: unavailable }; }
}

function validDraft(value: unknown): value is ConversationDraft {
  const draft = value as Partial<ConversationDraft> | null;
  return !!draft && typeof draft.message === "string" && draft.message.length <= 4000 &&
    typeof draft.renameTitle === "string" && draft.renameTitle.length <= 200 &&
    typeof draft.baseTitle === "string" && draft.baseTitle.length <= 200 &&
    typeof draft.conversationCreatedAt === "string" && draft.conversationCreatedAt.length > 0 &&
    draft.conversationCreatedAt.length <= 100;
}

export function readConversationDraft(row: Conversation): Result<ConversationDraft | null> {
  if (!validId(row.agent_id) || !validId(row.id)) return { value: null, error: invalid };
  try {
    const raw = window.localStorage.getItem(conversationDraftKey(row.agent_id, row.id));
    if (raw === null) return { value: null, error: null };
    if (raw.length > MAX_RECORD_LENGTH) return { value: null, error: invalid };
    const value = JSON.parse(raw) as Partial<ConversationDraft> & {
      schema_version?: number; agent_id?: number; conversation_id?: number;
    } | null;
    if (!value || value.schema_version !== 1 || value.agent_id !== row.agent_id ||
        value.conversation_id !== row.id || !validDraft(value) || value.conversationCreatedAt !== row.created_at) {
      return { value: null, error: invalid };
    }
    return { value: { message: value.message, renameTitle: value.renameTitle, baseTitle: value.baseTitle,
      conversationCreatedAt: value.conversationCreatedAt }, error: null };
  } catch (error) {
    return { value: null, error: error instanceof SyntaxError ? invalid : unavailable };
  }
}

export function writeConversationDraft(agentId: number, conversationId: number, draft: ConversationDraft): Result<boolean> {
  if (!validId(agentId) || !validId(conversationId) || !validDraft(draft)) return { value: false, error: invalid };
  try {
    const key = conversationDraftKey(agentId, conversationId);
    if (draft.message === "" && draft.renameTitle === draft.baseTitle) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify({ schema_version: 1, agent_id: agentId,
      conversation_id: conversationId, message: draft.message, renameTitle: draft.renameTitle,
      baseTitle: draft.baseTitle, conversationCreatedAt: draft.conversationCreatedAt }));
    return { value: true, error: null };
  } catch { return { value: false, error: unavailable }; }
}

export function removeConversationDraft(agentId: number, conversationId: number): Result<boolean> {
  if (!validId(agentId) || !validId(conversationId)) return { value: false, error: invalid };
  try {
    window.localStorage.removeItem(conversationDraftKey(agentId, conversationId));
    return { value: true, error: null };
  } catch { return { value: false, error: unavailable }; }
}

export function clearAgentDrafts(agentId: number): Result<boolean> {
  if (!validId(agentId)) return { value: false, error: invalid };
  const preference = writeDraftPreference(agentId, false);
  let error = preference.error;
  try {
    const storage = window.localStorage, prefix = `${PREFIX}${agentId}:conversation:`;
    const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index))
      .filter((key): key is string => key !== null && key.startsWith(prefix) &&
        /^[1-9]\d*$/.test(key.slice(prefix.length)) && validId(Number(key.slice(prefix.length))));
    for (const key of keys) {
      try { storage.removeItem(key); } catch { error = unavailable; }
    }
  } catch { error = unavailable; }
  return { value: error === null, error };
}
