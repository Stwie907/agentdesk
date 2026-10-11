import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import { ConversationMessageSearch } from "../src/components/ConversationMessageSearch";
import { MessageContextExport } from "../src/components/MessageContextExport";
import type { MessageRoleFilter } from "../src/api/messageSearch";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation, exportMessages } from "./conversationExportFixtures";
import { contextData, contextResponse } from "./messageContextFixtures";
import { contextExportData, contextExportResponse } from "./messageContextExportFixtures";
import { messageSearchData, searchResponse } from "./messageSearchFixtures";
import { deferredResponse } from "./taskFixtures";

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function downloads() {
  const create = vi.fn().mockReturnValue("blob:context-export"); const revoke = vi.fn();
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  return { create, revoke, clicked };
}

test.each(["JSON", "Markdown"])("downloads %s only after an explicit click and keeps the complete conversation export separate", async (label) => {
  const { clicked } = downloads();
  const format = label === "JSON" ? "json" : "markdown";
  const fetchMock = vi.fn().mockResolvedValue(contextExportResponse(format)); vi.stubGlobal("fetch", fetchMock);
  render(<StrictMode><MessageContextExport context={contextData()} disabled={false} /></StrictMode>);
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.getByText(/For an importable backup, use Export JSON/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: `Export context ${label}` }));
  await screen.findByText(`Downloaded conversation-91-message-13-context.${format === "json" ? "json" : "md"} with 7 displayed saved messages.`);
  expect(clicked).toHaveBeenCalledOnce(); expect(fetchMock).toHaveBeenCalledOnce();
  expect(document.querySelector('a[download]')).toBeNull();
});

test("prevents duplicate and simultaneous format requests", async () => {
  const { clicked } = downloads(); const pending = deferredResponse();
  const fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  render(<MessageContextExport context={contextData()} disabled={false} />);
  const button = screen.getByRole("button", { name: "Export context JSON" });
  fireEvent.click(button); fireEvent.click(button);
  fireEvent.click(screen.getByRole("button", { name: "Export context Markdown" }));
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "Exporting context JSON..." })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Export context Markdown" })).toBeDisabled();
  await act(async () => { pending.resolve(contextExportResponse()); });
  await screen.findByText(/Downloaded conversation-91-message-13-context.json/);
  expect(clicked).toHaveBeenCalledOnce();
});

test.each(["network", "404", "413", "metadata", "changed"])("preserves displayed context and allows explicit retry after %s failure", async (failure) => {
  const { clicked } = downloads(); const fetchMock = vi.fn();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else if (failure === "404" || failure === "413") fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Export failed" }), { status: Number(failure) }));
  else if (failure === "metadata") fetchMock.mockResolvedValueOnce(contextExportResponse("json", contextData(), undefined, { "X-Agent-ID": "8" }));
  else { const value = contextExportData(); value.context.items[0].content += "Changed"; fetchMock.mockResolvedValueOnce(contextExportResponse("json", contextData(), value)); }
  fetchMock.mockResolvedValueOnce(contextExportResponse()); vi.stubGlobal("fetch", fetchMock);
  const source = contextData(); render(<MessageContextExport context={source} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Export context JSON" }));
  const alert = await screen.findByRole("alert"); expect(clicked).not.toHaveBeenCalled(); expect(fetchMock).toHaveBeenCalledOnce();
  if (failure === "changed") expect(alert.textContent).toContain("Reload message context before exporting");
  if (failure === "404") expect(alert.textContent).toContain("no longer available");
  expect(source.items).toHaveLength(7);
  fireEvent.click(screen.getByRole("button", { name: "Export context JSON" }));
  await screen.findByText(/Downloaded conversation-91-message-13-context.json/);
  expect(clicked).toHaveBeenCalledOnce(); expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(["disabled", "context", "unmount"])("aborts and discards a late attachment after %s", async (change) => {
  const { clicked, create } = downloads(); const pending = deferredResponse();
  const fetchMock = vi.fn().mockReturnValue(pending.promise); vi.stubGlobal("fetch", fetchMock);
  const source = contextData(); const view = render(<MessageContextExport context={source} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Export context JSON" }));
  const signal = (fetchMock.mock.calls[0][1] as RequestInit).signal!;
  if (change === "unmount") view.unmount();
  else view.rerender(<MessageContextExport context={change === "context" ? contextData(1) : source} disabled={change === "disabled"} />);
  expect(signal.aborted).toBe(true);
  await act(async () => { pending.resolve(contextExportResponse()); });
  expect(clicked).not.toHaveBeenCalled(); expect(create).not.toHaveBeenCalled();
});

test("revokes the temporary download URL after the browser starts reading it", async () => {
  const { revoke } = downloads(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue(contextExportResponse()));
  render(<MessageContextExport context={contextData()} disabled={false} />);
  vi.useFakeTimers(); fireEvent.click(screen.getByRole("button", { name: "Export context JSON" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(revoke).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(revoke).toHaveBeenCalledWith("blob:context-export");
});

test.each(["JSON", "Markdown"])("exports an unloaded older %s context while preserving chat, search, title filter, and every draft", async (label) => {
  const { clicked } = downloads(); const onActivity = vi.fn();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/conversations/page") return conversationPageResponse([exportConversation]);
    if (url.pathname.endsWith("/messages/page")) return conversationMessagePageResponse(exportMessages.slice(-20), { has_more: true, next_before_id: 6 });
    if (url.pathname.endsWith("/messages/search")) return searchResponse(messageSearchData(url.searchParams.get("query")!,
      url.searchParams.get("role") as MessageRoleFilter, Number(url.searchParams.get("limit")), Number(url.searchParams.get("offset"))));
    if (url.pathname.endsWith("/context")) return contextResponse(contextData(1));
    if (url.pathname.endsWith("/context/export")) return contextExportResponse(url.searchParams.get("format") as "json" | "markdown", contextData(1));
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock); render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  const drafts = { "Chat message": "Chat draft", "Conversation title": "Rename draft", "New conversation title": "Create draft", "Conversation title search": "Title draft" };
  for (const [name, value] of Object.entries(drafts)) fireEvent.change(screen.getByLabelText(name), { target: { value } });
  fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "中文" } });
  fireEvent.change(screen.getByLabelText("Search results per page"), { target: { value: "50" } });
  fireEvent.click(screen.getByRole("button", { name: "Search messages" })); await screen.findByRole("list", { name: "Message search results" });
  fireEvent.click(screen.getByRole("button", { name: "Read surrounding messages 1" }));
  await screen.findByRole("list", { name: "Surrounding saved messages" });
  fireEvent.click(screen.getByRole("button", { name: `Export context ${label}` }));
  await screen.findByText(`Downloaded conversation-91-message-1-context.${label === "JSON" ? "json" : "md"} with 4 displayed saved messages.`);
  expect(clicked).toHaveBeenCalledOnce();
  expect(within(screen.getByRole("list", { name: "Conversation messages" })).getAllByRole("listitem")).toHaveLength(20);
  expect(within(screen.getByRole("list", { name: "Surrounding saved messages" })).getAllByRole("listitem")).toHaveLength(4);
  expect(screen.getByLabelText("Conversation")).toHaveValue("91"); expect(screen.getByLabelText("Message content search")).toHaveValue("中文");
  for (const [name, value] of Object.entries(drafts)) expect(screen.getByLabelText(name)).toHaveValue(value);
  expect(onActivity).not.toHaveBeenCalled();
  expect(fetchMock.mock.calls.every((call) => !((call as unknown[])[1] as RequestInit | undefined)?.method)).toBe(true);
});

test.each(["before", "after", "reload", "close", "query", "role", "size", "revision", "disabled", "agent", "conversation", "unmount"])(
  "never downloads a stale attachment after %s changes", async (change) => {
    const { clicked, create } = downloads(); const pending = deferredResponse();
    const fetchMock = vi.fn().mockResolvedValueOnce(searchResponse()).mockResolvedValueOnce(contextResponse(contextData(25)))
      .mockReturnValueOnce(pending.promise).mockResolvedValue(contextResponse(contextData(25))); vi.stubGlobal("fetch", fetchMock);
    const props = { conversationId: 91, agentId: 7, disabled: false, revision: 0 };
    const view = render(<ConversationMessageSearch {...props} />);
    fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "中文" } });
    fireEvent.click(screen.getByRole("button", { name: "Search messages" })); await screen.findByRole("list", { name: "Message search results" });
    fireEvent.click(screen.getByRole("button", { name: "Read surrounding messages 25" }));
    await screen.findByRole("list", { name: "Surrounding saved messages" });
    fireEvent.click(screen.getByRole("button", { name: "Export context JSON" }));
    const signal = (fetchMock.mock.calls[2][1] as RequestInit).signal!;
    if (change === "before") fireEvent.change(screen.getByLabelText("Messages before selected"), { target: { value: "5" } });
    else if (change === "after") fireEvent.change(screen.getByLabelText("Messages after selected"), { target: { value: "5" } });
    else if (change === "reload") fireEvent.click(screen.getByRole("button", { name: "Reload message context" }));
    else if (change === "close") fireEvent.click(screen.getByRole("button", { name: "Close message context" }));
    else if (change === "query") fireEvent.change(screen.getByLabelText("Message content search"), { target: { value: "New query" } });
    else if (change === "role") fireEvent.change(screen.getByLabelText("Message role"), { target: { value: "assistant" } });
    else if (change === "size") fireEvent.change(screen.getByLabelText("Search results per page"), { target: { value: "5" } });
    else if (change === "unmount") view.unmount();
    else view.rerender(<ConversationMessageSearch {...props} revision={change === "revision" ? 1 : 0}
      disabled={change === "disabled"} agentId={change === "agent" ? 8 : 7} conversationId={change === "conversation" ? 92 : 91} />);
    expect(signal.aborted).toBe(true);
    await act(async () => { pending.resolve(contextExportResponse("json", contextData(25))); });
    expect(clicked).not.toHaveBeenCalled(); expect(create).not.toHaveBeenCalled();
  },
);
