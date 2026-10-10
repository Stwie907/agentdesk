import { afterEach, expect, test, vi } from "vitest";
import { getSavedMessage, searchConversationMessages, type MessageRoleFilter } from "../src/api/messageSearch";
import { exportMessages } from "./conversationExportFixtures";
import { detailResponse, messageSearchData, searchResponse } from "./messageSearchFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test("uses an encoded scoped read-only query and validates newest-first results", async () => {
  const query = "中文 %_ & 🐍";
  const row = { ...exportMessages[0], content: `Start ${query} End` };
  const fetchMock = vi.fn().mockResolvedValue(searchResponse(messageSearchData(query, "user", 5, 0, [row])));
  vi.stubGlobal("fetch", fetchMock);
  const controller = new AbortController();
  const result = await searchConversationMessages(91, 7, ` ${query} `, "user", 5, 0, controller.signal);
  expect(result.items).toHaveLength(1);
  const url = new URL(fetchMock.mock.calls[0][0], "http://localhost");
  expect(url.pathname).toBe("/conversations/91/messages/search");
  expect(Object.fromEntries(url.searchParams)).toEqual({ agent_id: "7", query, limit: "5", offset: "0", role: "user" });
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: "no-store", signal: controller.signal });
  expect(fetchMock.mock.calls[0][1].method).toBeUndefined();
});

test("counts emoji as characters and keeps microseconds and early calendar years", async () => {
  const query = "🐍".repeat(200);
  const row = { ...exportMessages[0], content: query, created_at: "0001-01-01T00:00:00.000001" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(searchResponse(messageSearchData(query, null, 10, 0, [row]))));
  expect((await searchConversationMessages(91, 7, query)).items[0].snippet).toBe(query);
});

test.each([
  [""], [" \n "], ["x".repeat(201)], ["\uD800"], ["\x00"],
  ["中文", null, 0], ["中文", null, 51], ["中文", null, 10, -1], ["中文", "wrong"],
])("rejects invalid request parameters before HTTP: %j", async (query, role = null, limit = 10, offset = 0) => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  await expect(searchConversationMessages(91, 7, query as string, role as MessageRoleFilter, limit as number, offset as number)).rejects.toMatchObject({ status: 422 });
  expect(fetchMock).not.toHaveBeenCalled();
});

const corrupt = [
  "agent", "conversation", "query", "role", "limit", "offset", "total", "has_more", "missing_items", "size", "duplicates", "order",
  "foreign_item", "unsafe_id", "role_item", "timestamp", "calendar", "snippet", "long_snippet", "match_start", "match_end", "match_text", "prefix", "suffix",
];
test.each(corrupt)("rejects corrupt search response: %s", async (change) => {
  const value = messageSearchData("中文", "user") as Record<string, any>;
  const item = value.items[0];
  if (change === "agent") value.agent_id = 8;
  if (change === "conversation") value.conversation_id = 92;
  if (change === "query") value.query = "other";
  if (change === "role") value.role = null;
  if (change === "limit") value.limit = 5;
  if (change === "offset") value.offset = 10;
  if (change === "total") value.total = -1;
  if (change === "has_more") value.has_more = false;
  if (change === "missing_items") value.items = null;
  if (change === "size") value.items.pop();
  if (change === "duplicates") value.items[1] = { ...item };
  if (change === "order") value.items.reverse();
  if (change === "foreign_item") item.conversation_id = 92;
  if (change === "unsafe_id") item.id = Number.MAX_SAFE_INTEGER + 1;
  if (change === "role_item") item.role = "assistant";
  if (change === "timestamp") item.created_at = "wrong";
  if (change === "calendar") item.created_at = "2026-02-30T06:00:00";
  if (change === "snippet") item.snippet = null;
  if (change === "long_snippet") item.snippet += "x".repeat(241);
  if (change === "match_start") item.match_start = -1;
  if (change === "match_end") item.match_end = 241;
  if (change === "match_text") item.snippet = "Wrong preview";
  if (change === "prefix") item.truncated_before = "false";
  if (change === "suffix") item.truncated_after = null;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(searchResponse(value)));
  await expect(searchConversationMessages(91, 7, "中文", "user")).rejects.toMatchObject({ status: 502 });
});

test("checks microsecond ordering rather than millisecond Date rounding", async () => {
  const rows = [{ ...exportMessages[0], id: 2, created_at: "2026-10-10T06:00:00.000001" },
    { ...exportMessages[0], id: 1, created_at: "2026-10-10T06:00:00.000002" }];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(searchResponse(messageSearchData("中文", null, 10, 0, rows))));
  expect((await searchConversationMessages(91, 7, "中文")).items.map((row) => row.id)).toEqual([1, 2]);
});

test("accepts empty pages and independently reads one exact full message", async () => {
  const message = { ...exportMessages[0], role: "archived/custom", content: '中文\r\n<script>literal</script>\n```\nTail:  \n' };
  const fetchMock = vi.fn().mockResolvedValueOnce(searchResponse(messageSearchData("missing"))).mockResolvedValueOnce(detailResponse(message));
  vi.stubGlobal("fetch", fetchMock);
  expect((await searchConversationMessages(91, 7, "missing")).items).toEqual([]);
  expect(await getSavedMessage(91, 7, 1)).toEqual(message);
  expect(fetchMock.mock.calls[1][0]).toBe("/conversations/91/messages/1?agent_id=7");
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ cache: "no-store" });
});

test.each(["id", "conversation", "content", "time"])("rejects a wrong full message: %s", async (change) => {
  const message = { ...exportMessages[0] } as Record<string, any>;
  if (change === "id") message.id = 2;
  if (change === "conversation") message.conversation_id = 92;
  if (change === "content") message.content = null;
  if (change === "time") message.created_at = "2026-13-10T00:00:00";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(detailResponse(message as any)));
  await expect(getSavedMessage(91, 7, 1)).rejects.toMatchObject({ status: 502 });
});

test("preserves server errors without retries", async () => {
  const fetchMock = vi.fn().mockResolvedValue(searchResponse({ detail: "Conversation not found" }, 404));
  vi.stubGlobal("fetch", fetchMock);
  await expect(searchConversationMessages(91, 7, "中文")).rejects.toMatchObject({ status: 404 });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
