import { afterEach, expect, test, vi } from "vitest";
import {
  clearAgentDrafts, readConversationDraft, readDraftPreference, removeConversationDraft,
  writeConversationDraft, writeDraftPreference, type ConversationDraft,
} from "../src/state/conversationDraftStorage";
import { exportConversation } from "./conversationExportFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const mainKey = "agentdesk:conversation-drafts:v1:7:conversation:91";
const preferenceKey = "agentdesk:conversation-drafts:v1:7:enabled";
const draft: ConversationDraft = { message: "  中文\n<script>literal text</script>  ", renameTitle: " Rename draft ",
  baseTitle: exportConversation.title, conversationCreatedAt: exportConversation.created_at };
const stored = () => ({ schema_version: 1, agent_id: 7, conversation_id: 91, ...draft });

test("saving is off by default and reading preferences does not write browser data", () => {
  const write = vi.spyOn(Storage.prototype, "setItem"), remove = vi.spyOn(Storage.prototype, "removeItem");
  expect(readDraftPreference(7)).toEqual({ value: false, error: null });
  expect(write).not.toHaveBeenCalled(); expect(remove).not.toHaveBeenCalled();
});

test("preferences are separate for each Agent and disabling keeps stored copies", () => {
  expect(writeDraftPreference(7, true).value).toBe(true);
  expect(readDraftPreference(7).value).toBe(true); expect(readDraftPreference(8).value).toBe(false);
  writeConversationDraft(7, 91, draft);
  expect(writeDraftPreference(7, false).value).toBe(true);
  expect(readDraftPreference(7).value).toBe(false); expect(readConversationDraft(exportConversation).value).toEqual(draft);
});

test("round trips exact Unicode, whitespace and literal text in a versioned scoped record", () => {
  expect(writeConversationDraft(7, 91, draft)).toEqual({ value: true, error: null });
  expect(JSON.parse(window.localStorage.getItem(mainKey)!)).toEqual(stored());
  expect(readConversationDraft(exportConversation)).toEqual({ value: draft, error: null });
  expect(readConversationDraft({ ...exportConversation, agent_id: 8 }).value).toBeNull();
  expect(readConversationDraft({ ...exportConversation, id: 92 }).value).toBeNull();
});

test.each([
  ["future schema", { schema_version: 2 }], ["foreign Agent", { agent_id: 8 }],
  ["foreign conversation", { conversation_id: 92 }], ["reused conversation ID", { conversationCreatedAt: "2026-10-12T00:00:00" }],
  ["non-text message", { message: 42 }], ["oversized message", { message: "x".repeat(4001) }],
  ["oversized rename", { renameTitle: "x".repeat(201) }], ["oversized base title", { baseTitle: "x".repeat(201) }],
  ["missing creation time", { conversationCreatedAt: "" }], ["oversized creation time", { conversationCreatedAt: "x".repeat(101) }],
])("rejects a saved record with %s without altering its bytes", (_name, changes) => {
  const raw = JSON.stringify({ ...stored(), ...changes }); window.localStorage.setItem(mainKey, raw);
  const result = readConversationDraft(exportConversation);
  expect(result.value).toBeNull(); expect(result.error).toContain("could not be restored");
  expect(window.localStorage.getItem(mainKey)).toBe(raw);
});

test.each([["broken JSON", "{"], ["null", "null"], ["array", "[]"], ["string", '"draft"'],
  ["oversized serialized value", "x".repeat(64 * 1024 + 1)]])("ignores a malformed or oversized record: %s", (_name, raw) => {
  window.localStorage.setItem(mainKey, raw);
  expect(readConversationDraft(exportConversation).value).toBeNull();
  expect(readConversationDraft(exportConversation).error).not.toBeNull();
  expect(window.localStorage.getItem(mainKey)).toBe(raw);
});

test("extra caller fields cannot replace the record's scope or schema", () => {
  const extra = { ...draft, schema_version: 2, agent_id: 8, conversation_id: 93, unrelated: "ignore" };
  writeConversationDraft(7, 91, extra);
  expect(JSON.parse(window.localStorage.getItem(mainKey)!)).toEqual(stored());
  expect(readConversationDraft(exportConversation).value).toEqual(draft);
});

test.each([0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])("rejects invalid scoped IDs %s before touching storage", (id) => {
  const read = vi.spyOn(Storage.prototype, "getItem"), write = vi.spyOn(Storage.prototype, "setItem"), remove = vi.spyOn(Storage.prototype, "removeItem");
  expect(readDraftPreference(id).error).not.toBeNull(); expect(writeDraftPreference(id, true).value).toBe(false);
  expect(readConversationDraft({ ...exportConversation, id }).value).toBeNull();
  expect(writeConversationDraft(7, id, draft).value).toBe(false);
  expect(removeConversationDraft(id, 91).value).toBe(false); expect(clearAgentDrafts(id).value).toBe(false);
  expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled(); expect(remove).not.toHaveBeenCalled();
});

test("does not store oversized field values and accepts exact UI length bounds", () => {
  expect(writeConversationDraft(7, 91, { ...draft, message: "x".repeat(4001) }).value).toBe(false);
  expect(window.localStorage.getItem(mainKey)).toBeNull();
  const maximum = { ...draft, message: "x".repeat(4000), renameTitle: "x".repeat(200) };
  expect(writeConversationDraft(7, 91, maximum).value).toBe(true);
  expect(readConversationDraft(exportConversation).value).toEqual(maximum);
});

test("a clean draft removes only its own copy while a whitespace-only draft remains restorable", () => {
  writeConversationDraft(7, 91, draft); writeConversationDraft(7, 92, draft);
  writeConversationDraft(7, 91, { ...draft, message: "", renameTitle: draft.baseTitle });
  expect(window.localStorage.getItem(mainKey)).toBeNull();
  expect(window.localStorage.getItem("agentdesk:conversation-drafts:v1:7:conversation:92")).not.toBeNull();
  writeConversationDraft(7, 91, { ...draft, message: " \n ", renameTitle: "" });
  expect(readConversationDraft(exportConversation).value?.message).toBe(" \n ");
});

test("invalid preferences fall back to saving off without repairing their value", () => {
  window.localStorage.setItem(preferenceKey, "unknown");
  expect(readDraftPreference(7).value).toBe(false); expect(readDraftPreference(7).error).not.toBeNull();
  expect(window.localStorage.getItem(preferenceKey)).toBe("unknown");
});

test("quota failures keep the previous stored bytes and report failed updates", () => {
  writeConversationDraft(7, 91, draft); const raw = window.localStorage.getItem(mainKey);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
  expect(writeConversationDraft(7, 91, { ...draft, message: "New draft" }).value).toBe(false);
  expect(writeDraftPreference(7, true).error).toContain("remain in this page");
  expect(window.localStorage.getItem(mainKey)).toBe(raw);
});

test("blocked storage reads, writes and deletion return failures without throwing", () => {
  vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
  expect(readDraftPreference(7).value).toBe(false); expect(readConversationDraft(exportConversation).value).toBeNull();
  expect(writeConversationDraft(7, 91, draft).value).toBe(false); expect(removeConversationDraft(7, 91).value).toBe(false);
  expect(clearAgentDrafts(7).value).toBe(false);
});

test("clearing one Agent disables saving and keeps other Agents, versions and unrelated browser data", () => {
  writeDraftPreference(7, true); writeDraftPreference(8, true);
  writeConversationDraft(7, 91, draft); writeConversationDraft(7, 92, draft); writeConversationDraft(8, 93, draft);
  window.localStorage.setItem("other-app", "keep"); window.localStorage.setItem("agentdesk:conversation-drafts:v2:7:conversation:91", "keep");
  window.localStorage.setItem("agentdesk:conversation-drafts:v1:7:conversation:bad", "keep");
  expect(clearAgentDrafts(7)).toEqual({ value: true, error: null });
  expect(readDraftPreference(7).value).toBe(false); expect(readDraftPreference(8).value).toBe(true);
  expect(window.localStorage.getItem(mainKey)).toBeNull();
  expect(window.localStorage.getItem("agentdesk:conversation-drafts:v1:7:conversation:92")).toBeNull();
  expect(window.localStorage.getItem("agentdesk:conversation-drafts:v1:8:conversation:93")).not.toBeNull();
  expect(window.localStorage.getItem("other-app")).toBe("keep");
  expect(window.localStorage.getItem("agentdesk:conversation-drafts:v2:7:conversation:91")).toBe("keep");
  expect(window.localStorage.getItem("agentdesk:conversation-drafts:v1:7:conversation:bad")).toBe("keep");
});

test("a failed deletion is reported and clearing continues for other owned records", () => {
  writeConversationDraft(7, 91, draft); writeConversationDraft(7, 92, draft);
  const original = Storage.prototype.removeItem;
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(function (this: Storage, key: string) {
    if (key === mainKey) throw new DOMException("blocked", "SecurityError");
    original.call(this, key);
  });
  expect(clearAgentDrafts(7).value).toBe(false); expect(readDraftPreference(7).value).toBe(false);
  expect(window.localStorage.getItem(mainKey)).not.toBeNull();
  expect(window.localStorage.getItem("agentdesk:conversation-drafts:v1:7:conversation:92")).toBeNull();
  expect(removeConversationDraft(7, 91).value).toBe(false);
});
