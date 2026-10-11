import { afterEach, expect, test, vi } from "vitest";
import type { ConversationExportFormat } from "../src/api/conversationExport";
import { getMessageContextExport } from "../src/api/messageContextExport";
import { contextData } from "./messageContextFixtures";
import { contextExportData, contextExportResponse, literalContextFixture } from "./messageContextExportFixtures";
import { deferredResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test.each(["json", "markdown"] as const)("requests the displayed %s context with scope, counts, and cancellation", async (format) => {
  const fetchMock = vi.fn().mockResolvedValue(contextExportResponse(format)); vi.stubGlobal("fetch", fetchMock);
  const controller = new AbortController();
  const result = await getMessageContextExport(contextData(), format, controller.signal);
  expect(fetchMock).toHaveBeenCalledWith(`/conversations/91/messages/13/context/export?agent_id=7&before=3&after=3&format=${format}`,
    expect.objectContaining({ cache: "no-store", signal: controller.signal }));
  expect(result.filename).toBe(`conversation-91-message-13-context.${format === "json" ? "json" : "md"}`);
  expect(result.messageCount).toBe(7); expect(result.blob.size).toBeGreaterThan(0);
});

test.each([[1, 3, 3], [25, 3, 3], [13, 0, 0], [13, 10, 10], [13, 1, 5]])(
  "downloads exact bounded windows %s/%s/%s in both formats", async (anchor, before, after) => {
    const context = contextData(anchor, before, after);
    for (const format of ["json", "markdown"] as const) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextExportResponse(format, context)));
      expect((await getMessageContextExport(context, format)).messageCount).toBe(context.items.length);
    }
  },
);

test.each(["json", "markdown"] as const)("retains custom roles, empty content, microseconds, fences, and literal text in %s", async (format) => {
  const context = literalContextFixture();
  const response = contextExportResponse(format, context);
  const bytes = await response.clone().arrayBuffer();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  const file = await getMessageContextExport(context, format);
  expect(file.blob.size).toBe(bytes.byteLength); expect(file.messageCount).toBe(3);
});

test.each([
  ["X-Conversation-ID", "92"], ["X-Agent-ID", "8"], ["X-Anchor-Message-ID", "14"],
  ["X-Context-Export-Kind", "agentdesk.conversation"], ["X-Context-Export-Schema-Version", "2"],
  ["Content-Disposition", 'attachment; filename="../../other.json"'], ["Content-Type", "text/html"],
  ["Cache-Control", "max-age=60"], ["X-Content-Type-Options", ""],
  ["X-Message-Count", "0"], ["X-Message-Count", "8"], ["X-Message-Count", "07"], ["X-Message-Count", "bad"],
])("rejects invalid header %s=%s before reading attachment bytes", async (name, value) => {
  const response = contextExportResponse("json", contextData(), undefined, { [name]: value });
  const read = vi.spyOn(response, "arrayBuffer"); vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  await expect(getMessageContextExport(contextData(), "json")).rejects.toMatchObject({ status: 502 });
  expect(read).not.toHaveBeenCalled();
});

test.each(["kind", "version", "booleanVersion", "count", "missingContext", "foreign", "counts", "anchor", "duplicate", "order", "date"])(
  "rejects incomplete or foreign JSON: %s", async (change) => {
    const value = contextExportData();
    if (change === "kind") value.export_kind = "agentdesk.conversation";
    if (change === "version") value.schema_version = 2;
    if (change === "booleanVersion") Object.assign(value, { schema_version: true });
    if (change === "count") value.message_count = 6;
    if (change === "missingContext") Object.assign(value, { context: null });
    if (change === "foreign") value.context.items[0].conversation_id = 92;
    if (change === "counts") value.context.before = 4;
    if (change === "anchor") value.context.anchor_message_id = 14;
    if (change === "duplicate") value.context.items[1] = { ...value.context.items[0] };
    if (change === "order") value.context.items.reverse();
    if (change === "date") value.context.items[0].created_at = "2026-02-30T00:00:00";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextExportResponse("json", contextData(), value)));
    await expect(getMessageContextExport(contextData(), "json")).rejects.toMatchObject({ status: 502 });
  },
);

test.each(["content", "role", "timestamp", "boundary"])("requires a reload when valid saved context changed: %s", async (change) => {
  const value = contextExportData();
  if (change === "content") value.context.items[0].content += "Changed";
  if (change === "role") value.context.items[0].role = "system";
  if (change === "timestamp") value.context.items[0].created_at = "2026-10-10T05:59:59.999999";
  if (change === "boundary") value.context.has_more_before = false;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextExportResponse("json", contextData(), value)));
  await expect(getMessageContextExport(contextData(), "json")).rejects.toMatchObject({ status: 409 });
});

test("rejects changed or incomplete Markdown before offering a download", async () => {
  const response = contextExportResponse("markdown");
  const text = await response.text();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextExportResponse("markdown", contextData(), text.replace("Saved turn 10", "Changed turn 10"))));
  await expect(getMessageContextExport(contextData(), "markdown")).rejects.toMatchObject({ status: 409 });
});

test.each(["empty", "oversize", "utf8", "json"])("rejects invalid attachment bytes: %s", async (change) => {
  const response = contextExportResponse();
  const bytes = change === "empty" ? new Uint8Array() : change === "oversize" ? new Uint8Array(10 * 1024 * 1024 + 1) :
    change === "utf8" ? new Uint8Array([0xc3, 0x28]) : new TextEncoder().encode("not JSON");
  vi.spyOn(response, "arrayBuffer").mockResolvedValue(bytes.buffer);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  await expect(getMessageContextExport(contextData(), "json")).rejects.toMatchObject({ status: 502 });
});

test.each(["identity", "count", "invalidContext", "format", "null"])("rejects an invalid displayed request before HTTP: %s", async (change) => {
  const context = contextData(); let format: ConversationExportFormat = "json";
  if (change === "identity") context.agent_id = 0;
  if (change === "count") context.before = 11;
  if (change === "invalidContext") context.items = [];
  if (change === "format") format = "html" as ConversationExportFormat;
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  await expect(getMessageContextExport(change === "null" ? null as unknown as typeof context : context, format)).rejects.toBeDefined();
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([404, 413, 500])("retains server error status %s for explicit retry", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Stable export failure" }),
    { status, headers: { "Content-Type": "application/json" } })));
  await expect(getMessageContextExport(contextData(), "json")).rejects.toMatchObject({ status, message: "Stable export failure" });
});

test("retains a stable HTTP failure when an error body is not JSON", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("proxy unavailable", { status: 503 })));
  await expect(getMessageContextExport(contextData(), "json")).rejects.toMatchObject({ status: 503 });
});

test("captures the displayed text before a delayed request completes", async () => {
  const context = contextData(); const response = contextExportResponse("json", context);
  const pending = deferredResponse(); vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending.promise));
  const result = getMessageContextExport(context, "json");
  context.items[0].content = "Later local mutation";
  pending.resolve(response);
  expect((await result).messageCount).toBe(7);
});
