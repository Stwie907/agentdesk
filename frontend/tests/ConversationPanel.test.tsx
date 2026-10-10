import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ConversationPanel } from "../src/components/ConversationPanel";
import type { Conversation, ConversationMessage } from "../src/types/conversations";
import { deferredResponse, jsonResponse } from "./taskFixtures";
import { conversationPageResponse } from "./conversationFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

const conversation: Conversation = { id: 91, agent_id: 7, title: "Memory demo", created_at: "2026-10-08T14:00:00" };
const user: ConversationMessage = { id: 1, conversation_id: 91, role: "user", content: "I like Python", created_at: "2026-10-08T14:00:00" };
const assistant: ConversationMessage = { ...user, id: 2, role: "assistant", content: "[MOCK] Fixed reply" };
const reply = { execution_id: 101, status: "completed", response: assistant.content };

async function activePanel() {
  const fetchMock = vi.fn().mockResolvedValueOnce(conversationPageResponse([conversation])).mockResolvedValueOnce(jsonResponse([]));
  const onActivity = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: "Memory demo (ID: 91)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("No messages in this conversation.");
  return { fetchMock, onActivity, ...view };
}

function draft(value = "I like Python") {
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value } });
}

test("does not load conversations before selecting an Agent", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<ConversationPanel agentId={null} onActivity={vi.fn()} />);
  expect(screen.getByText(/Select an Agent above to start/)).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("reloads a failed conversation list and keeps writes disabled until recovery", async () => {
  const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(conversationPageResponse([]));
  vi.stubGlobal("fetch", fetchMock);
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByRole("alert");
  expect(screen.getByLabelText("New conversation title")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload conversations" }));
  await screen.findByText("No conversations for this Agent.");
  expect(screen.getByLabelText("New conversation title")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Create conversation" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
});

test("creates a trimmed title once and selects the returned conversation", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn().mockResolvedValueOnce(conversationPageResponse([])).mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce(conversationPageResponse([conversation])).mockResolvedValueOnce(jsonResponse([]));
  vi.stubGlobal("fetch", fetchMock);
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByText("No conversations for this Agent.");
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "  Memory demo  " } });
  const form = screen.getByRole("button", { name: "Create conversation" }).closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenLastCalledWith("/conversations", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: 7, title: "Memory demo" }),
  });
  await act(async () => { pending.resolve(jsonResponse(conversation)); });
  await screen.findByText("No messages in this conversation.");
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("");
});

test("keeps the title on a failed create without automatic retries", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(conversationPageResponse([])).mockRejectedValueOnce(new TypeError("offline")));
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByText("No conversations for this Agent.");
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "Keep title" } });
  fireEvent.click(screen.getByRole("button", { name: "Create conversation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Reload conversations");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("Keep title");
  expect(fetch).toHaveBeenCalledTimes(2);
});

test("renders the ordered transcript as plain text", async () => {
  const content = '<img src="x" onerror="alert(1)">';
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(conversationPageResponse([conversation]))
    .mockResolvedValueOnce(jsonResponse([{ ...user, content }, assistant])));
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByRole("option", { name: "Memory demo (ID: 91)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  const transcript = await screen.findByRole("list", { name: "Conversation messages" });
  expect(within(transcript).getAllByRole("listitem")[0]).toHaveTextContent(content);
  expect(transcript.querySelector("img")).toBeNull();
});

test("sends trimmed chat in the selected scope once and reloads its transcript", async () => {
  const { fetchMock, onActivity } = await activePanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse([user, assistant]));
  draft("  I like Python  ");
  const form = screen.getByRole("button", { name: "Send message" }).closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(fetchMock).toHaveBeenLastCalledWith("/conversations/91/chat?agent_id=7", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: "I like Python" }),
  });
  expect(screen.getByLabelText("Conversation")).toBeDisabled();
  await act(async () => { pending.resolve(jsonResponse(reply)); });
  await screen.findByRole("list", { name: "Conversation messages" });
  expect(onActivity).toHaveBeenCalledExactlyOnceWith(7, 101);
  expect(screen.getByLabelText("Chat message")).toHaveValue("");
  expect(screen.getByText(assistant.content)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith("/conversations/91/messages?agent_id=7", { cache: "no-store" });
});

test.each(["network", "validation"])("keeps the draft after a %s send failure", async (kind) => {
  const { fetchMock, onActivity } = await activePanel();
  if (kind === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [] }, 422));
  draft();
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(kind === "network" ? "Reload messages" : "1 to 4000 characters");
  expect(screen.getByLabelText("Chat message")).toHaveValue("I like Python");
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(onActivity).not.toHaveBeenCalled();
});

test("retains the draft for a failed execution and still opens its inspection", async () => {
  const { fetchMock, onActivity } = await activePanel();
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...reply, status: "failed", response: "Tool failed" }))
    .mockResolvedValueOnce(jsonResponse([user, { ...assistant, content: "Tool failed" }]));
  draft();
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByText("Tool failed");
  expect(screen.getByLabelText("Chat message")).toHaveValue("I like Python");
  expect(screen.getByRole("status")).toHaveTextContent("Inspect the execution");
  expect(onActivity).toHaveBeenCalledExactlyOnceWith(7, 101);
});

test("a failed transcript reload after successful chat does not resend the message", async () => {
  const { fetchMock, onActivity } = await activePanel();
  fetchMock.mockResolvedValueOnce(jsonResponse(reply)).mockRejectedValueOnce(new TypeError("offline"))
    .mockResolvedValueOnce(jsonResponse([user, assistant]));
  draft();
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reload messages" }));
  await screen.findByRole("list", { name: "Conversation messages" });
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  expect(onActivity).toHaveBeenCalledTimes(1);
});

test("ignores a late transcript after selecting another conversation", async () => {
  const pending = deferredResponse();
  const other = { ...conversation, id: 92, title: "Other conversation" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(conversationPageResponse([conversation, other]))
    .mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse([{ ...user, conversation_id: 92, content: "Current transcript" }])));
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByRole("option", { name: "Other conversation (ID: 92)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "92" } });
  await screen.findByText("Current transcript");
  await act(async () => { pending.resolve(jsonResponse([user, assistant])); });
  expect(screen.queryByText(user.content)).not.toBeInTheDocument();
});

test("ignores a late conversation list after switching Agents", async () => {
  const pending = deferredResponse();
  vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValueOnce(conversationPageResponse([], { agent_id: 8 })));
  const { rerender } = render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  rerender(<ConversationPanel agentId={8} onActivity={vi.fn()} />);
  await screen.findByText("No conversations for this Agent.");
  await act(async () => { pending.resolve(conversationPageResponse([conversation])); });
  expect(screen.queryByRole("option", { name: "Memory demo (ID: 91)" })).not.toBeInTheDocument();
});

test("ignores a late create after switching Agents", async () => {
  const pending = deferredResponse();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(conversationPageResponse([])).mockReturnValueOnce(pending.promise)
    .mockResolvedValueOnce(conversationPageResponse([], { agent_id: 8 })));
  const { rerender } = render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByText("No conversations for this Agent.");
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "Old conversation" } });
  fireEvent.click(screen.getByRole("button", { name: "Create conversation" }));
  rerender(<ConversationPanel agentId={8} onActivity={vi.fn()} />);
  await screen.findByText("No conversations for this Agent.");
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "New draft" } });
  await act(async () => { pending.resolve(jsonResponse(conversation)); });
  expect(screen.getByLabelText("New conversation title")).toHaveValue("New draft");
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
});

test("ignores a late chat result after switching Agents", async () => {
  const { fetchMock, onActivity, rerender } = await activePanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(conversationPageResponse([], { agent_id: 8 }));
  draft();
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  rerender(<ConversationPanel agentId={8} onActivity={onActivity} />);
  await screen.findByText("No conversations for this Agent.");
  await act(async () => { pending.resolve(jsonResponse(reply)); });
  expect(onActivity).not.toHaveBeenCalled();
  expect(screen.queryByText(/Execution 101 returned/)).not.toBeInTheDocument();
});

test("rejects another Agent's conversation list", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(conversationPageResponse([{ ...conversation, agent_id: 8 }])));
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid conversation data for this Agent");
  expect(screen.queryByRole("option", { name: "Memory demo (ID: 91)" })).not.toBeInTheDocument();
});

test("rejects messages from another conversation and disables sending", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(conversationPageResponse([conversation]))
    .mockResolvedValueOnce(jsonResponse([{ ...user, conversation_id: 92 }])));
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByRole("option", { name: "Memory demo (ID: 91)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid messages for this conversation");
  expect(screen.queryByText(user.content)).not.toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toBeDisabled();
});
