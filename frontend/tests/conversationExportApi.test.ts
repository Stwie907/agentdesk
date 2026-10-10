import { afterEach, expect, test, vi } from "vitest";
import { downloadConversationAttachment, getConversationExport } from "../src/api/conversationExport";
import { exportData, exportResponse } from "./conversationExportFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

test.each(["json", "markdown"] as const)("fetches a scoped complete %s attachment", async (format) => {
  const fetchMock = vi.fn().mockResolvedValue(exportResponse(format)); vi.stubGlobal("fetch", fetchMock);
  const file = await getConversationExport(91, 7, format);
  expect(fetchMock).toHaveBeenCalledWith(`/conversations/91/export?agent_id=7&format=${format}`, { cache: "no-store", signal: undefined });
  expect(file.filename).toBe(`conversation-91.${format === "json" ? "json" : "md"}`);
  expect(file.messageCount).toBe(25); expect(file.blob.size).toBeGreaterThan(0);
});

test.each([
  ["X-Conversation-ID", "92"], ["X-Agent-ID", "8"], ["X-Export-Schema-Version", "2"],
  ["X-Message-Count", ""], ["X-Message-Count", "10001"], ["X-Message-Count", "25.0"],
  ["Content-Disposition", 'attachment; filename="../../other.json"'], ["Content-Type", "text/html"],
])("rejects invalid header %s=%s", async (header, value) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(exportResponse("json", undefined, { [header]: value })));
  await expect(getConversationExport(91, 7, "json")).rejects.toThrow("invalid export metadata");
});

test.each(["scope", "conversation", "version", "count", "foreign_message", "duplicate", "order", "timestamp", "content"])(
  "rejects corrupted or foreign JSON: %s", async (change) => {
    const data = exportData();
    if (change === "scope") data.conversation.agent_id = 8;
    if (change === "conversation") data.conversation.id = 92;
    if (change === "version") data.schema_version = 2;
    if (change === "count") data.messages.pop();
    if (change === "foreign_message") data.messages[0].conversation_id = 92;
    if (change === "duplicate") data.messages[1].id = data.messages[0].id;
    if (change === "order") data.messages.reverse();
    if (change === "timestamp") data.messages[0].created_at = "invalid";
    if (change === "content") (data.messages[0] as unknown as { content: null }).content = null;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(exportResponse("json", data)));
    await expect(getConversationExport(91, 7, "json")).rejects.toThrow();
  },
);

test("rejects invalid JSON, empty or oversized files, and invalid UTF-8", async () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValueOnce(exportResponse("json", "{broken"));
  await expect(getConversationExport(91, 7, "json")).rejects.toThrow("invalid conversation export JSON");
  fetchMock.mockResolvedValueOnce(exportResponse("markdown", ""));
  await expect(getConversationExport(91, 7, "markdown")).rejects.toThrow("empty or oversized");
  const oversized = exportResponse();
  vi.spyOn(oversized, "arrayBuffer").mockResolvedValue(new ArrayBuffer(10 * 1024 * 1024 + 1));
  fetchMock.mockResolvedValueOnce(oversized);
  await expect(getConversationExport(91, 7, "json")).rejects.toThrow("empty or oversized");
  const broken = exportResponse(); vi.spyOn(broken, "arrayBuffer").mockResolvedValue(new Uint8Array([255]).buffer);
  fetchMock.mockResolvedValueOnce(broken);
  await expect(getConversationExport(91, 7, "json")).rejects.toThrow("invalid UTF-8");
});

test.each([404, 413, 500])("surfaces HTTP %s without a file", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Useful export error" }), { status })));
  await expect(getConversationExport(91, 7, "json")).rejects.toMatchObject({ status, message: "Useful export error" });
});

test("starts a named browser download and releases the object URL", () => {
  vi.useFakeTimers();
  const create = vi.fn().mockReturnValue("blob:export"); const revoke = vi.fn();
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
  const clicked: { href: string; filename: string; connected: boolean }[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function(this: HTMLAnchorElement) {
    clicked.push({ href: this.href, filename: this.download, connected: this.isConnected });
  });
  const blob = new Blob(["中文"]);
  downloadConversationAttachment({ blob, filename: "conversation-91.md", messageCount: 0 });
  expect(create).toHaveBeenCalledWith(blob);
  expect(clicked).toEqual([{ href: "blob:export", filename: "conversation-91.md", connected: true }]);
  expect(document.querySelector("a[download]")).toBeNull(); expect(revoke).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1000); expect(revoke).toHaveBeenCalledWith("blob:export");
});
