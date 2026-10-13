import { StrictMode } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AgentMessageSearch } from "../src/components/AgentMessageSearch";
import { ConversationMessageSearch } from "../src/components/ConversationMessageSearch";
import { ConversationPanel } from "../src/components/ConversationPanel";
import type { MessageRoleFilter } from "../src/api/messageSearch";
import { agentSearchData, agentSearchResponse, siblingMarkdown, siblingMessage } from "./agentMessageSearchFixtures";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation, exportMessages } from "./conversationExportFixtures";
import { contextData, contextResponse } from "./messageContextFixtures";
import { contextExportResponse } from "./messageContextExportFixtures";
import { detailResponse, messageSearchData, searchResponse } from "./messageSearchFixtures";
import { deferredResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const props = { agentId: 7, disabled: false, revision: 0 };

function mockRequests() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const query = url.searchParams.get("query") ?? "";
    const role = url.searchParams.get("role") as MessageRoleFilter;
    const limit = Number(url.searchParams.get("limit") ?? 10), offset = Number(url.searchParams.get("offset") ?? 0);
    if (url.pathname === "/agents/7/messages/search") return agentSearchResponse(agentSearchData(query, role, limit, offset));
    if (url.pathname === "/conversations/page") return conversationPageResponse(query ? [] : [exportConversation], { agent_id: 7, query });
    if (url.pathname === "/conversations/91/messages/page") return conversationMessagePageResponse(exportMessages.slice(-20), { has_more: true, next_before_id: 6 });
    if (url.pathname === "/conversations/91/messages/search") return searchResponse(messageSearchData(query, role, limit, offset));
    const match = /^\/conversations\/(91|92)\/messages\/(\d+)(\/context(?:\/export)?)?$/.exec(url.pathname);
    if (match) {
      const conversationId = Number(match[1]), messageId = Number(match[2]);
      const messages = conversationId === 91 ? exportMessages : [siblingMessage];
      if (!match[3]) return detailResponse(messages.find((row) => row.id === messageId)!);
      const before = Number(url.searchParams.get("before") ?? 3), after = Number(url.searchParams.get("after") ?? 3);
      const context = { ...contextData(messageId, before, after, messages), conversation_id: conversationId };
      if (match[3] === "/context") return contextResponse(context);
      const format = url.searchParams.get("format") === "markdown" ? "markdown" : "json";
      return contextExportResponse(format, context, format === "markdown" && conversationId === 92 ? siblingMarkdown : undefined);
    }
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock); return fetchMock;
}

function enter(query = "中文") { fireEvent.change(screen.getByLabelText("Agent message content search"), { target: { value: query } }); }
async function search() {
  fireEvent.click(screen.getByRole("button", { name: "Search Agent messages" }));
  await screen.findByRole("list", { name: "Agent message search results" });
}

function downloads() {
  const create = vi.fn().mockReturnValue("blob:agent-context");
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn(); });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  return { create, clicked };
}

test("Agent search is available before selecting a conversation and makes no automatic search request", async () => {
  const fetchMock = mockRequests(); render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  expect(screen.getByLabelText("Conversation")).toHaveValue(""); expect(fetchMock).toHaveBeenCalledOnce();
  enter(); expect(fetchMock).toHaveBeenCalledOnce(); await search();
  expect(screen.getByText("Showing 1–10 of 26 matching Agent messages.")).toBeInTheDocument();
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
  expect(fetchMock.mock.calls.some((call) => String(call[0]).endsWith("/messages/page?agent_id=7&limit=20"))).toBe(false);
});

test("searches, reads another conversation, and downloads both formats while retaining chat, selection, drafts, and Inspector", async () => {
  const { clicked } = downloads(); const fetchMock = mockRequests(); const onActivity = vi.fn();
  render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  for (const [label, value] of [["Chat message", "Keep my chat draft"], ["Conversation title", "Rename draft"],
    ["New conversation title", "Create draft"], ["Conversation title search", "Title filter draft"]]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  enter(); await search();
  fireEvent.click(screen.getByRole("button", { name: "Read full Agent message 26" }));
  expect((await screen.findByRole("region", { name: "Full Agent saved message" })).textContent).toContain(siblingMessage.content);
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe("/conversations/92/messages/26?agent_id=7");
  fireEvent.click(screen.getByRole("button", { name: "Read Agent message context 26" }));
  const context = await screen.findByRole("region", { name: "Agent search message context" });
  expect((await within(context).findByRole("list", { name: "Surrounding saved messages" })).textContent).toContain(siblingMessage.content);
  for (const label of ["JSON", "Markdown"]) {
    fireEvent.click(within(context).getByRole("button", { name: `Export context ${label}` }));
    await within(context).findByText(`Downloaded conversation-92-message-26-context.${label === "JSON" ? "json" : "md"} with 1 displayed saved messages.`);
  }
  expect(clicked).toHaveBeenCalledTimes(2);
  expect(within(screen.getByRole("list", { name: "Conversation messages" })).getAllByRole("listitem")).toHaveLength(20);
  expect(screen.getByLabelText("Conversation")).toHaveValue("91"); expect(onActivity).not.toHaveBeenCalled();
  for (const [label, value] of [["Chat message", "Keep my chat draft"], ["Conversation title", "Rename draft"],
    ["New conversation title", "Create draft"], ["Conversation title search", "Title filter draft"]]) {
    expect(screen.getByLabelText(label)).toHaveValue(value);
  }
  expect(fetchMock.mock.calls.every((call) => !((call as unknown[])[1] as RequestInit | undefined)?.method)).toBe(true);
  expect(document.querySelector("script")).toBeNull();
});

test("pages across conversations and reads an older message outside the loaded page", async () => {
  const fetchMock = mockRequests(); render(<AgentMessageSearch {...props} />); enter(); await search();
  fireEvent.click(screen.getByRole("button", { name: "Next Agent matching messages" }));
  await screen.findByText("Showing 11–20 of 26 matching Agent messages.");
  fireEvent.click(screen.getByRole("button", { name: "Next Agent matching messages" }));
  await screen.findByText("Showing 21–26 of 26 matching Agent messages.");
  expect(screen.getByRole("button", { name: "Next Agent matching messages" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Read full Agent message 1" }));
  expect((await screen.findByRole("region", { name: "Full Agent saved message" })).textContent).toContain(exportMessages[0].content);
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe("/conversations/91/messages/1?agent_id=7");
  fireEvent.click(screen.getByRole("button", { name: "Close full Agent message" }));
  expect(screen.queryByRole("region", { name: "Full Agent saved message" })).not.toBeInTheDocument();
});

test("role, size, and clear actions invalidate results without automatic HTTP and preserve the search draft", async () => {
  const fetchMock = mockRequests(); render(<AgentMessageSearch {...props} />); enter(); await search();
  fireEvent.change(screen.getByLabelText("Agent message role"), { target: { value: "assistant" } });
  expect(fetchMock).toHaveBeenCalledOnce(); expect(screen.queryByRole("list", { name: "Agent message search results" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Agent search results per page"), { target: { value: "5" } }); await search();
  expect(screen.getByText("Showing 1–5 of 13 matching Agent messages.")).toBeInTheDocument();
  expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("role=assistant");
  fireEvent.click(screen.getByRole("button", { name: "Clear Agent message search" }));
  expect(screen.getByLabelText("Agent message content search")).toHaveValue("");
});

test("guards duplicate search submissions and ignores old results after a query edit", async () => {
  const pending = deferredResponse(); const fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  render(<AgentMessageSearch {...props} />); enter();
  const form = screen.getByRole("form", { name: "Search Agent conversation messages" });
  fireEvent.submit(form); fireEvent.submit(form); expect(fetchMock).toHaveBeenCalledOnce();
  const signal = fetchMock.mock.calls[0][1].signal as AbortSignal; enter("New query"); expect(signal.aborted).toBe(true);
  await act(async () => { pending.resolve(agentSearchResponse()); });
  expect(screen.queryByRole("list", { name: "Agent message search results" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Agent message content search")).toHaveValue("New query");
});

test.each(["network", "404"])("keeps the query and retries only explicitly after search %s", async (failure) => {
  const fetchMock = mockRequests();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(agentSearchResponse({ detail: "Agent not found" }, 404));
  render(<AgentMessageSearch {...props} />); enter();
  fireEvent.click(screen.getByRole("button", { name: "Search Agent messages" })); await screen.findByRole("alert");
  expect(screen.getByLabelText("Agent message content search")).toHaveValue("中文"); expect(fetchMock).toHaveBeenCalledOnce();
  await search(); expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(["network", "404", "changed"])("keeps results and retries full-message %s errors", async (failure) => {
  const fetchMock = mockRequests(); render(<AgentMessageSearch {...props} />); enter(); await search();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else if (failure === "404") fetchMock.mockResolvedValueOnce(agentSearchResponse({ detail: "Message not found" }, 404));
  else fetchMock.mockResolvedValueOnce(detailResponse({ ...siblingMessage, role: "user" }));
  fireEvent.click(screen.getByRole("button", { name: "Read full Agent message 26" })); await screen.findByRole("alert");
  expect(screen.getByRole("list", { name: "Agent message search results" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Read full Agent message 26" }));
  await screen.findByRole("region", { name: "Full Agent saved message" });
});

test.each(["revision", "disabled", "agent", "unmount"])("aborts late search responses after %s", async (change) => {
  const pending = deferredResponse(); const fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  const view = render(<AgentMessageSearch {...props} />); enter();
  fireEvent.click(screen.getByRole("button", { name: "Search Agent messages" }));
  if (change === "unmount") view.unmount();
  else view.rerender(<AgentMessageSearch {...props} agentId={change === "agent" ? 8 : 7}
    revision={change === "revision" ? 1 : 0} disabled={change === "disabled"} />);
  expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  await act(async () => { pending.resolve(agentSearchResponse()); });
  expect(screen.queryByRole("list", { name: "Agent message search results" })).not.toBeInTheDocument();
  if (change === "agent") expect(screen.getByLabelText("Agent message content search")).toHaveValue("");
});

test("query changes discard a pending full-message read", async () => {
  const fetchMock = mockRequests(); render(<AgentMessageSearch {...props} />); enter(); await search();
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Read full Agent message 26" })); enter("Latest query");
  await act(async () => { pending.resolve(detailResponse(siblingMessage)); });
  expect(screen.queryByRole("region", { name: "Full Agent saved message" })).not.toBeInTheDocument();
});

test.each(["query", "role", "size", "revision", "disabled", "agent", "close", "unmount"])("does not download a stale context after %s", async (change) => {
  const { clicked, create } = downloads(); const fetchMock = mockRequests();
  const view = render(<AgentMessageSearch {...props} />); enter(); await search();
  fireEvent.click(screen.getByRole("button", { name: "Read Agent message context 26" }));
  const region = await screen.findByRole("region", { name: "Agent search message context" });
  const button = await within(region).findByRole("button", { name: "Export context JSON" });
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise); fireEvent.click(button);
  const signal = (fetchMock.mock.calls.at(-1) as unknown[])[1] as RequestInit;
  if (change === "query") enter("Latest query");
  else if (change === "role") fireEvent.change(screen.getByLabelText("Agent message role"), { target: { value: "user" } });
  else if (change === "size") fireEvent.change(screen.getByLabelText("Agent search results per page"), { target: { value: "5" } });
  else if (change === "close") fireEvent.click(within(region).getByRole("button", { name: "Close message context" }));
  else if (change === "unmount") view.unmount();
  else view.rerender(<AgentMessageSearch {...props} agentId={change === "agent" ? 8 : 7}
    revision={change === "revision" ? 1 : 0} disabled={change === "disabled"} />);
  expect(signal.signal!.aborted).toBe(true);
  const context = { ...contextData(26, 3, 3, [siblingMessage]), conversation_id: 92 };
  await act(async () => { pending.resolve(contextExportResponse("json", context)); });
  expect(clicked).not.toHaveBeenCalled(); expect(create).not.toHaveBeenCalled();
});

test("global and conversation context controls remain independently labelled for the same saved message", async () => {
  mockRequests(); render(<><AgentMessageSearch {...props} /><ConversationMessageSearch conversationId={91} {...props} /></>);
  enter(); fireEvent.change(screen.getByLabelText("Agent search results per page"), { target: { value: "50" } }); await search();
  fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "中文" } });
  fireEvent.change(screen.getByLabelText("Search results per page"), { target: { value: "50" } });
  fireEvent.click(screen.getByRole("button", { name: "Search messages" })); await screen.findByRole("list", { name: "Message search results" });
  fireEvent.click(screen.getByRole("button", { name: "Read Agent message context 1" }));
  fireEvent.click(screen.getByRole("button", { name: "Read surrounding messages 1" }));
  const controls = screen.getAllByLabelText("Messages before selected");
  expect(controls).toHaveLength(2); expect(new Set(controls.map((control) => control.id)).size).toBe(2);
  await screen.findAllByRole("list", { name: "Surrounding saved messages" });
});

test("conversation title browsing retains Agent results, displayed context, and search draft", async () => {
  mockRequests(); render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  enter(); await search(); fireEvent.click(screen.getByRole("button", { name: "Read Agent message context 26" }));
  const region = await screen.findByRole("region", { name: "Agent search message context" });
  await within(region).findByRole("list", { name: "Surrounding saved messages" });
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "No matching title" } });
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await screen.findByText("Your current conversation is outside these results. Its messages and unsent draft stay selected.");
  expect(screen.getByRole("list", { name: "Agent message search results" })).toBeInTheDocument();
  expect(within(region).getByRole("list", { name: "Surrounding saved messages" })).toBeInTheDocument();
  expect(screen.getByLabelText("Agent message content search")).toHaveValue("中文");
});

test("Strict Mode does not search until submission and rejects excessive queries without HTTP", async () => {
  const fetchMock = mockRequests(); render(<StrictMode><AgentMessageSearch {...props} /></StrictMode>);
  expect(fetchMock).not.toHaveBeenCalled(); enter("x".repeat(201));
  expect(screen.getByRole("button", { name: "Search Agent messages" })).toBeDisabled();
  fireEvent.submit(screen.getByRole("form", { name: "Search Agent conversation messages" }));
  expect(fetchMock).not.toHaveBeenCalled(); expect(screen.getByRole("alert")).toHaveTextContent("1 to 200");
});
