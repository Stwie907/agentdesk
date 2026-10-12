import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ExecutionReportExport } from "../src/components/ExecutionReportExport";
import { ExecutionInspector } from "../src/components/ExecutionInspector";
import { reportFixture } from "./executionReportFixtures";
import { jsonResponse } from "./taskFixtures";
import { testAgent } from "./taskFixtures";
import { mockDraftRequests, mainConversation } from "./draftPersistenceFixtures";
import { HomePage } from "../src/pages/HomePage";

const api = vi.hoisted(() => ({ inspection: vi.fn(), replay: vi.fn(), cancel: vi.fn(), retry: vi.fn() }));
vi.mock("../src/api/executions", async (original) => ({
  ...await original<object>(), getExecutionInspection: api.inspection,
  replayExecution: api.replay, cancelExecution: api.cancel, retryExecution: api.retry,
}));

const createUrl = vi.fn(() => "blob:report-test");
const revokeUrl = vi.fn();
let downloads: string[];

beforeEach(() => {
  vi.clearAllMocks();
  downloads = [];
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeUrl });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download); });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "No memory evidence" }, 404)));
  api.inspection.mockImplementation(async (id: number) => reportFixture(id));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test.each(["JSON", "Markdown"])("exports %s without additional network requests", (label) => {
  render(<ExecutionReportExport inspection={reportFixture()} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: `Export ${label}` }));
  expect(downloads).toEqual([`execution-42.${label === "JSON" ? "json" : "md"}`]);
  expect(screen.getByRole("status")).toHaveTextContent("Download requested");
  expect(fetch).not.toHaveBeenCalled();
  expect(api.inspection).not.toHaveBeenCalled();
});

test("busy inspection disables both export controls", () => {
  render(<ExecutionReportExport inspection={reportFixture()} disabled />);
  const button = screen.getByRole("button", { name: "Export JSON" });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(createUrl).not.toHaveBeenCalled();
});

test("download failure shows a local error and allows retry", () => {
  createUrl.mockImplementationOnce(() => { throw new Error("private browser detail"); });
  render(<ExecutionReportExport inspection={reportFixture()} disabled={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Unable to export");
  expect(screen.getByRole("alert")).not.toHaveTextContent("private browser detail");
  fireEvent.click(screen.getByRole("button", { name: "Export Markdown" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(downloads).toEqual(["execution-42.md"]);
});

test("late execution load cannot replace a newer selection or its report", async () => {
  let resolve!: (value: ReturnType<typeof reportFixture>) => void;
  const old = new Promise<ReturnType<typeof reportFixture>>((done) => { resolve = done; });
  api.inspection.mockImplementation((id: number) => id === 42 ? old : Promise.resolve(reportFixture(id)));
  const view = render(<ExecutionInspector selectedExecutionId={42} />);
  expect(screen.queryByRole("button", { name: "Export JSON" })).not.toBeInTheDocument();
  view.rerender(<ExecutionInspector selectedExecutionId={99} />);
  fireEvent.click(await screen.findByRole("button", { name: "Export JSON" }));
  await act(async () => resolve(reportFixture(42)));
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  expect(downloads).toEqual(["execution-99.json", "execution-99.json"]);
});

test("deselection ignores a late read and removes reports", async () => {
  let resolve!: (value: ReturnType<typeof reportFixture>) => void;
  api.inspection.mockReturnValue(new Promise((done) => { resolve = done; }));
  const view = render(<ExecutionInspector selectedExecutionId={42} />);
  view.rerender(<ExecutionInspector selectedExecutionId={null} />);
  await act(async () => resolve(reportFixture()));
  expect(screen.queryByRole("button", { name: "Export JSON" })).not.toBeInTheDocument();
});

test("a late refresh cannot replace the newly selected report", async () => {
  const view = render(<ExecutionInspector selectedExecutionId={42} />);
  await screen.findByRole("button", { name: "Export JSON" });
  let resolve!: (value: ReturnType<typeof reportFixture>) => void;
  api.inspection.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "Refresh execution" }));
  expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  view.rerender(<ExecutionInspector selectedExecutionId={99} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled());
  await act(async () => resolve(reportFixture()));
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  expect(downloads).toEqual(["execution-99.json"]);
});

test.each(["Replay execution", "Retry execution"])("late %s does not redirect a newer report", async (label) => {
  let resolve!: (value: ReturnType<typeof reportFixture>["execution"]) => void;
  const action = label === "Replay execution" ? api.replay : api.retry;
  action.mockReturnValue(new Promise((done) => { resolve = done; }));
  const view = render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: label }));
  view.rerender(<ExecutionInspector selectedExecutionId={99} />);
  await screen.findByRole("button", { name: "Export JSON" });
  await act(async () => resolve(reportFixture(43).execution));
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  expect(downloads).toEqual(["execution-99.json"]);
});

test("exporting both reports in the workbench preserves the conversation and exact drafts", async () => {
  const draftFetch = mockDraftRequests().fetchMock;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/agents") return jsonResponse([testAgent]);
    if (path === "/agents/7") return jsonResponse(testAgent);
    if (path === "/projects/1") return jsonResponse({ id: 1, owner_id: 1 });
    if (path.startsWith("/conversations")) return draftFetch(input, init);
    if (path.endsWith("/memory-context")) return jsonResponse({ detail: "No memory evidence" }, 404);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<HomePage />);
  await screen.findByRole("option", { name: "Calculator Agent (ID: 7)" });
  fireEvent.change(screen.getByLabelText("Agent", { exact: true }), { target: { value: "7" } });
  const conversation = await screen.findByLabelText("Conversation", { exact: true });
  await waitFor(() => expect(within(conversation).getAllByRole("option").length).toBeGreaterThan(1));
  fireEvent.change(conversation, { target: { value: String(mainConversation.id) } });
  const message = await screen.findByLabelText("Chat message");
  const title = screen.getByLabelText("Conversation title", { exact: true });
  await waitFor(() => expect(message).toBeEnabled());
  fireEvent.change(message, { target: { value: "  未发送的报告草稿\n第二行  " } });
  fireEvent.change(title, { target: { value: "未保存标题" } });
  fireEvent.change(screen.getByLabelText("Execution ID"), { target: { value: "42" } });
  fireEvent.click(screen.getByRole("button", { name: "Load Execution" }));
  const group = await screen.findByRole("region", { name: "Export execution report" });
  const requestCount = fetchMock.mock.calls.length;
  fireEvent.click(within(group).getByRole("button", { name: "Export JSON" }));
  fireEvent.click(within(group).getByRole("button", { name: "Export Markdown" }));
  expect(message).toHaveValue("  未发送的报告草稿\n第二行  ");
  expect(title).toHaveValue("未保存标题");
  expect(conversation).toHaveValue(String(mainConversation.id));
  expect(fetchMock.mock.calls.length).toBe(requestCount);
  expect(fetchMock.mock.calls.every(([, init]) => init?.method === undefined || init.method === "GET")).toBe(true);
  expect(downloads).toEqual(["execution-42.json", "execution-42.md"]);
});

test("a late cancellation cannot attach its execution to a newer report", async () => {
  api.inspection.mockImplementation(async (id: number) => {
    const data = reportFixture(id); data.execution.status = id === 42 ? "pending" : "completed"; return data;
  });
  let resolve!: (value: ReturnType<typeof reportFixture>["execution"]) => void;
  api.cancel.mockReturnValue(new Promise((done) => { resolve = done; }));
  const view = render(<ExecutionInspector selectedExecutionId={42} />);
  fireEvent.click(await screen.findByRole("button", { name: "Cancel execution" }));
  view.rerender(<ExecutionInspector selectedExecutionId={99} />);
  await screen.findByRole("button", { name: "Export JSON" });
  await act(async () => resolve({ ...reportFixture().execution, status: "cancelled" }));
  fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
  expect(downloads).toEqual(["execution-99.json"]);
});
