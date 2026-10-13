import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { MemorySearchPanel } from "../src/components/MemorySearchPanel";
import { UserMemoryPanel } from "../src/components/UserMemoryPanel";
import { deferredResponse, jsonResponse } from "./taskFixtures";

afterEach(() => vi.unstubAllGlobals());
const memory = { id: 11, agent_id: 7, content: "I prefer concise answers.", created_at: "2026-10-09T08:00:00" };
const result = { agent_id: 7, query: "Keep it brief.", limit: 5, mode: "semantic", provider: "mock",
  model: "mock-fixtures-v1", runtime_mode: "keyword", min_similarity: 0.35,
  results: [{ memory, similarity: 0.96 }] };
function panel() {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<MemorySearchPanel agentId={7} revision="initial" disabled={false} />);
  return { fetchMock, ...view };
}
function semantic() {
  fireEvent.change(screen.getByLabelText("Memory search method"), { target: { value: "semantic" } });
  fireEvent.change(screen.getByLabelText("Memory search query"), { target: { value: "  Keep it brief.  " } });
}
function submit() { fireEvent.click(screen.getByRole("button", { name: "Search memories" })); }

test("keeps the keyword endpoint as default and makes no requests on method selection", async () => {
  const { fetchMock } = panel();
  expect(screen.getByLabelText("Memory search method")).toHaveValue("keyword");
  semantic();
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Memory search method"), { target: { value: "keyword" } });
  fetchMock.mockResolvedValueOnce(jsonResponse({ agent_id: 7, query: "Keep it brief.", limit: 5, results: [] }));
  submit();
  await screen.findByText("No relevant memories found.");
  expect(fetchMock).toHaveBeenLastCalledWith("/memories/7/search?query=Keep+it+brief.&limit=5", { cache: "no-store" });
});

test("shows cosine similarity and explicit Mock/provider metadata without keyword scores", async () => {
  const { fetchMock } = panel();
  fetchMock.mockResolvedValueOnce(jsonResponse(result));
  semantic(); submit();
  const list = await screen.findByRole("list", { name: "Memory search results" });
  expect(fetchMock).toHaveBeenLastCalledWith("/memories/7/semantic-search?query=Keep+it+brief.&limit=5", { cache: "no-store" });
  expect(list).toHaveTextContent("Cosine similarity: 0.960");
  expect(screen.getByText(/Mock fixture vectors/)).toHaveTextContent("Runtime memory mode: keyword");
  expect(screen.getByText(/Cosine similarity measures/)).toBeInTheDocument();
  expect(list).not.toHaveTextContent("Keyword matches");
  expect(list).not.toHaveTextContent("Matched text");
});

test("shows the configured local model for Ollama results", async () => {
  const { fetchMock } = panel();
  fetchMock.mockResolvedValueOnce(jsonResponse({ ...result, provider: "ollama", model: "embeddinggemma", runtime_mode: "semantic" }));
  semantic(); submit();
  expect(await screen.findByText(/Ollama semantic vectors/)).toHaveTextContent("Model: embeddinggemma · Runtime memory mode: semantic");
});

test.each(["mode", "query", "limit", "revision", "disabled"])("ignores late semantic results after %s changes", async kind => {
  const { fetchMock, rerender } = panel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  semantic(); submit();
  if (kind === "mode") fireEvent.change(screen.getByLabelText("Memory search method"), { target: { value: "keyword" } });
  if (kind === "query") fireEvent.change(screen.getByLabelText("Memory search query"), { target: { value: "Different query" } });
  if (kind === "limit") fireEvent.change(screen.getByLabelText("Result limit"), { target: { value: "1" } });
  if (kind === "revision") rerender(<MemorySearchPanel agentId={7} revision="edited" disabled={false} />);
  if (kind === "disabled") rerender(<MemorySearchPanel agentId={7} revision="initial" disabled />);
  await act(async () => pending.resolve(jsonResponse(result)));
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
});

test("locks repeated semantic submits while allowing an explicit retry after 503", async () => {
  const { fetchMock } = panel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  semantic();
  const form = screen.getByLabelText("Memory search query").closest("form")!;
  fireEvent.submit(form); fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async () => pending.resolve(jsonResponse({ detail: "Local embeddings unavailable" }, 503)));
  expect(await screen.findByRole("alert")).toHaveTextContent("Local embeddings unavailable");
  expect(screen.getByLabelText("Memory search query")).toHaveValue("  Keep it brief.  ");
  expect(screen.getByLabelText("Memory search method")).toHaveValue("semantic");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fetchMock.mockResolvedValueOnce(jsonResponse(result));
  submit(); await screen.findByRole("list", { name: "Memory search results" });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test.each([
  { ...result, agent_id: 8 }, { ...result, query: "Wrong" }, { ...result, mode: "keyword" },
  { ...result, provider: "openai" }, { ...result, model: "" }, { ...result, runtime_mode: "invalid" },
  { ...result, min_similarity: 2 },
  { ...result, results: [{ memory, similarity: NaN }] },
  { ...result, results: [{ memory, similarity: Infinity }] },
  { ...result, results: [{ memory, similarity: 1.01 }] },
  { ...result, results: [{ memory, similarity: 0.1 }] },
  { ...result, results: [{ memory: { ...memory, agent_id: 8 }, similarity: 0.96 }] },
  { ...result, results: [result.results[0], result.results[0]] },
  { ...result, results: [{ memory, similarity: 0.96 }, { memory: { ...memory, id: 12 }, similarity: 0.97 }] },
])("rejects invalid semantic result %j", async data => {
  const { fetchMock } = panel();
  fetchMock.mockResolvedValueOnce(jsonResponse(data));
  semantic(); submit();
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid semantic memory search data");
  expect(screen.queryByRole("list", { name: "Memory search results" })).not.toBeInTheDocument();
});

const sharedMemory = { id: 21, user_id: 3, content: memory.content, created_at: memory.created_at };
const sharedContext = { agent_id: 7, user_id: 3, username: "demo", memories: [sharedMemory] };
const sharedResult = { ...result, user_id: 3, results: [{ memory: sharedMemory, similarity: 0.96 }] };
async function sharedPanel() {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(sharedContext));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<UserMemoryPanel agentId={7} />);
  fireEvent.click(screen.getByRole("button", { name: "Show shared memories" }));
  await screen.findByText(sharedMemory.content);
  fireEvent.change(screen.getByLabelText("Shared memory search method"), { target: { value: "semantic" } });
  fireEvent.change(screen.getByLabelText("Shared memory search query"), { target: { value: result.query } });
  return { fetchMock, ...view };
}

test("shared semantic preview validates the owner and retains saved records", async () => {
  const { fetchMock } = await sharedPanel();
  fetchMock.mockResolvedValueOnce(jsonResponse(sharedResult));
  fireEvent.click(screen.getByRole("button", { name: "Search shared memories" }));
  const list = await screen.findByRole("list", { name: "Shared memory search results" });
  expect(list).toHaveTextContent("Shared memory 21 · Cosine similarity: 0.960");
  expect(within(screen.getByRole("list", { name: "Saved shared memories" })).getAllByRole("listitem")).toHaveLength(1);
  expect(fetchMock).toHaveBeenLastCalledWith("/user-memories/for-agent/7/semantic-search?query=Keep+it+brief.&limit=5", { cache: "no-store" });
});

test.each([
  { ...sharedResult, user_id: 4 },
  { ...sharedResult, results: [{ memory: { ...sharedMemory, user_id: 4 }, similarity: 0.96 }] },
])("rejects cross-owner shared semantic responses %j", async data => {
  const { fetchMock } = await sharedPanel();
  fetchMock.mockResolvedValueOnce(jsonResponse(data));
  fireEvent.click(screen.getByRole("button", { name: "Search shared memories" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid semantic memory search data");
  expect(screen.queryByRole("list", { name: "Shared memory search results" })).not.toBeInTheDocument();
});

test("changing the shared method invalidates an older result", async () => {
  const { fetchMock } = await sharedPanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise);
  fireEvent.click(screen.getByRole("button", { name: "Search shared memories" }));
  fireEvent.change(screen.getByLabelText("Shared memory search method"), { target: { value: "keyword" } });
  await act(async () => pending.resolve(jsonResponse(sharedResult)));
  expect(screen.queryByRole("list", { name: "Shared memory search results" })).not.toBeInTheDocument();
});

test("changing Agent during a shared semantic request resets the mode and ignores late errors", async () => {
  const { fetchMock, rerender } = await sharedPanel();
  const pending = deferredResponse();
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(jsonResponse({ agent_id: 8, user_id: 4, username: "other", memories: [] }));
  fireEvent.click(screen.getByRole("button", { name: "Search shared memories" }));
  rerender(<UserMemoryPanel agentId={8} />);
  await screen.findByText("No shared memories for this user.");
  await act(async () => pending.resolve(jsonResponse({ detail: "Late failure" }, 503)));
  expect(screen.getByLabelText("Shared memory search method")).toHaveValue("keyword");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
