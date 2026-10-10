import { afterEach, expect, test, vi } from "vitest";
import { getConversationMessagePage } from "../src/api/conversations";
import { jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

const row = { id: 13, conversation_id: 91, role: "user", content: "中文 history", created_at: "2026-10-10T06:00:00" };
const page = { conversation_id: 91, agent_id: 7, limit: 20, before_id: null, has_more: false, next_before_id: null, items: [row] };

test.each([
  { conversation_id: 92 }, { agent_id: 8 }, { limit: 100 }, { before_id: 14 },
  { has_more: "true" }, { has_more: true }, { next_before_id: 13 }, { items: "wrong" },
  { items: [row, row] }, { items: [{ ...row, conversation_id: 92 }] },
  { items: [{ ...row, id: 0 }] }, { items: [{ ...row, id: 1.5 }] },
  { items: [{ ...row, content: null }] }, { items: [{ ...row, created_at: "invalid" }] },
  { items: [{ ...row, id: 14 }, row] },
  { items: Array.from({ length: 21 }, (_, index) => ({ ...row, id: index + 1 })) },
])("rejects malformed, unordered, duplicate, or foreign history pages %j", async (change) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...page, ...change })));
  await expect(getConversationMessagePage(91, 7)).rejects.toThrow(/invalid/);
});

test("requests latest then older pages with a scoped cursor and no offset", async () => {
  const older = { ...page, before_id: 99 };
  const mock = vi.fn().mockResolvedValueOnce(jsonResponse(page)).mockResolvedValueOnce(jsonResponse(older));
  vi.stubGlobal("fetch", mock);
  expect(await getConversationMessagePage(91, 7)).toEqual(page);
  expect(await getConversationMessagePage(91, 7, 20, 99)).toEqual(older);
  expect(mock).toHaveBeenNthCalledWith(1, "/conversations/91/messages/page?agent_id=7&limit=20", { cache: "no-store" });
  expect(mock).toHaveBeenNthCalledWith(2, "/conversations/91/messages/page?agent_id=7&limit=20&before_id=99", { cache: "no-store" });
});

test("preserves microsecond chronology when IDs and millisecond timestamps would sort differently", async () => {
  const items = [{ ...row, id: 100, created_at: row.created_at + ".000001" },
    { ...row, id: 1, created_at: row.created_at + ".000002" }];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...page, items })));
  expect((await getConversationMessagePage(91, 7)).items).toEqual(items);
});

test.each([99, 13, null])("rejects a wrong next cursor %j", async (cursor) => {
  const items = Array.from({ length: 20 }, (_, index) => ({ ...row, id: index + 1 }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...page, items, has_more: true, next_before_id: cursor })));
  await expect(getConversationMessagePage(91, 7)).rejects.toThrow(/cursor/);
});

test("rejects a page that includes its exclusive before cursor", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...page, before_id: 13 })));
  await expect(getConversationMessagePage(91, 7, 20, 13)).rejects.toThrow(/cursor/);
});
