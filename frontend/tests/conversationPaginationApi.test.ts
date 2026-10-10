import { afterEach, expect, test, vi } from "vitest";
import { getConversationPage } from "../src/api/conversations";
import { jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

const row = { id: 13, agent_id: 7, title: "中文 chat", created_at: "2026-10-10T06:00:00" };
const page = { agent_id: 7, query: "", limit: 10, offset: 0, total: 1, has_more: false, items: [row] };

test.each([
  { agent_id: 8 }, { query: "different" }, { limit: 20 }, { offset: 10 },
  { total: -1 }, { total: 1.5 }, { total: 11 }, { has_more: true }, { items: [] },
  { items: [row, row], total: 2 }, { items: [{ ...row, agent_id: 8 }] }, { items: "wrong" },
])("rejects malformed or incorrectly scoped pages %j", async (change) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...page, ...change })));
  await expect(getConversationPage(7)).rejects.toThrow(/invalid|duplicate/);
});

test("encodes punctuation and Chinese text as a single literal query parameter", async () => {
  const query = "中文 & 100%_ # /";
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...page, query }));
  vi.stubGlobal("fetch", fetchMock);
  expect(await getConversationPage(7, `  ${query}  `)).toEqual({ ...page, query });
  const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
  expect(url.searchParams.get("query")).toBe(query);
  expect([...url.searchParams.keys()]).toEqual(["agent_id", "limit", "offset", "query"]);
});
