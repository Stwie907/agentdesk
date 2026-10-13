import { afterEach, expect, test, vi } from "vitest";
import { importConversation, MAX_IMPORT_BYTES, prepareConversationImport, readConversationImport } from "../src/api/conversationImport";
import { importData, importFile, importResponse, importResult } from "./conversationImportFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test("previews complete Unicode backups locally and posts original text to the selected destination", async () => {
  const data = importData(); data.conversation.agent_id = 8000000001;
  const text = JSON.stringify(data, null, 2) + "\n";
  const fetchMock = vi.fn().mockResolvedValue(importResponse()); vi.stubGlobal("fetch", fetchMock);
  const preview = await readConversationImport(importFile(text));
  expect(fetchMock).not.toHaveBeenCalled(); expect(preview.text).toBe(text);
  expect(preview.messageCount).toBe(25); expect(preview.title).toBe(data.conversation.title);
  expect((await importConversation(7, preview)).conversation.id).toBe(92);
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/conversations/import?agent_id=7", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: text, cache: "no-store",
  });
});

test.each(["version", "boolean_version", "extra", "missing", "count", "boolean_count", "foreign", "duplicate", "order",
  "time", "zone", "precision", "boolean_id", "oversized_id", "null_content", "extra_message", "unicode", "title_type"])(
  "rejects invalid preview %s before network access", (change) => {
    const data = importData() as unknown as Record<string, any>;
    if (change === "version") data.schema_version = 2;
    if (change === "boolean_version") data.schema_version = true;
    if (change === "extra") data.execution = {};
    if (change === "missing") delete data.conversation.title;
    if (change === "count") data.message_count = 24;
    if (change === "boolean_count") data.message_count = true;
    if (change === "foreign") data.messages[0].conversation_id = 1;
    if (change === "duplicate") data.messages[1].id = data.messages[0].id;
    if (change === "order") data.messages.reverse();
    if (change === "time") data.messages[0].created_at = "2026-02-30T00:00:00";
    if (change === "zone") data.conversation.created_at += "Z";
    if (change === "precision") data.messages[0].created_at = "2026-10-10T00:00:00.1234567";
    if (change === "boolean_id") data.messages[0].id = true;
    if (change === "oversized_id") data.conversation.id = Number.MAX_SAFE_INTEGER + 1;
    if (change === "null_content") data.messages[0].content = null;
    if (change === "extra_message") data.messages[0].agent_id = 7;
    if (change === "unicode") data.messages[0].content = "\ud800";
    if (change === "title_type") data.conversation.title = 7;
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    expect(() => prepareConversationImport(JSON.stringify(data))).toThrow("complete, unmodified");
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

test("supports empty legacy null titles, original empty text, and microsecond ordering", () => {
  const empty = importData() as unknown as Record<string, any>;
  empty.conversation.title = null; empty.messages = []; empty.message_count = 0;
  expect(prepareConversationImport(JSON.stringify(empty)).title).toBe("Imported untitled conversation");
  const data = importData();
  data.messages.forEach((row, index) => { row.created_at = `2026-10-10T06:00:00.${String(index).padStart(6, "0")}`; row.content = ""; row.role = ""; });
  expect(prepareConversationImport(JSON.stringify(data)).messageCount).toBe(25);
});

test("rejects empty, oversized, invalid UTF-8, Markdown, and oversized message counts", async () => {
  await expect(readConversationImport(importFile(""))).rejects.toThrow("non-empty");
  const large = importFile(); Object.defineProperty(large, "size", { value: MAX_IMPORT_BYTES + 1 });
  await expect(readConversationImport(large)).rejects.toThrow("10 MiB");
  const broken = new File(["x"], "broken.json"); Object.defineProperty(broken, "arrayBuffer", { value: async () => new Uint8Array([255]).buffer });
  await expect(readConversationImport(broken)).rejects.toThrow("UTF-8");
  await expect(readConversationImport(importFile("# Markdown"))).rejects.toThrow("Markdown");
  const data = importData(); data.message_count = 10001;
  expect(() => prepareConversationImport(JSON.stringify(data))).toThrow("10,000 messages");
});

test.each(["scope", "version", "count", "title", "time", "id", "status", "json"])("rejects untrustworthy %s responses without retry", async (change) => {
  const data = importResult();
  if (change === "scope") data.conversation.agent_id = 8;
  if (change === "version") data.schema_version = 2;
  if (change === "count") data.message_count = 20;
  if (change === "title") data.conversation.title = "Another title";
  if (change === "time") data.conversation.created_at = "2026-10-09T06:00:00";
  if (change === "id") data.conversation.id = 0;
  const response = change === "json" ? new Response("{broken", { status: 201 }) : importResponse(data, change === "status" ? 200 : 201);
  const fetchMock = vi.fn().mockResolvedValue(response); vi.stubGlobal("fetch", fetchMock);
  await expect(importConversation(7, prepareConversationImport(JSON.stringify(importData())))).rejects.toThrow("Reload conversations");
  expect(fetchMock).toHaveBeenCalledOnce();
});

test.each([404, 413, 415, 422, 500])("surfaces HTTP %s and keeps ambiguous writes explicit", async (status) => {
  const fetchMock = vi.fn().mockResolvedValue(importResponse({ detail: "Useful import error" }, status)); vi.stubGlobal("fetch", fetchMock);
  await expect(importConversation(7, prepareConversationImport(JSON.stringify(importData())))).rejects.toMatchObject({ status });
  expect(fetchMock).toHaveBeenCalledOnce();
});

test("network failures and proxy HTML errors report uncertainty without automatic retry", async () => {
  const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(new Response("<h1>Too large</h1>", { status: 413 }));
  vi.stubGlobal("fetch", fetchMock);
  const prepared = prepareConversationImport(JSON.stringify(importData()));
  await expect(importConversation(7, prepared)).rejects.toThrow("may have been saved");
  expect(fetchMock).toHaveBeenCalledOnce();
  await expect(importConversation(7, prepared)).rejects.toMatchObject({ status: 413 });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
