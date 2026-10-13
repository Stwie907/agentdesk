import { afterEach, expect, test, vi } from "vitest";
import { ApiError } from "../src/api/executions";
import { getMessageContext } from "../src/api/messageContext";
import { contextData, contextResponse } from "./messageContextFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test("requests scoped uncached context and forwards its cancellation signal", async () => {
  const fetchMock = vi.fn().mockResolvedValue(contextResponse()); vi.stubGlobal("fetch", fetchMock);
  const controller = new AbortController();
  expect(await getMessageContext(91, 7, 13, 3, 3, controller.signal)).toEqual(contextData());
  expect(fetchMock).toHaveBeenCalledWith("/conversations/91/messages/13/context?agent_id=7&before=3&after=3",
    expect.objectContaining({ cache: "no-store", signal: controller.signal }));
});

test.each([[1, 3, 3], [25, 3, 3], [13, 0, 0], [13, 10, 10], [13, 1, 5]])("accepts boundaries and independent counts %s/%s/%s", async (id, before, after) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse(contextData(id, before, after))));
  const result = await getMessageContext(91, 7, id, before, after);
  expect(result.items[result.anchor_index].id).toBe(id);
  expect(result.items.length).toBeLessThanOrEqual(before + 1 + after);
});

test.each([
  [0, 7, 13, 3, 3], [91, 0, 13, 3, 3], [91, 7, 0, 3, 3], [Number.MAX_SAFE_INTEGER + 1, 7, 13, 3, 3],
  [91, Number.NaN, 13, 3, 3], [91, 7, Number.POSITIVE_INFINITY, 3, 3],
  [91, 7, 13, -1, 3], [91, 7, 13, 11, 3], [91, 7, 13, 1.5, 3],
  [91, 7, 13, 3, -1], [91, 7, 13, 3, 11], [91, 7, 13, 3, Number.NaN],
])("rejects invalid identities or window counts before requesting", async (conversation, agent, message, before, after) => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  await expect(getMessageContext(conversation, agent, message, before, after)).rejects.toMatchObject({ status: 422 });
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each(["conversation", "agent", "anchor", "before", "after", "index", "beforeFlag", "afterFlag", "empty", "oversize", "duplicate", "order", "foreign", "content", "timestamp", "missingAnchor", "wrongIndex", "shortBefore", "shortAfter"])(
  "rejects malformed or foreign context: %s", async (change) => {
    const data = contextData();
    if (change === "conversation") data.conversation_id = 92;
    if (change === "agent") data.agent_id = 8;
    if (change === "anchor") data.anchor_message_id = 14;
    if (change === "before") data.before = 4;
    if (change === "after") data.after = 4;
    if (change === "index") data.anchor_index = -1;
    if (change === "beforeFlag") Object.assign(data, { has_more_before: "true" });
    if (change === "afterFlag") Object.assign(data, { has_more_after: undefined });
    if (change === "empty") data.items = [];
    if (change === "oversize") data.items.push({ ...data.items.at(-1)!, id: 17 });
    if (change === "duplicate") data.items[1] = { ...data.items[0] };
    if (change === "order") data.items.reverse();
    if (change === "foreign") data.items[0].conversation_id = 92;
    if (change === "content") Object.assign(data.items[0], { content: null });
    if (change === "timestamp") data.items[0].created_at = "2026-02-30T00:00:00";
    if (change === "missingAnchor") data.items[3].id = 999;
    if (change === "wrongIndex") data.anchor_index = 2;
    if (change === "shortBefore") { data.items.shift(); data.anchor_index -= 1; }
    if (change === "shortAfter") data.items.pop();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse(data)));
    await expect(getMessageContext(91, 7, 13)).rejects.toMatchObject({ status: 502 });
  },
);

test("preserves custom roles, empty content, literal code, and microsecond chronological order", async () => {
  const data = contextData(13, 1, 1);
  data.items[0] = { ...data.items[0], id: 900, role: "", content: "", created_at: "0001-01-01T00:00:00.000001" };
  data.items[1] = { ...data.items[1], role: "archived/custom", content: '🐍<script>alert("literal")</script>\r\n  ', created_at: "0001-01-01T00:00:00.000002" };
  data.items[2] = { ...data.items[2], id: 1, created_at: "9999-12-31T23:59:59.999999" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse(data)));
  expect((await getMessageContext(91, 7, 13, 1, 1)).items).toEqual(data.items);
});

test("keeps scoped 404 errors available for an explicit refresh", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse({ detail: "Message not found in this conversation" }, 404)));
  await expect(getMessageContext(91, 7, 13)).rejects.toBeInstanceOf(ApiError);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse({ detail: "Message not found in this conversation" }, 404)));
  await expect(getMessageContext(91, 7, 13)).rejects.toMatchObject({ status: 404 });
});
