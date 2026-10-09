import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ConversationPanel } from "../src/components/ConversationPanel";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

const conversation = { id: 91, agent_id: 7, title: "Memory demo", created_at: "2026-10-08T14:00:00" };
const other = { ...conversation, id: 92, title: "Keep this chat" };
const messages = [
  { id: 1, conversation_id: 91, role: "user", content: "Saved user turn", created_at: conversation.created_at },
  { id: 2, conversation_id: 91, role: "assistant", content: "Saved answer", created_at: conversation.created_at },
];

async function activePanel() {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([conversation, other]))
    .mockResolvedValueOnce(jsonResponse(messages));
  vi.stubGlobal("fetch", fetchMock);
  const onActivity = vi.fn();
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  await screen.findByRole("option", { name: "Memory demo (ID: 91)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  await screen.findByText("Saved answer");
  return { fetchMock, onActivity, ...view };
}

function renameDraft(value = "  Renamed demo  ") {
  fireEvent.change(screen.getByLabelText("Conversation title"), { target: { value } });
}

test("renames once with a trimmed title and retains selection, messages, and chat draft", async () => {
  const { fetchMock, onActivity } = await activePanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Memory demo");
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Keep draft" } });
  renameDraft();
  const form = screen.getByRole("button", { name: "Rename conversation" }).closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(fetchMock).toHaveBeenLastCalledWith("/conversations/91?agent_id=7", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: "Renamed demo" }),
  });
  expect(screen.getByLabelText("Conversation")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Delete conversation" })).toBeDisabled();
  await act(async () => { pending.resolve(jsonResponse({ ...conversation, title: "Renamed demo" })); });
  await screen.findByRole("option", { name: "Renamed demo (ID: 91)" });
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Renamed demo");
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep draft");
  expect(screen.getByText("Saved answer")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(onActivity).not.toHaveBeenCalled();
});

test.each(["", "  ", "x".repeat(201), "  Memory demo  "])("disables invalid or unchanged rename draft %j", async (title) => {
  const { fetchMock } = await activePanel();
  renameDraft(title);
  expect(screen.getByRole("button", { name: "Rename conversation" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test.each(["network", "validation", "missing", "wrong_id", "wrong_agent"])("keeps the rename draft and transcript after %s failure", async (kind) => {
  const { fetchMock } = await activePanel();
  if (kind === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else if (kind === "validation") fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [] }, 422));
  else if (kind === "missing") fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Conversation not found" }, 404));
  else fetchMock.mockResolvedValueOnce(jsonResponse({ ...conversation, title: "Wrong response",
    ...(kind === "wrong_id" ? { id: 92 } : { agent_id: 8 }) }));
  renameDraft();
  fireEvent.click(screen.getByRole("button", { name: "Rename conversation" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(kind === "validation" ? "1 to 200 characters" : "Reload conversations");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("  Renamed demo  ");
  expect(screen.getByRole("option", { name: "Memory demo (ID: 91)" })).toBeInTheDocument();
  expect(screen.getByText("Saved answer")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test("cancels deletion without issuing a request or changing the transcript", async () => {
  const { fetchMock } = await activePanel();
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  const group = screen.getByRole("group", { name: /Delete.*Memory demo/ });
  expect(group).toHaveTextContent("Agent memories and execution history will stay available");
  expect(screen.getByLabelText("Conversation")).toBeDisabled();
  fireEvent.click(within(group).getByRole("button", { name: "Cancel delete" }));
  expect(screen.queryByRole("button", { name: "Confirm delete" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByText("Saved answer")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("confirms deletion once, clears the transcript and draft, and retains other conversations", async () => {
  const { fetchMock, onActivity } = await activePanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Old draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  fireEvent.click(screen.getByRole("button", { name: "Deleting..." }));
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(fetchMock).toHaveBeenLastCalledWith("/conversations/91?agent_id=7", { method: "DELETE" });
  expect(screen.getByLabelText("Chat message")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel delete" })).toBeDisabled();
  await act(async () => { pending.resolve(jsonResponse({ message: "deleted" })); });
  await screen.findByText(/Conversation 91 deleted/);
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
  expect(screen.getByLabelText("Chat message")).toHaveValue("");
  expect(screen.queryByRole("option", { name: "Memory demo (ID: 91)" })).not.toBeInTheDocument();
  expect(screen.queryByText("Saved answer")).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Keep this chat (ID: 92)" })).toBeInTheDocument();
  expect(onActivity).not.toHaveBeenCalled();
});

test.each(["network", "missing", "invalid_reply"])("preserves selection after %s delete failure and recovers by reloading", async (kind) => {
  const { fetchMock } = await activePanel();
  if (kind === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(jsonResponse(kind === "missing" ? { detail: "Conversation not found" } : {}, kind === "missing" ? 404 : 200));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Reload conversations");
  expect(screen.getByLabelText("Conversation")).toHaveValue("91");
  expect(screen.getByText("Saved answer")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  fetchMock.mockResolvedValueOnce(jsonResponse([other]));
  fireEvent.click(screen.getByRole("button", { name: "Reload conversations" }));
  await screen.findByText("Create or select a conversation to send a message.");
  expect(screen.queryByText("Saved answer")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "DELETE")).toHaveLength(1);
});

test.each(["rename", "delete"])("ignores a late %s result after switching Agents", async (action) => {
  const { fetchMock, onActivity, rerender } = await activePanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse([]));
  if (action === "rename") {
    renameDraft(); fireEvent.click(screen.getByRole("button", { name: "Rename conversation" }));
  } else {
    fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  }
  rerender(<ConversationPanel agentId={8} onActivity={onActivity} />);
  await screen.findByText("No conversations for this Agent.");
  await act(async () => { pending.resolve(jsonResponse(action === "rename" ? { ...conversation, title: "Renamed demo" } : { message: "deleted" })); });
  expect(screen.queryByText(/Conversation 91 (renamed|deleted)/)).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Renamed demo (ID: 91)" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
  expect(onActivity).not.toHaveBeenCalled();
});

test("ignores a late transcript after its conversation is deleted", async () => {
  const pending = deferredResponse();
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([conversation]))
    .mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse({ message: "deleted" }));
  vi.stubGlobal("fetch", fetchMock);
  render(<ConversationPanel agentId={7} onActivity={vi.fn()} />);
  await screen.findByRole("option", { name: "Memory demo (ID: 91)" });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: "91" } });
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  await screen.findByText(/Conversation 91 deleted/);
  await act(async () => { pending.resolve(jsonResponse(messages)); });
  expect(screen.queryByText("Saved answer")).not.toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Conversation messages" })).not.toBeInTheDocument();
});
