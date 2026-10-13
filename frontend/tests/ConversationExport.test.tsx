import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation as conversation, exportMessages as messages, exportResponse } from "./conversationExportFixtures";
import { deferredResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const other = { ...conversation, id: 92, title: "Other chat" };

async function setup() {
  const create = vi.fn().mockReturnValue("blob:export"); const revoke = vi.fn();
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const onActivity = vi.fn();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/conversations/page") {
      const query = url.searchParams.get("query") ?? ""; const agent = Number(url.searchParams.get("agent_id"));
      return conversationPageResponse(agent === 7 && !query ? [conversation, other] : [], { agent_id: agent, query });
    }
    if (url.pathname === "/conversations/91/messages/page") return conversationMessagePageResponse(messages.slice(-20),
      { has_more: true, next_before_id: 6 });
    if (url.pathname === "/conversations/92/messages/page") return conversationMessagePageResponse([], { conversation_id: 92 });
    if (url.pathname === "/conversations/91/export") return exportResponse(url.searchParams.get("format") as "json" | "markdown");
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: `${conversation.title} (ID: 91)` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText(messages[24].content.trim());
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Keep draft" } });
  return { ...view, fetchMock, onActivity, clicked };
}

test.each(["JSON", "Markdown"])("exports full %s history while preserving loaded pages and every draft", async (label) => {
  const { fetchMock, clicked, onActivity } = await setup();
  fireEvent.change(screen.getByLabelText("Conversation title"), { target: { value: "Rename draft" } });
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "Create draft" } });
  fireEvent.click(screen.getByRole("button", { name: `Export ${label}` }));
  await screen.findByText(`Downloaded conversation-91.${label === "JSON" ? "json" : "md"} with 25 saved messages.`);
  expect(clicked).toHaveBeenCalledOnce();
  expect(screen.getByText("20 messages loaded. Earlier messages are available.")).toBeInTheDocument();
  expect(screen.queryByText(messages[0].content.trim())).not.toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Rename draft");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("Create draft");
  expect(fetchMock).toHaveBeenCalledTimes(3); expect(onActivity).not.toHaveBeenCalled();
});

test("guards repeated clicks while pending and keeps the chat draft editable", async () => {
  const { fetchMock, clicked } = await setup();
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  const button = screen.getByRole("button", { name: "Export JSON" });
  fireEvent.click(button); fireEvent.click(button);
  expect(screen.getByRole("button", { name: "Exporting JSON..." })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Export Markdown" })).toBeDisabled();
  expect(screen.getByLabelText("Chat message")).toBeEnabled(); expect(fetchMock).toHaveBeenCalledTimes(3);
  await act(async () => { pending.resolve(exportResponse()); });
  await screen.findByText("Downloaded conversation-91.json with 25 saved messages.");
  expect(clicked).toHaveBeenCalledOnce();
});

test.each(["network", "404", "413", "metadata"])("retains history and drafts on %s failure and retries explicitly", async (failure) => {
  const { fetchMock, clicked } = await setup();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else if (failure === "metadata") fetchMock.mockResolvedValueOnce(exportResponse("json", undefined, { "X-Agent-ID": "8" }));
  else fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Export limit reached" }), { status: Number(failure) }));
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  await screen.findByRole("alert"); expect(clicked).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep draft");
  expect(screen.getByText("20 messages loaded. Earlier messages are available.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  await screen.findByText("Downloaded conversation-91.json with 25 saved messages.");
  expect(clicked).toHaveBeenCalledOnce(); expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(["conversation", "agent", "unmount"])("discards late exports after %s changes", async (change) => {
  const { fetchMock, clicked, rerender, unmount, onActivity } = await setup();
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  if (change === "conversation") fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "92" } });
  else if (change === "agent") rerender(<ConversationPanel agentId={8} onActivity={onActivity} />);
  else unmount();
  await act(async () => { pending.resolve(exportResponse()); });
  expect(clicked).not.toHaveBeenCalled();
  expect(screen.queryByText("Downloaded conversation-91.json with 25 saved messages.")).not.toBeInTheDocument();
});

test("exports the active off-page chat and locks export during delete confirmation", async () => {
  const { fetchMock, clicked } = await setup();
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "No results" } });
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await screen.findByText("Your current conversation is outside these results. Its messages and unsent draft stay selected.");
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  await screen.findByText("Downloaded conversation-91.json with 25 saved messages.");
  expect(clicked).toHaveBeenCalledOnce();
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe("/conversations/91/export?agent_id=7&format=json");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep draft");
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Export Markdown" })).toBeDisabled();
});
