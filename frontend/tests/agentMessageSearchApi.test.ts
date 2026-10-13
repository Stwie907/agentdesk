import { afterEach, expect, test, vi } from "vitest";
import { searchAgentMessages } from "../src/api/agentMessageSearch";
import { exportMessages } from "./conversationExportFixtures";
import { agentSearchData, agentSearchResponse, siblingMessage } from "./agentMessageSearchFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test("requests an uncached Agent-scoped page and preserves conversation identity and titles", async () => {
  const fetchMock = vi.fn().mockResolvedValue(agentSearchResponse()); vi.stubGlobal("fetch", fetchMock);
  const controller = new AbortController();
  const page = await searchAgentMessages(7, "  中文  ", null, 10, 0, controller.signal);
  expect(page.total).toBe(26); expect(page.items[0].conversation_id).toBe(92);
  expect(page.items[1].conversation_id).toBe(91);
  expect(fetchMock.mock.calls[0][0]).toBe("/agents/7/messages/search?query=%E4%B8%AD%E6%96%87&limit=10&offset=0");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: "no-store", signal: controller.signal });
});

test("encodes literal punctuation and applies the role and page without adding a conversation scope", async () => {
  const row = { ...siblingMessage, content: "100%_ready O'Reilly \\ 🐍" };
  const fetchMock = vi.fn().mockResolvedValue(agentSearchResponse(agentSearchData("%_", "assistant", 5, 0, [row])));
  vi.stubGlobal("fetch", fetchMock);
  expect((await searchAgentMessages(7, "%_", "assistant", 5)).items).toHaveLength(1);
  const url = new URL(fetchMock.mock.calls[0][0], "http://localhost");
  expect(url.searchParams.get("query")).toBe("%_"); expect(url.searchParams.get("role")).toBe("assistant");
  expect(url.searchParams.has("conversation_id")).toBe(false);
});

const invalid: unknown[][] = [[0, "中文"], [-1, "中文"], [Number.MAX_SAFE_INTEGER + 1, "中文"], [1.5, "中文"],
  [7, ""], [7, "   "], [7, "x".repeat(201)], [7, "a\0b"], [7, "\ud800"],
  [7, "中文", "custom"], [7, "中文", "USER"], [7, "中文", null, 0], [7, "中文", null, 51],
  [7, "中文", null, 1.5], [7, "中文", null, 10, -1], [7, "中文", null, 10, 1.5],
  [7, "中文", null, 10, Number.MAX_SAFE_INTEGER + 1]];
test.each(invalid)("rejects invalid Agent requests before HTTP: %j", async (...args) => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  await expect(searchAgentMessages(...args as Parameters<typeof searchAgentMessages>)).rejects.toMatchObject({ status: 422 });
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each(["agent", "query", "role", "limit", "offset", "total", "unsafe_total", "has_more", "missing_items", "size",
  "item_agent", "conversation", "title", "unsafe_id", "duplicates", "order", "item_role", "timestamp", "calendar",
  "snippet", "long_snippet", "start", "end", "match", "prefix", "suffix"])("rejects corrupt global responses: %s", async (change) => {
  const value = agentSearchData("中文", "user") as Record<string, any>; const row = value.items[0];
  if (change === "agent") value.agent_id = 8;
  if (change === "query") value.query = "other";
  if (change === "role") value.role = null;
  if (change === "limit") value.limit = 5;
  if (change === "offset") value.offset = 10;
  if (change === "total") value.total = -1;
  if (change === "unsafe_total") value.total = Number.MAX_SAFE_INTEGER + 1;
  if (change === "has_more") value.has_more = false;
  if (change === "missing_items") value.items = null;
  if (change === "size") value.items.pop();
  if (change === "item_agent") row.agent_id = 8;
  if (change === "conversation") row.conversation_id = 0;
  if (change === "title") row.conversation_title = null;
  if (change === "unsafe_id") row.id = Number.MAX_SAFE_INTEGER + 1;
  if (change === "duplicates") value.items[1] = { ...row };
  if (change === "order") value.items.reverse();
  if (change === "item_role") row.role = "assistant";
  if (change === "timestamp") row.created_at = "wrong";
  if (change === "calendar") row.created_at = "2026-02-30T06:00:00";
  if (change === "snippet") row.snippet = null;
  if (change === "long_snippet") row.snippet += "x".repeat(241);
  if (change === "start") row.match_start = -1;
  if (change === "end") row.match_end = 241;
  if (change === "match") row.snippet = "Wrong preview";
  if (change === "prefix") row.truncated_before = "false";
  if (change === "suffix") row.truncated_after = null;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(agentSearchResponse(value)));
  await expect(searchAgentMessages(7, "中文", "user")).rejects.toMatchObject({ status: 502 });
});

test("validates microsecond order across different conversations without millisecond rounding", async () => {
  const data = agentSearchData("中文", null, 10, 0, [exportMessages[0], siblingMessage]);
  data.items[0].id = 1; data.items[0].created_at = "2026-10-10T06:00:00.000002";
  data.items[1].id = 26; data.items[1].created_at = "2026-10-10T06:00:00.000001";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(agentSearchResponse(data)));
  expect((await searchAgentMessages(7, "中文")).items.map((row) => row.id)).toEqual([1, 26]);
});

test.each([404, 422, 500])("preserves explicit HTTP error %s", async (status) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(agentSearchResponse({ detail: "Agent search failed" }, status)));
  await expect(searchAgentMessages(7, "中文")).rejects.toMatchObject({ status, message: "Agent search failed" });
});

test("accepts empty and beyond-final pages", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(agentSearchResponse(agentSearchData("missing")))
    .mockResolvedValueOnce(agentSearchResponse(agentSearchData("中文", null, 10, 26)));
  vi.stubGlobal("fetch", fetchMock);
  expect((await searchAgentMessages(7, "missing")).items).toEqual([]);
  expect((await searchAgentMessages(7, "中文", null, 10, 26)).has_more).toBe(false);
});
