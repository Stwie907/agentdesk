import { afterEach, expect, test, vi } from "vitest";
import { reportFixture } from "./executionReportFixtures";
import { createExecutionReport, downloadExecutionReport, MAX_EXECUTION_REPORT_BYTES } from "../src/utils/executionReport";


afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

test("JSON preserves all displayed data, Unicode, nulls and failure details", () => {
  const source = reportFixture();
  const original = structuredClone(source);
  const file = createExecutionReport(source, "json", "2026-10-12T08:00:00Z");
  const report = JSON.parse(file.content);
  expect(report).toMatchObject({ schema_version: 1, captured_at: "2026-10-12T08:00:00Z",
    source: "displayed_execution_inspection", ...source });
  expect(source).toEqual(original);
  expect(file.filename).toBe("execution-42.json");
  expect(file.mime).toContain("application/json");
});

test("Markdown fences saved content and preserves recoverable structured sections", () => {
  const source = reportFixture();
  const file = createExecutionReport(source, "markdown");
  expect(file.filename).toBe("execution-42.md");
  expect(file.content).toContain("````json");
  const blocks = [...file.content.matchAll(/(`{3,})json\n([\s\S]*?)\n\1/g)];
  expect(blocks.map((block) => JSON.parse(block[2]))).toEqual([
    source.execution, source.trace, source.snapshot, source.replays,
  ]);
  expect(file.content).toContain("not an atomic database backup");
});

test("missing optional data is explicit without invented events", () => {
  const source = { ...reportFixture(), trace: [], snapshot: null, replays: [] };
  expect(JSON.parse(createExecutionReport(source, "json").content)).toMatchObject({ trace: [], snapshot: null, replays: [] });
  const markdown = createExecutionReport(source, "markdown").content;
  expect(markdown).toContain("No Runtime V4 trace events.");
  expect(markdown).toContain("No snapshot available.");
  expect(markdown).toContain("No replay executions.");
});

test("only allowlisted endpoint fields are exported", () => {
  const source = reportFixture();
  Object.assign(source.execution, { private_endpoint: "secret", unrelated: "secret" });
  Object.assign(source.snapshot!, { private_endpoint: "secret" });
  expect(createExecutionReport(source, "json").content).not.toContain("secret");
});

test.each(["trace", "snapshot", "replays"] as const)("rejects foreign %s data", (field) => {
  const source = reportFixture();
  if (field === "trace") source.trace[0].execution_id = 99;
  if (field === "snapshot") source.snapshot!.execution_id = 99;
  if (field === "replays") source.replays[0].replay_of_execution_id = 99;
  expect(() => createExecutionReport(source, "json")).toThrow("another execution");
});

test.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])("rejects invalid execution id %s", (id) => {
  expect(() => createExecutionReport(reportFixture(id), "json")).toThrow();
});

test.each(["json", "markdown"] as const)("rejects oversized %s without truncating input", (format) => {
  const source = reportFixture();
  source.execution.input = "中".repeat(Math.ceil(MAX_EXECUTION_REPORT_BYTES / 3));
  expect(() => createExecutionReport(source, format)).toThrow("10 MiB");
});

test("download releases object URL and removes its link even when browser click fails", () => {
  vi.useFakeTimers();
  const create = vi.fn(() => "blob:execution-test");
  const revoke = vi.fn();
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => { throw new Error("blocked"); });
  expect(() => downloadExecutionReport(createExecutionReport(reportFixture(), "json"))).toThrow("blocked");
  expect(document.querySelector("a")).toBeNull();
  expect(revoke).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1000);
  expect(revoke).toHaveBeenCalledWith("blob:execution-test");
});
