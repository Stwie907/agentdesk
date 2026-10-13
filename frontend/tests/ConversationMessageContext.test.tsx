import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import { ConversationMessageSearch } from "../src/components/ConversationMessageSearch";
import { ConversationMessageContext } from "../src/components/ConversationMessageContext";
import type { MessageRoleFilter } from "../src/api/messageSearch";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation, exportMessages } from "./conversationExportFixtures";
import { contextData, contextPreview, contextResponse } from "./messageContextFixtures";
import { detailResponse, messageSearchData, searchResponse } from "./messageSearchFixtures";
import { deferredResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const props = { conversationId: 91, agentId: 7, message: contextPreview(), disabled: false, onClose: vi.fn() };

test("includes earlier and later roles and marks the selected message", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse()));
  render(<ConversationMessageContext {...props} />);
  const list = await screen.findByRole("list", { name: "Surrounding saved messages" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(7);
  expect(list.querySelector('[aria-current="true"]')?.textContent).toContain("Selected message 13");
  expect(screen.getByText("Earlier saved messages remain outside this context.")).toBeInTheDocument();
  expect(screen.getByText("Later saved messages remain outside this context.")).toBeInTheDocument();
});

test("Strict Mode and repeated reload clicks start only one active request", async () => {
  const pending = deferredResponse(); const fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  render(<StrictMode><ConversationMessageContext {...props} /></StrictMode>);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Loading message context..." }));
  fireEvent.click(screen.getByRole("button", { name: "Loading message context..." }));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve(contextResponse()); });
  await screen.findByRole("list", { name: "Surrounding saved messages" });
});

test("window changes clear context without eager requests and require an explicit reload", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(contextResponse()).mockResolvedValueOnce(contextResponse(contextData(13, 0, 10)));
  vi.stubGlobal("fetch", fetchMock); render(<ConversationMessageContext {...props} />);
  await screen.findByRole("list", { name: "Surrounding saved messages" });
  fireEvent.change(screen.getByLabelText("Messages before selected"), { target: { value: "0" } });
  fireEvent.change(screen.getByLabelText("Messages after selected"), { target: { value: "10" } });
  expect(fetchMock).toHaveBeenCalledTimes(1); expect(screen.queryByRole("list", { name: "Surrounding saved messages" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Reload message context" }));
  const list = await screen.findByRole("list", { name: "Surrounding saved messages" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(11);
  expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("before=0&after=10");
});

test.each(["network", "404"])("keeps count drafts and retries explicitly after %s", async (failure) => {
  const fetchMock = vi.fn();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(contextResponse({ detail: "Message not found" }, 404));
  fetchMock.mockResolvedValueOnce(contextResponse(contextData(13, 5, 3))); vi.stubGlobal("fetch", fetchMock);
  render(<ConversationMessageContext {...props} />); await screen.findByRole("alert");
  fireEvent.change(screen.getByLabelText("Messages before selected"), { target: { value: "5" } });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Reload message context" }));
  await screen.findByRole("list", { name: "Surrounding saved messages" });
  expect(screen.getByLabelText("Messages before selected")).toHaveValue("5");
});

test.each(["role", "timestamp"])("rejects a changed selected message %s", async (change) => {
  const data = contextData();
  if (change === "role") data.items[3].role = "system";
  else data.items[3].created_at = "2026-10-10T06:00:00.000001";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse(data)));
  render(<ConversationMessageContext {...props} />); await screen.findByRole("alert");
  expect(screen.queryByRole("list", { name: "Surrounding saved messages" })).not.toBeInTheDocument();
});

test("count edits abort a pending read and discard its late result", async () => {
  const pending = deferredResponse(); const fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  render(<ConversationMessageContext {...props} />); await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const signal = (fetchMock.mock.calls[0][1] as RequestInit).signal!;
  fireEvent.change(screen.getByLabelText("Messages before selected"), { target: { value: "1" } });
  expect(signal.aborted).toBe(true);
  await act(async () => { pending.resolve(contextResponse()); });
  expect(screen.queryByRole("list", { name: "Surrounding saved messages" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Messages before selected")).toHaveValue("1");
});

test("long literal content renders as text without an executable script", async () => {
  const messages = exportMessages.map((row) => ({ ...row }));
  messages[0].content = '中文🐍<script>alert("literal")</script>\r\n' + "🐍".repeat(3000) + "Tail:  \n";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextResponse(contextData(1, 3, 3, messages))));
  const { container } = render(<ConversationMessageContext {...props} message={contextPreview(1, messages)} />);
  const list = await screen.findByRole("list", { name: "Surrounding saved messages" });
  expect(list.textContent).toContain(messages[0].content); expect(container.querySelector("script")).toBeNull();
});

test("reads an unloaded search result while keeping the selected chat and every draft", async () => {
  const onActivity = vi.fn();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/conversations/page") return conversationPageResponse([exportConversation]);
    if (url.pathname.endsWith("/messages/page")) return conversationMessagePageResponse(exportMessages.slice(-20), { has_more: true, next_before_id: 6 });
    if (url.pathname.endsWith("/messages/search")) return searchResponse(messageSearchData(url.searchParams.get("query")!,
      url.searchParams.get("role") as MessageRoleFilter, Number(url.searchParams.get("limit")), Number(url.searchParams.get("offset"))));
    if (url.pathname.endsWith("/context")) return contextResponse(contextData(Number(url.pathname.split("/").at(-2))));
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock); render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  const drafts = { "Chat message": "Chat draft", "Conversation title": "Rename draft", "New conversation title": "Create draft", "Conversation title search": "Title draft" };
  for (const [label, value] of Object.entries(drafts)) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "中文" } });
  fireEvent.change(screen.getByLabelText("Search results per page"), { target: { value: "50" } });
  fireEvent.click(screen.getByRole("button", { name: "Search messages" })); await screen.findByRole("list", { name: "Message search results" });
  fireEvent.click(screen.getByRole("button", { name: "Read surrounding messages 1" }));
  const list = await screen.findByRole("list", { name: "Surrounding saved messages" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(4);
  expect(within(screen.getByRole("list", { name: "Conversation messages" })).getAllByRole("listitem")).toHaveLength(20);
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  for (const [label, value] of Object.entries(drafts)) expect(screen.getByLabelText(label)).toHaveValue(value);
  expect(onActivity).not.toHaveBeenCalled();
  expect(fetchMock.mock.calls.every((call) => !((call as unknown[])[1] as RequestInit | undefined)?.method)).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Close message context" }));
  expect(screen.queryByRole("region", { name: "Saved message context" })).not.toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Message search results" })).toBeInTheDocument();
});

test.each(["query", "role", "size", "revision", "disabled", "agent", "conversation", "unmount"])("search change %s discards a late context response", async (change) => {
  const pending = deferredResponse();
  const fetchMock = vi.fn().mockResolvedValueOnce(searchResponse()).mockReturnValueOnce(pending.promise); vi.stubGlobal("fetch", fetchMock);
  const searchProps = { conversationId: 91, agentId: 7, disabled: false, revision: 0 };
  const view = render(<ConversationMessageSearch {...searchProps} />);
  fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "中文" } });
  fireEvent.click(screen.getByRole("button", { name: "Search messages" })); await screen.findByRole("list", { name: "Message search results" });
  fireEvent.click(screen.getByRole("button", { name: "Read surrounding messages 25" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const signal = (fetchMock.mock.calls[1][1] as RequestInit).signal!;
  if (change === "query") fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "New query" } });
  else if (change === "role") fireEvent.change(screen.getByLabelText("Message role"), { target: { value: "assistant" } });
  else if (change === "size") fireEvent.change(screen.getByLabelText("Search results per page"), { target: { value: "5" } });
  else if (change === "unmount") view.unmount();
  else view.rerender(<ConversationMessageSearch {...searchProps} revision={change === "revision" ? 1 : 0} disabled={change === "disabled"}
    agentId={change === "agent" ? 8 : 7} conversationId={change === "conversation" ? 92 : 91} />);
  expect(signal.aborted).toBe(true);
  await act(async () => { pending.resolve(contextResponse(contextData(25))); });
  expect(screen.queryByRole("list", { name: "Surrounding saved messages" })).not.toBeInTheDocument();
});

test("switching to full-message details aborts the prior context read", async () => {
  const pending = deferredResponse(); const fetchMock = vi.fn().mockResolvedValueOnce(searchResponse())
    .mockReturnValueOnce(pending.promise).mockResolvedValueOnce(detailResponse(exportMessages[24])); vi.stubGlobal("fetch", fetchMock);
  render(<ConversationMessageSearch conversationId={91} agentId={7} disabled={false} revision={0} />);
  fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "中文" } });
  fireEvent.click(screen.getByRole("button", { name: "Search messages" })); await screen.findByRole("list", { name: "Message search results" });
  fireEvent.click(screen.getByRole("button", { name: "Read surrounding messages 25" })); await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const signal = (fetchMock.mock.calls[1][1] as RequestInit).signal!;
  fireEvent.click(screen.getByRole("button", { name: "Read full message 25" }));
  await screen.findByRole("region", { name: "Full saved message" });
  expect(signal.aborted).toBe(true);
  await act(async () => { pending.resolve(contextResponse(contextData(25))); });
  expect(screen.queryByRole("region", { name: "Saved message context" })).not.toBeInTheDocument();
});
