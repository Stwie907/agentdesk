import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MemoryRetrievalPanel } from "../src/components/MemoryRetrievalPanel";
import { ExecutionInspector } from "../src/components/ExecutionInspector";
import { fixture, response } from "./memoryEvidenceFixtures";

afterEach(() => vi.unstubAllGlobals());

test("loads evidence only when requested and shows captured facts", async () => {
  const fetchMock = vi.fn(async () => response(fixture())); vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" />);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  expect(await screen.findByText("Memory #7")).toBeInTheDocument();
  const privateSection = screen.getByRole("region", { name: "Agent memories" });
  expect(within(privateSection).getByText("Python original.")).toBeInTheDocument();
  expect(screen.getByText("Keyword score: 1; matched terms: python")).toBeInTheDocument();
  expect(screen.getByText(/Later memory edits or deletions do not change/)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("shows semantic fixture scores and warns that they are fixed test vectors", async () => {
  const body = fixture(); const facts = body.evidence!;
  Object.assign(facts, { requested_mode: "semantic", mode: "semantic", provider: "mock", model: "mock-fixtures-v1", min_similarity: 0.35 });
  Object.assign(facts.agent_memories[0], { score: null, matched_terms: [], similarity: 0.96 });
  vi.stubGlobal("fetch", vi.fn(async () => response(body)));
  render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  expect(await screen.findByText("Cosine similarity: 0.960000")).toBeInTheDocument();
  expect(screen.getByText("Mock similarity uses fixed test vectors.")).toBeInTheDocument();
});

test("shows the actual fallback reason without claiming semantic scores", async () => {
  const body = fixture(); body.evidence!.requested_mode = "semantic";
  body.evidence!.fallback_reason = "Local embedding model unavailable";
  vi.stubGlobal("fetch", vi.fn(async () => response(body)));
  render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Keyword fallback: Local embedding model unavailable");
  expect(screen.queryByText(/Cosine similarity:/)).not.toBeInTheDocument();
});

test("distinguishes a recorded empty context from unavailable evidence", async () => {
  const body = fixture(); body.evidence!.agent_memories = []; body.evidence!.context = "";
  const fetchMock = vi.fn().mockResolvedValueOnce(response(body))
    .mockResolvedValueOnce(response({ execution_id: 42, available: false, evidence: null }));
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  expect(await screen.findByText("No memories were loaded.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Refresh memory retrieval" }));
  expect(await screen.findByText(/No memory retrieval evidence was recorded/)).toBeInTheDocument();
  expect(screen.queryByText("No memories were loaded.")).not.toBeInTheDocument();
});

test("reports API errors and lets the user retry", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ detail: "Evidence is invalid" }, 409))
    .mockResolvedValueOnce(response(fixture())));
  render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Evidence is invalid");
  fireEvent.click(screen.getByRole("button", { name: "Refresh memory retrieval" }));
  expect(await screen.findByText("Memory #7")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("ignores late evidence after switching the execution and avoids duplicate requests", async () => {
  let resolve!: (value: Response) => void;
  const old = new Promise<Response>(done => { resolve = done; });
  const fetchMock = vi.fn().mockReturnValueOnce(old)
    .mockResolvedValueOnce(response({ execution_id: 43, available: false, evidence: null }));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  const loading = screen.getByRole("button", { name: "Loading memory retrieval..." });
  fireEvent.click(loading); expect(fetchMock).toHaveBeenCalledTimes(1);
  view.rerender(<MemoryRetrievalPanel executionId={43} agentId={2} input="Rust" />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  expect(await screen.findByText(/No memory retrieval evidence was recorded/)).toBeInTheDocument();
  await act(async () => { resolve(response(fixture())); await old; });
  expect(screen.queryByText("Memory #7")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith("/executions/43/memory-context?agent_id=2", { cache: "no-store" });
});

test("escapes captured text and preserves line breaks", async () => {
  const body = fixture(); const text = "Python <script>alert(1)</script>\nSecond line";
  body.evidence!.agent_memories[0].content = text; body.evidence!.context = text;
  vi.stubGlobal("fetch", vi.fn(async () => response(body)));
  const view = render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  await screen.findByText("Memory #7");
  expect(view.container.querySelector("script")).toBeNull();
  expect(view.container.querySelector("pre")?.textContent).toBe(text);
});

test("integrates with Inspector without adding automatic inspection requests", async () => {
  const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path.includes("memory-context")) return response(fixture());
    if (path.endsWith("/snapshot")) return response({ detail: "No snapshot" }, 404);
    if (path.endsWith("/trace") || path.endsWith("/replays")) return response([]);
    return response({ id: 42, agent_id: 1, input: "Python", output: "[MOCK]", status: "completed",
      retry_count: 0, failure_type: null, failure_message: null, replay_of_execution_id: null, created_at: "2026-10-09T10:00:00" });
  }); vi.stubGlobal("fetch", fetchMock);
  render(<ExecutionInspector selectedExecutionId={42} />);
  const button = await screen.findByRole("button", { name: "Show memory retrieval" });
  expect(fetchMock).toHaveBeenCalledTimes(4);
  fireEvent.click(button);
  expect(await screen.findByText("Memory #7")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(5);
});
