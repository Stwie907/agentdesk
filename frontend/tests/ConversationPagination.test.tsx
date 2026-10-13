import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ConversationPanel } from "../src/components/ConversationPanel";
import type { Conversation } from "../src/types/conversations";
import { conversationMessagePageResponse, conversationPageResponse } from "./conversationFixtures";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

function conversation(id: number, title = `Chat ${id}`): Conversation {
  return { id, agent_id: 7, title, created_at: "2026-10-10T06:00:00" };
}
const rows = Array.from({ length: 13 }, (_, index) => conversation(13 - index));

function setup(initialRows = rows) {
  let saved = [...initialRows];
  const onActivity = vi.fn();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/conversations/page") {
      const query = url.searchParams.get("query") ?? "";
      const limit = Number(url.searchParams.get("limit"));
      const offset = Number(url.searchParams.get("offset"));
      const filtered = saved.filter((row) => row.title.toLowerCase().includes(query.toLowerCase()));
      return conversationPageResponse(filtered.slice(offset, offset + limit), { query, limit, offset, total: filtered.length });
    }
    if (url.pathname.endsWith("/messages/page")) {
      return conversationMessagePageResponse([{ id: 100, conversation_id: Number(url.pathname.split("/")[2]), role: "user",
        content: "Saved transcript", created_at: rows[0].created_at }]);
    }
    if (url.pathname === "/conversations" && init?.method === "POST") {
      const created = conversation(99, JSON.parse(String(init.body)).title);
      saved = [created, ...saved];
      return jsonResponse(created);
    }
    const id = Number(url.pathname.split("/")[2]);
    const current = saved.find((row) => row.id === id);
    if (!current) return jsonResponse({ detail: "Conversation not found" }, 404);
    if (init?.method === "PATCH") {
      const renamed = { ...current, title: JSON.parse(String(init.body)).title };
      saved = saved.map((row) => row.id === id ? renamed : row);
      return jsonResponse(renamed);
    }
    if (init?.method === "DELETE") {
      saved = saved.filter((row) => row.id !== id);
      return jsonResponse({ message: "deleted" });
    }
    return jsonResponse(current);
  });
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<ConversationPanel agentId={7} onActivity={onActivity} />);
  return { fetchMock, onActivity, ...view };
}

async function select(id = 13) {
  await screen.findByRole("option", { name: `Chat ${id} (ID: ${id})` });
  fireEvent.change(screen.getByLabelText("Conversation"), { target: { value: String(id) } });
  await screen.findByText("Saved transcript");
}

function search(query: string) {
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: query } });
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
}

test("requests bounded pages and navigates with correct counts and boundaries", async () => {
  const { fetchMock } = setup();
  await screen.findByText("Showing 1–10 of 13 conversations.");
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/conversations/page?agent_id=7&limit=10&offset=0", { cache: "no-store" });
  expect(screen.getByRole("button", { name: "Previous conversations" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Next conversations" }));
  await screen.findByText("Showing 11–13 of 13 conversations.");
  expect(screen.queryByRole("option", { name: "Chat 13 (ID: 13)" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next conversations" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Previous conversations" }));
  await screen.findByText("Showing 1–10 of 13 conversations.");
});

test("keeps the active transcript and all drafts when paging and searching other titles", async () => {
  const { fetchMock } = setup();
  await select();
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Unsent chat" } });
  fireEvent.change(screen.getByLabelText("Conversation title"), { target: { value: "Rename draft" } });
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "New chat draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Next conversations" }));
  await screen.findByText(/Your current conversation is outside these results/);
  search("no match");
  await screen.findByText("No conversations match this title search.");
  expect(screen.getByLabelText("Conversation")).toHaveValue("13");
  expect(screen.getByText("Saved transcript")).toBeInTheDocument();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Unsent chat");
  expect(screen.getByLabelText("Conversation title")).toHaveValue("Rename draft");
  expect(screen.getByLabelText("New conversation title")).toHaveValue("New chat draft");
  expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
  expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/messages"))).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Clear conversation search" }));
  await screen.findByText("Showing 1–10 of 13 conversations.");
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("");
});

test("submits a trimmed and encoded search explicitly and treats a blank draft as all titles", async () => {
  const { fetchMock } = setup();
  await screen.findByText("Showing 1–10 of 13 conversations.");
  fireEvent.change(screen.getByLabelText("Conversation title search"), { target: { value: "  中文 & 100%_  " } });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Search conversations" }));
  await screen.findByText("No conversations match this title search.");
  const url = new URL(String(fetchMock.mock.calls[1][0]), "http://localhost");
  expect(url.searchParams.get("query")).toBe("中文 & 100%_");
  expect(url.searchParams.get("offset")).toBe("0");
  search("   ");
  await screen.findByText("Showing 1–10 of 13 conversations.");
});

test("changing page size resets the offset and preserves the selected chat", async () => {
  setup();
  await select();
  fireEvent.click(screen.getByRole("button", { name: "Next conversations" }));
  await screen.findByText("Showing 11–13 of 13 conversations.");
  fireEvent.change(screen.getByLabelText("Conversations per page"), { target: { value: "5" } });
  await screen.findByText("Showing 1–5 of 13 conversations.");
  expect(screen.getByLabelText("Conversation")).toHaveValue("13");
  expect(screen.getByText("Saved transcript")).toBeInTheDocument();
});

test("a failed page keeps the draft, blocks writes, and recovers only on explicit reload", async () => {
  const { fetchMock } = setup();
  await select();
  fireEvent.change(screen.getByLabelText("Chat message"), { target: { value: "Keep this draft" } });
  fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  fireEvent.click(screen.getByRole("button", { name: "Next conversations" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  expect(screen.getByLabelText("Chat message")).toHaveValue("Keep this draft");
  const count = fetchMock.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Reload conversations" }));
  await screen.findByText("Showing 11–13 of 13 conversations.");
  expect(fetchMock.mock.calls.length).toBe(count + 2);
  expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
});

test("renaming outside the active search refreshes results while keeping the selected chat", async () => {
  const { onActivity } = setup();
  await select();
  search("Chat 13");
  await screen.findByText(/Showing 1–1 of 1 conversations/);
  fireEvent.change(screen.getByLabelText("Conversation title"), { target: { value: "Renamed topic" } });
  fireEvent.click(screen.getByRole("button", { name: "Rename conversation" }));
  await screen.findByText("No conversations match this title search.");
  expect(screen.getByRole("option", { name: "Renamed topic (ID: 13)" })).toBeInTheDocument();
  expect(screen.getByLabelText("Conversation")).toHaveValue("13");
  expect(screen.getByText("Saved transcript")).toBeInTheDocument();
  expect(onActivity).not.toHaveBeenCalled();
});

test("deleting the last conversation on a page moves back and fills the preceding page", async () => {
  const { fetchMock } = setup(rows.slice(2));
  await screen.findByText("Showing 1–10 of 11 conversations.");
  fireEvent.click(screen.getByRole("button", { name: "Next conversations" }));
  await screen.findByText("Showing 11–11 of 11 conversations.");
  await select(1);
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  await screen.findByText("Showing 1–10 of 10 conversations.");
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
  expect(screen.queryByText("Saved transcript")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next conversations" })).toBeDisabled();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "DELETE")).toHaveLength(1);
});

test("creating a conversation clears the applied search and selects it on the first page", async () => {
  setup();
  await screen.findByText("Showing 1–10 of 13 conversations.");
  search("no match");
  await screen.findByText("No conversations match this title search.");
  fireEvent.change(screen.getByLabelText("New conversation title"), { target: { value: "  New topic  " } });
  fireEvent.click(screen.getByRole("button", { name: "Create conversation" }));
  await screen.findByText("Showing 1–10 of 14 conversations.");
  expect(screen.getByLabelText("Conversation")).toHaveValue("99");
  expect(screen.getByRole("option", { name: "New topic (ID: 99)" })).toBeInTheDocument();
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("");
});

test("reload clears an off-page selection only after a scoped 404", async () => {
  const { fetchMock } = setup();
  await select();
  fireEvent.click(screen.getByRole("button", { name: "Next conversations" }));
  await screen.findByText("Showing 11–13 of 13 conversations.");
  fetchMock.mockResolvedValueOnce(conversationPageResponse(rows.slice(10), { offset: 10, total: 13 }))
    .mockResolvedValueOnce(jsonResponse({ detail: "Conversation not found" }, 404));
  fireEvent.click(screen.getByRole("button", { name: "Reload conversations" }));
  await screen.findByText("The selected conversation was removed. Choose another conversation.");
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
  expect(screen.queryByText("Saved transcript")).not.toBeInTheDocument();
});

test("ignores a late page when the selected Agent changes and resets the search draft", async () => {
  const { fetchMock, rerender, onActivity } = setup();
  await screen.findByText("Showing 1–10 of 13 conversations.");
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(conversationPageResponse([], { agent_id: 8 }));
  search("old search");
  rerender(<ConversationPanel agentId={8} onActivity={onActivity} />);
  await screen.findByText("No conversations for this Agent.");
  await act(async () => { pending.resolve(conversationPageResponse([], { query: "old search" })); });
  expect(screen.getByLabelText("Conversation title search")).toHaveValue("");
  expect(screen.queryByText(/Title contains/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
});

test("locks browsing while deletion is awaiting confirmation", async () => {
  setup();
  await select();
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  for (const name of ["Search conversations", "Next conversations", "Reload conversations"]) {
    expect(screen.getByRole("button", { name })).toBeDisabled();
  }
  expect(screen.getByLabelText("Conversations per page")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel delete" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Next conversations" })).toBeEnabled());
});

test("an emptied result set resets an old page offset and clears a removed selection on reload", async () => {
  const { fetchMock } = setup();
  await select();
  fireEvent.click(screen.getByRole("button", { name: "Next conversations" }));
  await screen.findByText("Showing 11–13 of 13 conversations.");
  fetchMock.mockResolvedValueOnce(conversationPageResponse([], { offset: 10 }))
    .mockResolvedValueOnce(conversationPageResponse([]))
    .mockResolvedValueOnce(jsonResponse({ detail: "Conversation not found" }, 404));
  fireEvent.click(screen.getByRole("button", { name: "Reload conversations" }));
  await screen.findByText("Showing 0–0 of 0 conversations.");
  expect(screen.getByRole("button", { name: "Previous conversations" })).toBeDisabled();
  expect(screen.getByLabelText("Conversation")).toHaveValue("");
});
