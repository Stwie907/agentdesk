import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import type { ConversationMessage } from "../src/types/conversations";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

const conversation = { id: 91, agent_id: 7, title: "Long chat", created_at: "2026-10-10T06:00:00" };
const other = { ...conversation, id: 92, title: "Other chat" };
const messages: ConversationMessage[] = Array.from({ length: 45 }, (_, index) => ({
  id: index + 1, conversation_id: 91, role: index % 2 === 0 ? "user" : "assistant",
  content: `Saved turn ${index + 1}`, created_at: conversation.created_at,
}));

function historyPage(beforeId: number | null = null, rows = messages) {
  const cutoff = beforeId === null ? rows.length : rows.findIndex((row) => row.id === beforeId);
  const eligible = rows.slice(0, cutoff);
  const items = eligible.slice(-20);
  return conversationMessagePageResponse(items, { before_id: beforeId, has_more: eligible.length > 20,
    next_before_id: eligible.length > 20 ? items[0].id : null });
}

async function setup() {
  const onActivity = vi.fn();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/conversations/page") {
      const agent = Number(url.searchParams.get("agent_id"));
      const query = url.searchParams.get("query") ?? "";
      return conversationPageResponse(agent === 7 && !query ? [conversation, other] : [], { agent_id: agent, query });
    }
    if (url.pathname === "/conversations/91/messages/page") {
      return historyPage(url.searchParams.has("before_id") ? Number(url.searchParams.get("before_id")) : null);
    }
    if (url.pathname === "/conversations/92/messages/page") return conversationMessagePageResponse([], { conversation_id: 92 });
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: "Long chat (ID: 91)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("Saved turn 45");
  return { fetchMock, onActivity, ...view };
}

function draft() {
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Unsent draft" } });
}

test("loads latest 20 first, prepends complete chronological history, and keeps all drafts", async () => {
  const { fetchMock, onActivity } = await setup();
  expect(screen.queryByText("Saved turn 1")).not.toBeInTheDocument();
  expect(screen.getByText("20 messages loaded. Earlier messages are available.")).toBeInTheDocument();
  draft();
  fireEvent.change(screen.getByLabelText("Conversation title"), { target: { value: "Rename draft" } });
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "New conversation draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  await screen.findByText("Saved turn 6");
  expect(screen.getByText("40 messages loaded. Earlier messages are available.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  await screen.findByText("Saved turn 1");
  expect(screen.getByText("45 messages loaded. All saved messages are loaded.")).toBeInTheDocument();
  const rows = within(screen.getByRole("list", { name: "Conversation messages" })).getAllByRole("listitem");
  expect(rows.map((row) => row.querySelector("p:last-child")?.textContent)).toEqual(messages.map((row) => row.content));
  expect(screen.getByRole("button", { name: "Load older messages" })).toBeDisabled();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Unsent draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Rename draft");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("New conversation draft");
  expect(fetchMock.mock.calls.map(([url]) => String(url)).slice(-2)).toEqual([
    "/conversations/91/messages/page?agent_id=7&limit=20&before_id=26",
    "/conversations/91/messages/page?agent_id=7&limit=20&before_id=6",
  ]);
  expect(onActivity).not.toHaveBeenCalled();
});

test("loads an older page once while busy and keeps the draft and rendered history", async () => {
  const { fetchMock } = await setup();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  draft();
  const button = screen.getByRole("button", { name: "Load older messages" });
  fireEvent.click(button); fireEvent.click(button);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(screen.getByRole("button", { name: "Loading older messages..." })).toBeDisabled();
  expect(screen.getByText("Saved turn 45")).toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Unsent draft");
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  await act(async () => { pending.resolve(historyPage(26)); });
  await screen.findByText("Saved turn 6");
  expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
});

test.each(["network", "overlap"])("keeps loaded messages and draft on an older %s failure and retries explicitly", async (failure) => {
  const { fetchMock } = await setup();
  draft();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(conversationMessagePageResponse([messages[36]], { before_id: 26 }));
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  await screen.findByRole("alert");
  expect(screen.getByText("Saved turn 45")).toBeInTheDocument();
  expect(screen.queryByText("Saved turn 6")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Unsent draft");
  expect(fetchMock).toHaveBeenCalledTimes(3);
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  await screen.findByText("Saved turn 6");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(4);
});

test("reload returns to the latest page and ignores an in-flight older response", async () => {
  const { fetchMock } = await setup();
  draft();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  fireEvent.click(screen.getByRole("button", { name: "Reload messages" }));
  await screen.findByText("Saved turn 45");
  await act(async () => { pending.resolve(historyPage(26)); });
  expect(screen.queryByText("Saved turn 6")).not.toBeInTheDocument();
  expect(screen.getByText("20 messages loaded. Earlier messages are available.")).toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Unsent draft");
});

test("a late older page cannot overwrite another selected conversation", async () => {
  const { fetchMock } = await setup();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "92" } });
  await screen.findByText("No messages in this conversation.");
  await act(async () => { pending.resolve(historyPage(26)); });
  expect(screen.queryByText("Saved turn 6")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Load older messages" })).not.toBeInTheDocument();
});

test("a late older page is ignored after switching Agents", async () => {
  const { fetchMock, rerender, onActivity } = await setup();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  rerender(<ConversationPanel agentId={8} onActivity={onActivity} />);
  await screen.findByText("No conversations for this Agent.");
  await act(async () => { pending.resolve(historyPage(26)); });
  expect(screen.queryByText("Saved turn 6")).not.toBeInTheDocument();
  expect(onActivity).not.toHaveBeenCalled();
});

test("searching other conversation titles preserves already loaded older history and the draft", async () => {
  await setup();
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  await screen.findByText("Saved turn 6");
  draft();
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "No matching title" } });
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await screen.findByText("No conversations match this title search.");
  expect(screen.getByText("Saved turn 6")).toBeInTheDocument();
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Unsent draft");
});

test("a completed chat refreshes latest history without issuing another POST", async () => {
  const { fetchMock, onActivity } = await setup();
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  await screen.findByText("Saved turn 6");
  draft();
  const newMessages = [...messages, { ...messages[0], id: 46, content: "Unsent draft" },
    { ...messages[0], id: 47, role: "assistant", content: "New answer" }];
  fetchMock.mockResolvedValueOnce(jsonResponse({ execution_id: 101, status: "completed", response: "New answer" }))
    .mockResolvedValueOnce(historyPage(null, newMessages));
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("New answer");
  expect(screen.queryByText("Saved turn 6")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("");
  expect(onActivity).toHaveBeenCalledExactlyOnceWith(7, 101);
  expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/chat?'))).toHaveLength(1);
  expect(screen.getByText("20 messages loaded. Earlier messages are available.")).toBeInTheDocument();
});
