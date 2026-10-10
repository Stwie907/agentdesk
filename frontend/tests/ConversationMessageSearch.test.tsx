import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import { ConversationMessageSearch } from "../src/components/ConversationMessageSearch";
import type { MessageRoleFilter } from "../src/api/messageSearch";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation, exportMessages } from "./conversationExportFixtures";
import { detailResponse, messageSearchData, searchResponse } from "./messageSearchFixtures";
import { deferredResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function setup() {
  const onActivity = vi.fn();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const agent = Number(url.searchParams.get("agent_id"));
    if (url.pathname === "/conversations/page") return conversationPageResponse(agent === 7 && !url.searchParams.get("query") ? [exportConversation] : [],
      { agent_id: agent, query: url.searchParams.get("query") ?? "" });
    if (url.pathname.endsWith("/messages/page")) return conversationMessagePageResponse(exportMessages.slice(-20), { has_more: true, next_before_id: 6 });
    if (url.pathname.endsWith("/messages/search")) return searchResponse(messageSearchData(url.searchParams.get("query")!,
      url.searchParams.get("role") as MessageRoleFilter, Number(url.searchParams.get("limit")), Number(url.searchParams.get("offset"))));
    const id = Number(url.pathname.split("/").at(-1));
    if (url.pathname.startsWith("/conversations/91/messages/") && id > 0) return detailResponse(exportMessages[id - 1]);
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Keep my chat draft" } });
  return { ...view, fetchMock, onActivity };
}

function enter(query = "中文") { fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: query } }); }
async function search() { fireEvent.click(screen.getByRole("button", { name: "Search messages" })); await screen.findByRole("list", { name: "Message search results" }); }

test("searches all 25 messages, opens an unloaded message, and preserves chat history and every draft", async () => {
  const { fetchMock, onActivity } = await setup();
  fireEvent.change(screen.getByLabelText("Conversation title"), { target: { value: "Rename draft" } });
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "Create draft" } });
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "Title draft" } });
  enter(); expect(fetchMock).toHaveBeenCalledTimes(2); await search();
  expect(screen.getByText("Showing 1–10 of 25 matching messages.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next matching messages" }));
  await screen.findByText("Showing 11–20 of 25 matching messages.");
  fireEvent.click(screen.getByRole("button", { name: "Next matching messages" }));
  await screen.findByText("Showing 21–25 of 25 matching messages.");
  expect(screen.getByRole("button", { name: "Next matching messages" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Read full message 1" }));
  const detail = await screen.findByRole("region", { name: "Full saved message" });
  expect(detail.textContent).toContain(exportMessages[0].content);
  expect(within(screen.getByRole("list", { name: "Conversation messages" })).getAllByRole("listitem")).toHaveLength(20);
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep my chat draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Rename draft");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("Create draft");
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("Title draft");
  expect(onActivity).not.toHaveBeenCalled();
  expect(fetchMock.mock.calls.every((call) => !((call as unknown[])[1] as RequestInit | undefined)?.method)).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Close full message" }));
  expect(screen.queryByRole("region", { name: "Full saved message" })).not.toBeInTheDocument();
});

test("role and page-size changes clear results without automatic requests", async () => {
  const { fetchMock } = await setup(); enter(); await search();
  fireEvent.change(screen.getByLabelText("Message role"), { target: { value: "assistant" } });
  expect(screen.queryByRole("list", { name: "Message search results" })).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  fireEvent.change(screen.getByLabelText("Search results per page"), { target: { value: "5" } }); await search();
  expect(screen.getByText("Showing 1–5 of 12 matching messages.")).toBeInTheDocument();
  expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("role=assistant");
  fireEvent.click(screen.getByRole("button", { name: "Clear message search" }));
  expect(screen.getByLabelText("Message content search")).toHaveValue("");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep my chat draft");
});

test("guards double submissions and query edits invalidate in-flight results", async () => {
  const { fetchMock } = await setup(); enter();
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  const form = screen.getByRole("form", { name: "Search conversation messages" });
  fireEvent.submit(form); fireEvent.submit(form); expect(fetchMock).toHaveBeenCalledTimes(3);
  enter("Latest query");
  await act(async () => { pending.resolve(searchResponse()); });
  expect(screen.queryByRole("list", { name: "Message search results" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Message content search")).toHaveValue("Latest query");
});

test.each(["network", "404"])("keeps drafts and retries search only on submission after %s", async (failure) => {
  const { fetchMock } = await setup(); enter();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(searchResponse({ detail: "Conversation not found" }, 404));
  fireEvent.click(screen.getByRole("button", { name: "Search messages" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Message content search")).toHaveValue("中文");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep my chat draft");
  expect(fetchMock).toHaveBeenCalledTimes(3); await search();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(["network", "404"])("keeps search results after a full-message %s failure", async (failure) => {
  const { fetchMock } = await setup(); enter(); await search();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(searchResponse({ detail: "Message not found" }, 404));
  fireEvent.click(screen.getByRole("button", { name: "Read full message 25" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("list", { name: "Message search results" })).toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep my chat draft");
  fireEvent.click(screen.getByRole("button", { name: "Read full message 25" }));
  await screen.findByRole("region", { name: "Full saved message" });
});

test("renders code as text and highlights Unicode without splitting an emoji", async () => {
  const content = '🐍<script>alert("literal")</script>\r\nTail:  \n';
  const row = { ...exportMessages[0], content };
  const fetchMock = vi.fn().mockResolvedValueOnce(searchResponse(messageSearchData("<script>", null, 10, 0, [row])))
    .mockResolvedValueOnce(detailResponse(row)); vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<ConversationMessageSearch conversationId={91} agentId={7} disabled={false} revision={0} />);
  enter("<script>"); await search(); expect(container.querySelector("mark")?.textContent).toBe("<script>");
  expect(container.querySelector("script")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Read full message 1" }));
  const detail = await screen.findByRole("region", { name: "Full saved message" });
  expect(detail.textContent).toContain(content); expect(container.querySelector("script")).toBeNull();
});

test.each(["revision", "disabled", "agent", "conversation", "unmount"])("invalidates late responses after %s changes", async (change) => {
  const pending = deferredResponse(); vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending.promise));
  const props = { conversationId: 91, agentId: 7, disabled: false, revision: 0 };
  const { rerender, unmount } = render(<ConversationMessageSearch {...props} />); enter();
  fireEvent.click(screen.getByRole("button", { name: "Search messages" }));
  if (change === "unmount") unmount();
  else rerender(<ConversationMessageSearch {...props} revision={change === "revision" ? 1 : 0}
    disabled={change === "disabled"} agentId={change === "agent" ? 8 : 7} conversationId={change === "conversation" ? 92 : 91} />);
  await act(async () => { pending.resolve(searchResponse()); });
  expect(screen.queryByRole("list", { name: "Message search results" })).not.toBeInTheDocument();
});

test("changing the query discards a late full-message response", async () => {
  const { fetchMock } = await setup(); enter(); await search();
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Read full message 25" })); enter("New query");
  await act(async () => { pending.resolve(detailResponse(exportMessages[24])); });
  expect(screen.queryByRole("region", { name: "Full saved message" })).not.toBeInTheDocument();
});

test("delete confirmation locks search and active title filtering preserves its draft", async () => {
  await setup(); enter(); await search();
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  expect(screen.getByRole("button", { name: "Search messages" })).toBeDisabled();
  expect(screen.queryByRole("list", { name: "Message search results" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel delete" }));
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "No matching title" } });
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await screen.findByText("Your current conversation is outside these results. Its messages and unsent draft stay selected.");
  expect(screen.getByLabelText("Message content search")).toHaveValue("中文"); await search();
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("No matching title");
});
