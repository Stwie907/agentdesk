import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { MemoryPanel } from "../src/components/MemoryPanel";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => { vi.unstubAllGlobals(); });

const memory = { id: 11, agent_id: 7, content: "Python SQLite guide.", created_at: "2026-10-09T08:00:00" };
const match = { memory, score: 2, matched_terms: ["python", "sqlite"] };
const response = { agent_id: 7, query: "Python SQLite", limit: 5, results: [match] };

async function activePanel() {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([memory]));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<MemoryPanel agentId={7} />);
  await screen.findByRole("list", { name: "Saved memories" });
  return { fetchMock, ...view };
}

function draft(value = "Python SQLite") {
  fireEvent.change(screen.getByLabelText("Memory search query"), { target: { value } });
}

async function searchedPanel() {
  const view = await activePanel();
  view.fetchMock.mockResolvedValueOnce(jsonResponse(response));
  draft();
  fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  await screen.findByRole("list", { name: "Memory search results" });
  return view;
}

test("waits for an Agent and its memory list without automatically searching", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse([]));
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<MemoryPanel agentId={null} />);
  expect(screen.queryByLabelText("Memory search query")).not.toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  rerender(<MemoryPanel agentId={7} />);
  expect(screen.getByLabelText("Memory search query")).toBeDisabled();
  await screen.findByText("No saved memories for this Agent.");
  expect(screen.getByLabelText("Result limit")).toHaveValue("5");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("sends one scoped GET with encoded, trimmed query and displays ranking evidence", async () => {
  const { fetchMock } = await activePanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  draft("  Python SQLite  ");
  const form = screen.getByRole("button", { name: "Search memories" }).closest("form")!;
  fireEvent.submit(form); fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenLastCalledWith("/memories/7/search?query=Python+SQLite&limit=5", { cache: "no-store" });
  await act(async () => { pending.resolve(jsonResponse(response)); });
  const list = await screen.findByRole("list", { name: "Memory search results" });
  expect(list).toHaveTextContent("Keyword matches: 2");
  expect(list).toHaveTextContent("Matched text: python, sqlite");
  expect(within(list).getByText(memory.content)).toBeInTheDocument();
  expect(fetchMock.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});

test.each(["", " \n ", "x".repeat(501)])("rejects invalid search draft %j", async (query) => {
  const { fetchMock } = await activePanel();
  draft(query);
  expect(screen.getByLabelText("Memory search query")).toHaveAttribute("maxlength", "500");
  expect(screen.getByRole("button", { name: "Search memories" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("applies the selected limit to the preview only", async () => {
  const { fetchMock } = await activePanel();
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...response, limit: 1 }));
  draft();
  fireEvent.change(screen.getByLabelText("Result limit"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  await screen.findByRole("list", { name: "Memory search results" });
  expect(fetchMock).toHaveBeenLastCalledWith("/memories/7/search?query=Python+SQLite&limit=1", { cache: "no-store" });
});

test("displays an empty result without changing saved memories", async () => {
  const { fetchMock } = await activePanel();
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...response, results: [] }));
  draft(); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  await screen.findByText("No relevant memories found.");
  expect(within(screen.getByRole("list", { name: "Saved memories" })).getByText(memory.content)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test.each(["network", "validation"])("keeps the query after %s failure and retries only on click", async (kind) => {
  const { fetchMock } = await activePanel();
  if (kind === "network") fetchMock.mockRejectedValueOnce(new TypeError("offline"));
  else fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [] }, 422));
  draft(); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(kind === "network" ? "Unable to search memories" : "1 to 500 characters");
  expect(screen.getByLabelText("Memory search query")).toHaveValue(response.query);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  fetchMock.mockResolvedValueOnce(jsonResponse(response));
  fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  await screen.findByRole("list", { name: "Memory search results" });
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test.each(["agent", "query", "limit", "memory_agent", "score", "duplicates", "order"])("rejects invalid %s response data", async (kind) => {
  const { fetchMock } = await activePanel();
  const invalid = {
    ...response,
    ...(kind === "agent" ? { agent_id: 8 } : {}),
    ...(kind === "query" ? { query: "Other query" } : {}),
    ...(kind === "limit" ? { limit: 20 } : {}),
    ...(kind === "memory_agent" ? { results: [{ ...match, memory: { ...memory, agent_id: 8 } }] } : {}),
    ...(kind === "score" ? { results: [{ ...match, score: 0 }] } : {}),
    ...(kind === "duplicates" ? { results: [match, match] } : {}),
    ...(kind === "order" ? { results: [{ ...match, score: 1, matched_terms: ["python"] }, { ...match, memory: { ...memory, id: 12 } }] } : {}),
  };
  fetchMock.mockResolvedValueOnce(jsonResponse(invalid));
  draft(); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid memory");
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
});

test("ignores a late result after editing the query and submitting a new search", async () => {
  const { fetchMock } = await activePanel();
  const pending = deferredResponse();
  const rust = { ...memory, id: 12, content: "Rust current result." };
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse({ ...response, query: "Rust", results: [
    { memory: rust, score: 1, matched_terms: ["rust"] },
  ] }));
  draft(); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  draft("Rust"); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  await screen.findByText(rust.content);
  await act(async () => { pending.resolve(jsonResponse(response)); });
  const list = screen.getByRole("list", { name: "Memory search results" });
  expect(list).toHaveTextContent(rust.content);
  expect(within(list).queryByText(memory.content)).not.toBeInTheDocument();
});

test("clears preview after a manual save while keeping its query and limit", async () => {
  const { fetchMock } = await searchedPanel();
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...memory, id: 12, content: "Rust new memory." }));
  fireEvent.change(screen.getByLabelText("Memory content"), { target: { value: "Rust new memory." } });
  fireEvent.click(screen.getByRole("button", { name: "Save memory" }));
  await screen.findByText("Memory 12 saved.");
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Memory search query")).toHaveValue(response.query);
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test("clears preview after deletion without automatically searching again", async () => {
  const { fetchMock } = await searchedPanel();
  fetchMock.mockResolvedValueOnce(jsonResponse({ message: "Memory deleted successfully" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete memory 11" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
  await screen.findByText("No saved memories for this Agent.");
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Memory search query")).toHaveValue(response.query);
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test("ignores a search result after a chat-triggered memory refresh", async () => {
  const { fetchMock, rerender } = await activePanel();
  const pending = deferredResponse();
  const current = { ...memory, id: 12, content: "Extracted memory after chat." };
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse([memory, current]));
  draft(); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  rerender(<MemoryPanel agentId={7} refreshKey={1} />);
  await screen.findByText(current.content);
  await act(async () => { pending.resolve(jsonResponse(response)); });
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Memory search query")).toHaveValue(response.query);
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test("ignores a late search after switching Agents and resets the query", async () => {
  const { fetchMock, rerender } = await activePanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse([]));
  draft(); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  rerender(<MemoryPanel agentId={8} />);
  await screen.findByText("No saved memories for this Agent.");
  await act(async () => { pending.resolve(jsonResponse(response)); });
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Memory search query")).toHaveValue("");
});

test("renders matched memory content as plain text", async () => {
  const { fetchMock } = await activePanel();
  const content = '<img src="x" onerror="alert(1)"> Python';
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...response, results: [{ ...match, memory: { ...memory, content } }] }));
  draft(); fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  const list = await screen.findByRole("list", { name: "Memory search results" });
  expect(within(list).getByText(content)).toBeInTheDocument();
  expect(list.querySelector("img")).toBeNull();
});
