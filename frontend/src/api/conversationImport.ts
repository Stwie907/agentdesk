import { ApiError } from "./executions";
import type { Conversation } from "../types/conversations";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;
const UNTITLED_IMPORT = "Imported untitled conversation";
const INVALID_BACKUP = "Use a complete, unmodified AgentDesk JSON backup. Markdown files cannot be imported.";
const UNKNOWN_RESULT = "The import may have been saved. Reload conversations and check the imported title before trying again.";
export type PreparedConversationImport = { text: string; title: string; messageCount: number; createdAt: string };
export type ConversationImportResult = { schema_version: number; conversation: Conversation; message_count: number };

function objectWithKeys(value: unknown, keys: string[]): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) &&
    Object.keys(value).sort().join(",") === [...keys].sort().join(",");
}

function positiveId(value: unknown): value is number { return Number.isSafeInteger(value) && (value as number) > 0; }

function validText(value: unknown): value is string {
  if (typeof value !== "string") return false;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(++index);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
    } else if (code >= 0xdc00 && code <= 0xdfff) return false;
  }
  return true;
}

function timestamp(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const parts = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?$/.exec(value);
  const milliseconds = parts ? Date.parse(parts[1] + "Z") : NaN;
  if (!parts || !Number.isFinite(milliseconds) || parts[1].startsWith("0000-") ||
      new Date(milliseconds).toISOString().slice(0, 19) !== parts[1]) return null;
  return parts[1] + "." + (parts[2] ?? "").padEnd(6, "0");
}

export function prepareConversationImport(text: string): PreparedConversationImport {
  if (new TextEncoder().encode(text).byteLength > MAX_IMPORT_BYTES) throw new ApiError(413, "The JSON backup exceeds 10 MiB.");
  let data: unknown;
  try { data = JSON.parse(text); }
  catch { throw new ApiError(422, INVALID_BACKUP); }
  if (!objectWithKeys(data, ["schema_version", "conversation", "message_count", "messages"]) || data.schema_version !== 1 ||
      !Number.isSafeInteger(data.message_count) || (data.message_count as number) < 0 || !Array.isArray(data.messages) ||
      !objectWithKeys(data.conversation, ["id", "agent_id", "title", "created_at"])) throw new ApiError(422, INVALID_BACKUP);
  if (data.messages.length > 10000 || (data.message_count as number) > 10000) throw new ApiError(413, "The JSON backup exceeds 10,000 messages.");
  const source = data.conversation;
  if (!positiveId(source.id) || !positiveId(source.agent_id) || !(source.title === null || validText(source.title)) ||
      timestamp(source.created_at) === null || data.messages.length !== data.message_count) throw new ApiError(422, INVALID_BACKUP);
  const seen = new Set<number>();
  let previousTime: string | null = null;
  let previousId = 0;
  for (const row of data.messages) {
    if (!objectWithKeys(row, ["id", "conversation_id", "role", "content", "created_at"]) || !positiveId(row.id) ||
        seen.has(row.id) || row.conversation_id !== source.id || !validText(row.role) || !validText(row.content)) throw new ApiError(422, INVALID_BACKUP);
    const time = timestamp(row.created_at);
    if (time === null || (previousTime !== null && (time < previousTime || (time === previousTime && row.id <= previousId)))) {
      throw new ApiError(422, INVALID_BACKUP);
    }
    seen.add(row.id); previousTime = time; previousId = row.id;
  }
  return { text, title: source.title === null ? UNTITLED_IMPORT : source.title as string,
    messageCount: data.message_count as number, createdAt: source.created_at as string };
}

export async function readConversationImport(file: File): Promise<PreparedConversationImport> {
  if (file.size === 0) throw new ApiError(422, "Choose a non-empty AgentDesk JSON backup.");
  if (file.size > MAX_IMPORT_BYTES) throw new ApiError(413, "The JSON backup exceeds 10 MiB.");
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_IMPORT_BYTES) throw new ApiError(413, "The JSON backup is empty or exceeds 10 MiB.");
  let text: string;
  try { text = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
  catch { throw new ApiError(422, "The JSON backup must contain valid UTF-8 text."); }
  return prepareConversationImport(text);
}

export async function importConversation(agentId: number, prepared: PreparedConversationImport): Promise<ConversationImportResult> {
  const expected = prepareConversationImport(prepared.text);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/conversations/import?agent_id=${agentId}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: expected.text, cache: "no-store",
    });
  } catch { throw new ApiError(0, UNKNOWN_RESULT); }
  if (!response.ok) {
    let message = `Unable to import conversation (status ${response.status}).`;
    try { const body = await response.json() as { detail?: unknown }; if (typeof body?.detail === "string") message = body.detail; }
    catch { /* Retain the status when a proxy returns an HTML error. */ }
    throw new ApiError(response.status, response.status >= 500 ? `${message} ${UNKNOWN_RESULT}` : message);
  }
  let data: ConversationImportResult;
  try { data = await response.json() as ConversationImportResult; }
  catch { throw new ApiError(502, UNKNOWN_RESULT); }
  const conversation = data?.conversation;
  if (response.status !== 201 || data?.schema_version !== 1 || data?.message_count !== expected.messageCount ||
      !conversation || !positiveId(conversation.id) || conversation.agent_id !== agentId || conversation.title !== expected.title ||
      timestamp(conversation.created_at) === null || timestamp(conversation.created_at) !== timestamp(expected.createdAt)) {
    throw new ApiError(502, UNKNOWN_RESULT);
  }
  return data;
}
