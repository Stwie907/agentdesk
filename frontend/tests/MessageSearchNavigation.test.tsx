import { StrictMode } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import { AgentMessageSearch } from "../src/components/AgentMessageSearch";
import { exportConversation, exportMessages } from "./conversationExportFixtures";
import { mockNavigationRequests, siblingConversation } from "./messageNavigationFixtures";
import { siblingMessage } from "./agentMessageSearchFixtures";
import { contextData } from "./messageContextFixtures";
import { contextExportResponse } from "./messageContextExportFixtures";
import { conversationPageResponse } from "./conversationFixtures";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function setup(selected = true, includeSibling = false) {
  const requests = mockNavigationRequests(includeSibling), onActivity = vi.fn();
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  if (selected) {
    fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
    await screen.findByText("20 messages loaded. Earlier messages are available.");
  }
  fireEvent.change(screen.getByLabelText("Agent message content search"), { target: { value: "中文" } });
  fireEvent.change(screen.getByLabelText("Agent search results per page"), { target: { value: "50" } });
  fireEvent.click(screen.getByRole("button", { name: "Search Agent messages" }));
  await screen.findByText("Showing 1–26 of 26 matching Agent messages.");
  return { ...requests, onActivity, ...view };
}

function type(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
async function open(id = 26) {
  fireEvent.click(screen.getByRole("button", { name: `Open message ${id} in chat` }));
  const heading = await screen.findByRole("heading", { name: `Located message ${id} in conversation ${id === 26 ? 92 : 91}` });
  const region = heading.closest("section")!;
  await within(region).findByRole("list", { name: "Surrounding saved messages" });
  return region;
}

test("opens a result before selecting any conversation, outside the current title page, with literal saved content and focus", async () => {
  const { fetchMock, onActivity } = await setup(false);
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
  const region = await open();
  expect(screen.getByLabelText("Conversation")).toHaveValue("92");
  expect(region).toHaveFocus(); expect(region.textContent).toContain(siblingMessage.content);
  expect(region.querySelector("script")).toBeNull(); expect(onActivity).not.toHaveBeenCalled();
  expect(fetchMock.mock.calls.some(([url]) => url === "/conversations/92?agent_id=7")).toBe(true);
  expect(fetchMock.mock.calls.some(([url]) => url === "/conversations/92/messages/26?agent_id=7")).toBe(true);
  expect(fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true);
});

test("keeps separate exact chat/rename drafts on round trips and retains search, title filter, creation draft, and Inspector", async () => {
  const { onActivity } = await setup();
  const mainDraft = "  Keep main draft\n中文  ", mainRename = " Main rename draft ";
  type("Chat message", mainDraft); type("Conversation title", mainRename);
  type("New conversation title", "Create draft"); type("Conversation title search", "no-match");
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await screen.findByText("No conversations match this title search.");
  await open();
  expect(screen.getByLabelText("Chat message")).toHaveValue("");
  expect(screen.getByLabelText("Conversation title")).toHaveValue(siblingConversation.title);
  type("Chat message", "Sibling chat draft"); type("Conversation title", "Sibling rename draft");
  const region = await open(1);
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  expect(screen.getByLabelText("Chat message")).toHaveValue(mainDraft);
  expect(screen.getByLabelText("Conversation title")).toHaveValue(mainRename);
  expect(within(region).getAllByRole("listitem")).toHaveLength(4);
  expect(within(screen.getByRole("list", { name: "Conversation messages" })).getAllByRole("listitem")).toHaveLength(20);
  expect(within(region).getByText("This saved message is outside the loaded chat page. Its context is shown below.")).toBeInTheDocument();
  await open();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Sibling chat draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Sibling rename draft");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("Create draft");
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("no-match");
  expect(screen.getByLabelText("Agent message content search")).toHaveValue("中文");
  expect(screen.getByLabelText("Agent search results per page")).toHaveValue("50");
  expect(onActivity).not.toHaveBeenCalled();
});

test("ordinary Conversation selection also restores each conversation's drafts and clears located context", async () => {
  await setup(true, true); type("Chat message", "Main draft"); type("Conversation title", "Main rename");
  await open(); type("Chat message", "Sibling draft"); type("Conversation title", "Sibling rename");
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  expect(screen.queryByRole("region", { name: "Located saved message in chat" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Main draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Main rename");
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "92" } });
  await screen.findByText("1 messages loaded. All saved messages are loaded.");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Sibling draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Sibling rename");
});

test("preserves already loaded older history when opening another message in the same conversation", async () => {
  const { fetchMock } = await setup();
  fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
  await screen.findByText("25 messages loaded. All saved messages are loaded.");
  const region = await open(1);
  expect(within(region).getByText("This saved message is also in the loaded chat history.")).toBeInTheDocument();
  const rows = within(screen.getByRole("list", { name: "Conversation messages" })).getAllByRole("listitem");
  expect(rows).toHaveLength(25); expect(rows[0]).toHaveAttribute("aria-current", "true");
  expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/messages/page"))).toHaveLength(2);
  fireEvent.click(within(region).getByRole("button", { name: "Close located message" }));
  expect(screen.getByLabelText("Conversation")).toHaveValue("91"); expect(rows[0]).not.toHaveAttribute("aria-current");
});

test("a delayed title page cannot overwrite a newer scoped navigation to the same conversation", async () => {
  const { fetchMock, respond } = await setup();
  const pending = deferredResponse(); const fresh = { ...exportConversation, title: "Fresh saved title" };
  fetchMock.mockReturnValueOnce(pending.promise);
  type("Conversation title search", "中文");
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  fetchMock.mockImplementation((input) => String(input).startsWith("/conversations/91?") ?
    Promise.resolve(jsonResponse(fresh)) : respond(input));
  const region = await open(1);
  await act(async () => { pending.resolve(conversationPageResponse([exportConversation], { query: "中文" })); });
  expect(within(region).getByText("Conversation title: Fresh saved title")).toBeInTheDocument();
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Fresh saved title");
  expect(screen.getByRole("option", { name: "Fresh saved title (ID: 91)" })).toBeInTheDocument();
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
});

test("downloads the located context from its original conversation in both formats", async () => {
  const create = vi.fn().mockReturnValue("blob:located-context");
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn(); });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  await setup(); const region = await open();
  for (const format of ["JSON", "Markdown"]) {
    fireEvent.click(within(region).getByRole("button", { name: `Export context ${format}` }));
    await within(region).findByText(`Downloaded conversation-92-message-26-context.${format === "JSON" ? "json" : "md"} with 1 displayed saved messages.`);
  }
  expect(clicked).toHaveBeenCalledTimes(2);
  expect(clicked.mock.instances.map((anchor) => (anchor as HTMLAnchorElement).download)).toEqual([
    "conversation-92-message-26-context.json", "conversation-92-message-26-context.md"]);
  expect(screen.getByLabelText("Conversation")).toHaveValue("92");
});

test("saves the latest draft edits made while navigation is pending and ignores duplicate clicks", async () => {
  const { fetchMock } = await setup(); const pending = deferredResponse();
  type("Chat message", "Initial draft"); fetchMock.mockReturnValueOnce(pending.promise);
  const button = screen.getByRole("button", { name: "Open message 26 in chat" });
  fireEvent.click(button); fireEvent.click(button);
  type("Chat message", "Typed while opening"); type("Conversation title", "Renamed while opening");
  await act(async () => { pending.resolve(jsonResponse(siblingConversation)); });
  await screen.findByRole("heading", { name: "Located message 26 in conversation 92" });
  await open(1);
  expect(screen.getByLabelText("Chat message")).toHaveValue("Typed while opening");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Renamed while opening");
  expect(fetchMock.mock.calls.filter(([url]) => url === "/conversations/92?agent_id=7")).toHaveLength(1);
});

test.each(["close", "reload"])("a pending located-context download cannot finish after %s", async (change) => {
  const create = vi.fn().mockReturnValue("blob:stale-location");
  vi.stubGlobal("URL", class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn(); });
  const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { fetchMock } = await setup(); const region = await open(); type("Chat message", "Retain located draft");
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(within(region).getByRole("button", { name: "Export context JSON" }));
  const signal = fetchMock.mock.calls.at(-1)?.[1]?.signal;
  fireEvent.click(change === "close" ? within(region).getByRole("button", { name: "Close located message" }) :
    screen.getByRole("button", { name: "Reload messages" }));
  expect(signal?.aborted).toBe(true);
  await act(async () => { pending.resolve(contextExportResponse("json", {
    ...contextData(26, 3, 3, [siblingMessage]), conversation_id: 92 })); });
  expect(create).not.toHaveBeenCalled(); expect(clicked).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Conversation")).toHaveValue("92");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Retain located draft");
});

test.each(["query", "role", "size", "clear", "cancel", "selection", "reload", "delete", "agent", "unmount"])(
  "cancels pending navigation after %s without late selection or a message read", async (change) => {
    const view = await setup(true, true); const pending = deferredResponse();
    view.fetchMock.mockReturnValueOnce(pending.promise);
    fireEvent.click(screen.getByRole("button", { name: "Open message 26 in chat" }));
    const controllerSignal = view.fetchMock.mock.calls.at(-1)?.[1]?.signal;
    if (change === "query") type("Agent message content search", "new query");
    else if (change === "role") type("Agent message role", "assistant");
    else if (change === "size") type("Agent search results per page", "5");
    else if (change === "clear") fireEvent.click(screen.getByRole("button", { name: "Clear Agent message search" }));
    else if (change === "cancel") fireEvent.click(screen.getByRole("button", { name: "Cancel opening message" }));
    else if (change === "selection") type("Conversation", "92");
    else if (change === "reload") fireEvent.click(screen.getByRole("button", { name: "Reload messages" }));
    else if (change === "delete") fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
    else if (change === "agent") view.rerender(<ConversationPanel agentId={8} onActivity={view.onActivity} />);
    else view.unmount();
    expect(controllerSignal?.aborted).toBe(true);
    await act(async () => { pending.resolve(jsonResponse(siblingConversation)); });
    expect(screen.queryByRole("region", { name: "Located saved message in chat" })).not.toBeInTheDocument();
    if (!["agent", "unmount"].includes(change)) expect(screen.getByLabelText("Conversation")).toHaveValue(change === "selection" ? "92" : "91");
    expect(view.fetchMock.mock.calls.some(([url]) => url === "/conversations/92/messages/26?agent_id=7")).toBe(false);
    expect(view.onActivity).not.toHaveBeenCalled();
  });

test.each(["missing", "foreign", "network"])("keeps current chat/drafts after a %s navigation failure and retries explicitly", async (failure) => {
  const { fetchMock } = await setup(); type("Chat message", "Keep draft"); type("Conversation title", "Keep rename");
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(jsonResponse(failure === "missing" ? { detail: "Conversation not found" } :
    { ...siblingConversation, agent_id: 8 }, failure === "missing" ? 404 : 200));
  fireEvent.click(screen.getByRole("button", { name: "Open message 26 in chat" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Keep rename");
  expect(screen.getByRole("list", { name: "Agent message search results" })).toBeInTheDocument();
  await open(); expect(screen.getByLabelText("Conversation")).toHaveValue("92");
});

test("explicit navigation can be declined by a busy parent without changing search evidence", async () => {
  mockNavigationRequests(); const onOpenMessage = vi.fn().mockReturnValue(false);
  render(<AgentMessageSearch agentId={7} disabled={false} revision={0} onOpenMessage={onOpenMessage} />);
  type("Agent message content search", "中文");
  fireEvent.click(screen.getByRole("button", { name: "Search Agent messages" }));
  await screen.findByRole("list", { name: "Agent message search results" });
  fireEvent.click(screen.getByRole("button", { name: "Open message 26 in chat" }));
  await screen.findByText("Finish the current conversation action before opening another saved message.");
  expect(onOpenMessage).toHaveBeenCalledOnce();
});

test("switching Agent starts fresh drafts and cannot restore drafts from the previous Agent instance", async () => {
  const view = await setup(); type("Chat message", "Agent 7 draft");
  view.rerender(<ConversationPanel agentId={8} onActivity={view.onActivity} />);
  await screen.findByText("No conversations for this Agent.");
  view.rerender(<ConversationPanel agentId={7} onActivity={view.onActivity} />);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  type("Conversation", "91"); await screen.findByText("20 messages loaded. Earlier messages are available.");
  expect(screen.getByLabelText("Chat message")).toHaveValue("");
});

test("Strict Mode opens only once and retains the original latest page", async () => {
  const { fetchMock } = mockNavigationRequests();
  render(<StrictMode><ConversationPanel agentId={7} onActivity={vi.fn()} /></StrictMode>);
  await screen.findByRole("option", { name: `${exportConversation.title} (ID: 91)` });
  type("Agent message content search", "turn 1");
  fireEvent.click(screen.getByRole("button", { name: "Search Agent messages" }));
  await screen.findByRole("list", { name: "Agent message search results" });
  type("Agent search results per page", "50");
  fireEvent.click(screen.getByRole("button", { name: "Search Agent messages" }));
  await screen.findByRole("button", { name: "Open message 1 in chat" });
  await open(1);
  await screen.findByText("20 messages loaded. Earlier messages are available.");
  expect(fetchMock.mock.calls.filter(([url]) => url === "/conversations/91?agent_id=7")).toHaveLength(1);
  expect(within(screen.getByRole("region", { name: "Located saved message in chat" })).getAllByRole("listitem")).toHaveLength(4);
  expect(exportMessages).toHaveLength(25);
});
