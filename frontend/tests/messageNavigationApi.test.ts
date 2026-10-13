import { afterEach, expect, test, vi } from "vitest";
import { getMessageNavigationTarget } from "../src/api/messageNavigation";
import { navigationItem, siblingConversation } from "./messageNavigationFixtures";
import { siblingMessage } from "./agentMessageSearchFixtures";
import { detailResponse } from "./messageSearchFixtures";
import { jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

test("reads the result's actual scoped conversation and full message, with one cancellation signal and no writes", async () => {
  const controller = new AbortController();
  const fresh = { ...siblingConversation, title: "Fresh saved title" };
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(fresh)).mockResolvedValueOnce(detailResponse(siblingMessage));
  vi.stubGlobal("fetch", fetchMock);
  const target = await getMessageNavigationTarget(7, navigationItem, controller.signal);
  expect(fetchMock.mock.calls).toEqual([
    ["/conversations/92?agent_id=7", { cache: "no-store", signal: controller.signal }],
    ["/conversations/92/messages/26?agent_id=7", { cache: "no-store", signal: controller.signal }],
  ]);
  expect(target.conversation).toEqual(fresh);
  expect(target.message).toEqual({ ...navigationItem, conversation_title: fresh.title });
});

test.each([{ agent_id: 8 }, { conversation_id: 0 }, { id: -1 }, { id: Number.MAX_SAFE_INTEGER + 1 }])(
  "rejects invalid or foreign navigation scope before HTTP: %s", async (change) => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    await expect(getMessageNavigationTarget(7, { ...navigationItem, ...change })).rejects.toMatchObject({ status: 422 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

test.each([{ id: 91 }, { agent_id: 8 }])("rejects a foreign conversation before reading messages: %s", async (change) => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...siblingConversation, ...change }));
  vi.stubGlobal("fetch", fetchMock);
  await expect(getMessageNavigationTarget(7, navigationItem)).rejects.toMatchObject({ status: 502 });
  expect(fetchMock).toHaveBeenCalledOnce();
});

test.each([{ id: 1 }, { conversation_id: 91 }, { role: "user" }, { created_at: "2026-10-10T06:00:01" },
  { content: "Changed saved body" }])("rejects changed saved message evidence: %s", async (change) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(siblingConversation))
    .mockResolvedValueOnce(detailResponse({ ...siblingMessage, ...change })));
  await expect(getMessageNavigationTarget(7, navigationItem)).rejects.toMatchObject({ status: 502 });
});

test.each(["before", "conversation", "message"])("honours cancellation %s a response, even when transport ignores abort", async (when) => {
  const controller = new AbortController();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const metadata = String(input).startsWith("/conversations/92?");
    if (when === (metadata ? "conversation" : "message")) controller.abort();
    return metadata ? jsonResponse(siblingConversation) : detailResponse(siblingMessage);
  });
  vi.stubGlobal("fetch", fetchMock);
  if (when === "before") controller.abort();
  await expect(getMessageNavigationTarget(7, navigationItem, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  expect(fetchMock).toHaveBeenCalledTimes(when === "before" ? 0 : when === "conversation" ? 1 : 2);
});

test("propagates a deleted conversation's 404", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Conversation not found" }, 404)));
  await expect(getMessageNavigationTarget(7, navigationItem)).rejects.toMatchObject({ status: 404 });
});
