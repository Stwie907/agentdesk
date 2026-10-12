import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ExecutionInspector } from "../src/components/ExecutionInspector";
import { MemoryRetrievalPanel } from "../src/components/MemoryRetrievalPanel";
import { HomePage } from "../src/pages/HomePage";
import * as reports from "../src/utils/executionReport";
import { reportFixture } from "./executionReportFixtures";
import { fixture, response } from "./memoryEvidenceFixtures";
import { deferredResponse, jsonResponse, testAgent } from "./taskFixtures";
import { mockDraftRequests, mainConversation } from "./draftPersistenceFixtures";

let files: ReturnType<typeof reports.createExecutionReport>[];
beforeEach(() => {
  files = [];
  vi.spyOn(reports, "downloadExecutionReport").mockImplementation((file) => { files.push(file); });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function inspection(id = 42, agentId = 1, input = "Python") {
  const data = reportFixture(id);
  Object.assign(data.execution, { agent_id: agentId, input, status: "completed" });
  data.snapshot!.input_snapshot = input;
  data.replays = [];
  return data;
}

function mockReads(memory: (id: number) => Promise<Response> = async () => response(fixture())) {
  const data = new Map([[42, inspection()], [43, inspection(43, 2, "Rust")]]);
  const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
    const path = new URL(String(url), "http://localhost").pathname;
    const match = /^\/executions\/(\d+)(?:\/(trace|snapshot|replays|memory-context))?$/.exec(path);
    if (!match) throw new Error(`Unexpected read ${path}`);
    const id = Number(match[1]), row = data.get(id)!;
    if (match[2] === "memory-context") return memory(id);
    return response(match[2] ? row[match[2] as "trace" | "snapshot" | "replays"] : row.execution);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { data, fetchMock };
}

function exportJson() {
  fireEvent.click(within(screen.getByRole("region", { name: "Export execution report" })).getByRole("button", { name: "Export JSON" }));
  return JSON.parse(files.at(-1)!.content);
}

test("inspection and exports never automatically read memory evidence", async () => {
  const { fetchMock } = mockReads(); render(<ExecutionInspector selectedExecutionId={42} />);
  await screen.findByRole("button", { name: "Export JSON" });
  expect(exportJson().memory_retrieval.status).toBe("not_loaded");
  fireEvent.click(within(screen.getByRole("region", { name: "Export execution report" })).getByRole("button", { name: "Export Markdown" }));
  expect(files[1].content).toContain('"status": "not_loaded"');
  expect(fetchMock).toHaveBeenCalledTimes(4);
});

test("explicitly loaded captured evidence is included without extra export reads", async () => {
  const { fetchMock } = mockReads(); render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  await screen.findByText("Memory #7");
  expect(exportJson().memory_retrieval).toMatchObject({ status: "loaded", evidence: fixture().evidence });
  fireEvent.click(within(screen.getByRole("region", { name: "Export execution report" })).getByRole("button", { name: "Export Markdown" }));
  expect(files.at(-1)!.content).toContain("Python original.");
  expect(fetchMock).toHaveBeenCalledTimes(5);
  expect(screen.getByText(/Memory evidence: Included/)).toBeInTheDocument();
});

test("an unavailable saved context remains exportable with an explicit state", async () => {
  mockReads(async () => response({ execution_id: 42, available: false, evidence: null }));
  render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  await screen.findByText(/No memory retrieval evidence was recorded/);
  expect(exportJson().memory_retrieval).toMatchObject({ status: "unavailable", evidence: null });
});

test("failed reads do not export private errors and can be retried", async () => {
  let fail = true;
  const { fetchMock } = mockReads(async () => fail ? response({ detail: "private upstream detail" }, 503) : response(fixture()));
  render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  await screen.findByRole("alert");
  expect(exportJson().memory_retrieval).toMatchObject({ status: "failed", evidence: null });
  expect(files.at(-1)!.content).not.toContain("private upstream detail");
  fail = false; fireEvent.click(screen.getByRole("button", { name: "Refresh memory retrieval" }));
  await screen.findByText("Memory #7");
  expect(exportJson().memory_retrieval.status).toBe("loaded");
  expect(fetchMock).toHaveBeenCalledTimes(6);
});

test("exports during a pending read record loading rather than old captured content", async () => {
  const pending = deferredResponse(); let wait = false;
  const { fetchMock } = mockReads(async () => wait ? pending.promise : response(fixture()));
  render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  await screen.findByText("Memory #7"); wait = true;
  fireEvent.click(screen.getByRole("button", { name: "Refresh memory retrieval" }));
  expect(exportJson().memory_retrieval).toMatchObject({ status: "loading", evidence: null });
  expect(files.at(-1)!.content).not.toContain("Python original.");
  await act(async () => pending.resolve(response(fixture())));
  await screen.findByText("Memory #7");
  expect(exportJson().memory_retrieval.status).toBe("loaded");
  expect(fetchMock).toHaveBeenCalledTimes(6);
});

test.each(["success", "error"])("late memory %s cannot contaminate another execution's export", async (outcome) => {
  const pending = deferredResponse();
  mockReads(async (id) => id === 42 ? pending.promise : response({ execution_id: 43, available: false, evidence: null }));
  const view = render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  view.rerender(<ExecutionInspector selectedExecutionId={43} />);
  await screen.findByRole("button", { name: "Show memory retrieval" });
  expect(exportJson().memory_retrieval).toEqual({ execution_id: 43, agent_id: 2, status: "not_loaded", evidence: null });
  await act(async () => pending.resolve(outcome === "success" ? response(fixture()) : response({ detail: "old private error" }, 503)));
  expect(exportJson().execution.id).toBe(43);
  expect(files.at(-1)!.content).not.toContain("Python original.");
  expect(files.at(-1)!.content).not.toContain("old private error");
});

test("same execution ID with changed Agent/input loses foreign evidence without automatically rereading it", async () => {
  const { data, fetchMock } = mockReads();
  render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  await screen.findByText("Memory #7");
  data.set(42, inspection(42, 2, "Rust"));
  fireEvent.click(screen.getByRole("button", { name: "Refresh execution" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled());
  expect(exportJson().memory_retrieval).toEqual({ execution_id: 42, agent_id: 2, status: "not_loaded", evidence: null });
  expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("memory-context"))).toHaveLength(1);
});

test("invalid foreign evidence is failed rather than included", async () => {
  const body = fixture(); body.evidence!.agent_memories[0].scope_id = 99;
  mockReads(async () => response(body));
  render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  await screen.findByRole("alert");
  expect(exportJson().memory_retrieval).toMatchObject({ status: "failed", evidence: null });
});

test("unmount prevents pending evidence from publishing to its owner", async () => {
  const pending = deferredResponse(); const callback = vi.fn();
  vi.stubGlobal("fetch", vi.fn(() => pending.promise));
  const view = render(<MemoryRetrievalPanel executionId={42} agentId={1} input="Python" onReportState={callback} />);
  fireEvent.click(screen.getByRole("button", { name: "Show memory retrieval" }));
  expect(callback.mock.calls.map(([state]) => state.status)).toEqual(["not_loaded", "loading"]);
  view.unmount(); await act(async () => pending.resolve(response(fixture())));
  expect(callback).toHaveBeenCalledTimes(2);
});

test("explicit memory loading and both exports preserve exact workbench conversation drafts", async () => {
  const draftFetch = mockDraftRequests().fetchMock;
  const data = inspection(42, 7); const body = fixture(); body.evidence!.agent_id = 7; body.evidence!.agent_memories[0].scope_id = 7;
  const fetchMock = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(url), "http://localhost").pathname;
    if (path === "/agents") return jsonResponse([testAgent]);
    if (path === "/agents/7") return jsonResponse(testAgent);
    if (path === "/projects/1") return jsonResponse({ id: 1, owner_id: 1 });
    if (path.startsWith("/conversations")) return draftFetch(url, init);
    if (path.endsWith("/memory-context")) return response(body);
    if (path === "/executions/42") return response(data.execution);
    if (path.endsWith("/trace")) return response(data.trace);
    if (path.endsWith("/snapshot")) return response(data.snapshot);
    return jsonResponse([]);
  }); vi.stubGlobal("fetch", fetchMock);
  render(<HomePage />);
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  fireEvent.change(screen.getByLabelText("Agent", { exact: true }), { target: { value: "7" } });
  const conversation = await screen.findByLabelText("Conversation", { exact: true });
  await waitFor(() => expect(within(conversation).getAllByRole("option").length).toBeGreaterThan(1));
  fireEvent.change(conversation, { target: { value: String(mainConversation.id) } });
  const message = await screen.findByLabelText("Chat message"), title = screen.getByLabelText("Conversation title", { exact: true });
  await waitFor(() => expect(message).toBeEnabled());
  fireEvent.change(message, { target: { value: "  未发送记忆报告草稿\n第二行  " } });
  fireEvent.change(title, { target: { value: "未保存记忆报告标题" } });
  fireEvent.change(screen.getByLabelText("Execution ID"), { target: { value: "42" } });
  fireEvent.click(screen.getByRole("button", { name: "Load Execution" }));
  fireEvent.click(await screen.findByRole("button", { name: "Show memory retrieval" }));
  await screen.findByText("Memory #7");
  const count = fetchMock.mock.calls.length;
  expect(exportJson().memory_retrieval.status).toBe("loaded");
  fireEvent.click(within(screen.getByRole("region", { name: "Export execution report" })).getByRole("button", { name: "Export Markdown" }));
  expect(fetchMock.mock.calls.length).toBe(count);
  expect(message).toHaveValue("  未发送记忆报告草稿\n第二行  ");
  expect(title).toHaveValue("未保存记忆报告标题");
  expect(conversation).toHaveValue(String(mainConversation.id));
  expect(fetchMock.mock.calls.every(([, init]) => init?.method === undefined || init.method === "GET")).toBe(true);
});
