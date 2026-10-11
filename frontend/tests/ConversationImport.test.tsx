import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConversationPanel } from "../src/components/ConversationPanel";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { exportConversation as conversation, exportMessages as messages } from "./conversationExportFixtures";
import { importData, importFile, importResponse, importResult } from "./conversationImportFixtures";
import { deferredResponse } from "./taskFixtures";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function setup(importedPage?: Promise<Response>) {
  let saved = false;
  const onActivity = vi.fn();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost"); const agent = Number(url.searchParams.get("agent_id"));
    if (url.pathname === "/conversations/page") {
      const query = url.searchParams.get("query") ?? "";
      if (saved && importedPage) return importedPage;
      return conversationPageResponse(agent === 7 && !query ? (saved ? [importResult().conversation, conversation] : [conversation]) : [], { agent_id: agent, query });
    }
    if (url.pathname === "/conversations/91/messages/page") return conversationMessagePageResponse(messages.slice(-20), { has_more: true, next_before_id: 6 });
    if (url.pathname === "/conversations/import" && init?.method === "POST") { saved = true; return importResponse(); }
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: `${conversation.title} (ID: 91)` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText(messages[24].content.trim());
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Keep chat draft" } });
  return { ...view, fetchMock, onActivity };
}

async function choose(file = importFile()) {
  fireEvent.change(screen.getByLabelText("Conversation JSON backup"), { target: { files: [file] } });
  await screen.findByText("25 saved messages. Destination: Agent 7.");
}

test("previews without writes, requires confirmation, and preserves selection, history, and drafts after import", async () => {
  const { fetchMock, onActivity } = await setup();
  fireEvent.change(screen.getByLabelText("Conversation title"), { target: { value: "Rename draft" } });
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "Create draft" } });
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "Search draft" } });
  await choose(); expect(fetchMock).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "Confirm import as new conversation" }));
  await screen.findByText(/as conversation 92 with 25 saved messages/);
  await screen.findByRole("option", { name: `${conversation.title} (ID: 92)` });
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep chat draft");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Rename draft");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("Create draft");
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("Search draft");
  expect(screen.getByText("20 messages loaded. Earlier messages are available.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Confirm import as new conversation" })).toBeDisabled();
  expect(onActivity).not.toHaveBeenCalled();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
});

test("guards repeated submits and locks other writes while pending", async () => {
  const { fetchMock } = await setup(); await choose();
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  const form = screen.getByRole("form", { name: "Import conversation backup" });
  fireEvent.submit(form); fireEvent.submit(form);
  expect(screen.getByRole("button", { name: "Importing..." })).toBeDisabled();
  for (const name of ["Create conversation", "Rename conversation", "Delete conversation", "Send message", "Export JSON", "Export Markdown"]) {
    expect(screen.getByRole("button", { name })).toBeDisabled();
  }
  expect(fetchMock).toHaveBeenCalledTimes(3);
  await act(async () => { pending.resolve(importResponse()); });
  await screen.findByText(/as conversation 92 with 25 saved messages/);
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep chat draft");
});

test.each(["422", "network"])("keeps the file and all drafts after %s failure and retries only on confirmation", async (failure) => {
  const { fetchMock } = await setup(); await choose();
  if (failure === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(importResponse({ detail: "Invalid backup" }, 422));
  fireEvent.click(screen.getByRole("button", { name: "Confirm import as new conversation" }));
  await screen.findByRole("alert");
  expect(screen.getByText("25 saved messages. Destination: Agent 7.")).toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep chat draft");
  expect(fetchMock).toHaveBeenCalledTimes(3);
  fireEvent.click(screen.getByRole("button", { name: "Confirm import as new conversation" }));
  await screen.findByText(/as conversation 92 with 25 saved messages/);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(["agent", "unmount"])("ignores late successful imports after %s changes", async (change) => {
  const { fetchMock, rerender, unmount, onActivity } = await setup(); await choose();
  const pending = deferredResponse(); fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Confirm import as new conversation" }));
  if (change === "agent") rerender(<ConversationPanel agentId={8} onActivity={onActivity} />);
  else unmount();
  await act(async () => { pending.resolve(importResponse()); });
  expect(screen.queryByText(/as conversation 92 with 25 saved messages/)).not.toBeInTheDocument();
  expect(onActivity).not.toHaveBeenCalled();
});

test("new file selection and clearing discard late file reads without HTTP requests", async () => {
  const { fetchMock } = await setup();
  let resolve: (value: ArrayBuffer) => void = () => {};
  const bytes = new Promise<ArrayBuffer>((done) => { resolve = done; });
  const slow = new File(["slow"], "slow.json"); Object.defineProperty(slow, "arrayBuffer", { value: () => bytes });
  fireEvent.change(screen.getByLabelText("Conversation JSON backup"), { target: { files: [slow] } });
  expect(screen.getByText("Reading backup...")).toBeInTheDocument();
  const next = importData(); next.conversation.title = "Latest backup";
  fireEvent.change(screen.getByLabelText("Conversation JSON backup"), { target: { files: [importFile(JSON.stringify(next))] } });
  await screen.findByText("Backup title: Latest backup");
  await act(async () => { resolve(new TextEncoder().encode(JSON.stringify(importData())).buffer); });
  expect(screen.getByText("Backup title: Latest backup")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear import file" }));
  expect(screen.getByRole("button", { name: "Confirm import as new conversation" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("invalid files cannot be submitted and delete confirmation locks import", async () => {
  const { fetchMock } = await setup();
  fireEvent.change(screen.getByLabelText("Conversation JSON backup"), { target: { files: [importFile("# Markdown")] } });
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Confirm import as new conversation" })).toBeDisabled();
  await choose(); fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  expect(screen.getByLabelText("Conversation JSON backup")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Confirm import as new conversation" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("import refreshes active title filters and preserves off-page selection after a delayed page response", async () => {
  const refreshedPage = deferredResponse();
  const { fetchMock } = await setup(refreshedPage.promise);
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "No matches" } });
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await screen.findByText("Your current conversation is outside these results. Its messages and unsent draft stay selected.");
  await choose();
  const requestsBeforeImport = fetchMock.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Confirm import as new conversation" }));
  await screen.findByText(/as conversation 92 with 25 saved messages/);
  await waitFor(() => {
    const refreshRequests = fetchMock.mock.calls.slice(requestsBeforeImport).filter(([input]) =>
      new URL(String(input), "http://localhost").pathname === "/conversations/page");
    expect(refreshRequests).toHaveLength(1);
    const url = new URL(String(refreshRequests[0][0]), "http://localhost");
    expect(url.searchParams.get("agent_id")).toBe("7");
    expect(url.searchParams.get("query")).toBe("No matches");
  });
  expect(screen.getByRole("button", { name: "Search conversations" })).toBeDisabled();
  await act(async () => {
    refreshedPage.resolve(conversationPageResponse([], { agent_id: 7, query: "No matches" }));
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "Search conversations" })).toBeEnabled());
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("No matches");
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep chat draft");
  expect(screen.getByText("20 messages loaded. Earlier messages are available.")).toBeInTheDocument();
  expect(screen.getByText("Your current conversation is outside these results. Its messages and unsent draft stay selected.")).toBeInTheDocument();
});
