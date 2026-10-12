import { expect, test } from "vitest";
import { createExecutionReport, MAX_EXECUTION_REPORT_BYTES } from "../src/utils/executionReport";
import type { MemoryEvidenceExportState } from "../src/types/memoryEvidence";
import { reportFixture } from "./executionReportFixtures";
import { fixture } from "./memoryEvidenceFixtures";

function sources() {
  const inspection = reportFixture();
  inspection.execution.input = "  Python  ";
  const memory: MemoryEvidenceExportState = {
    execution_id: 42, agent_id: 1, input: inspection.execution.input,
    status: "loaded", evidence: fixture().evidence,
  };
  return { inspection, memory };
}

test.each(["not_loaded", "loading", "unavailable", "failed"] as const)("records %s distinctly with no invented evidence", (status) => {
  const { inspection, memory } = sources(); memory.status = status; memory.evidence = null;
  const report = JSON.parse(createExecutionReport(inspection, "json", undefined, memory).content);
  expect(report.schema_version).toBe(2);
  expect(report.memory_retrieval).toEqual({ execution_id: 42, agent_id: 1, status, evidence: null });
});

test("default exports do not mistake an unread context for unavailable evidence", () => {
  const report = JSON.parse(createExecutionReport(reportFixture(), "json").content);
  expect(report.memory_retrieval).toEqual({ execution_id: 42, agent_id: 1, status: "not_loaded", evidence: null });
});

test("includes exact captured keyword and shared-user facts without changing source data", () => {
  const { inspection, memory } = sources();
  const facts = memory.evidence!;
  facts.shared_memories = [{ ...facts.agent_memories[0], memory_id: 8, scope: "user", scope_id: 3,
    content: "Python 用户偏好\n第二行" }];
  facts.context = `Shared user memory:\n${facts.shared_memories[0].content}\nAgent memory:\n${facts.agent_memories[0].content}`;
  const before = structuredClone(memory);
  const report = JSON.parse(createExecutionReport(inspection, "json", undefined, memory).content);
  expect(report.memory_retrieval.evidence).toEqual(facts);
  expect(memory).toEqual(before);
  expect(report).toMatchObject({ execution: inspection.execution, trace: inspection.trace,
    snapshot: inspection.snapshot, replays: inspection.replays });
});

test("includes real captured semantic metadata and similarity values", () => {
  const { inspection, memory } = sources();
  Object.assign(memory.evidence!, { requested_mode: "semantic", mode: "semantic", provider: "ollama",
    model: "embeddinggemma", min_similarity: 0.35 });
  Object.assign(memory.evidence!.agent_memories[0], { score: null, matched_terms: [], similarity: 0.960123456 });
  const report = JSON.parse(createExecutionReport(inspection, "json", undefined, memory).content);
  expect(report.memory_retrieval.evidence).toEqual(memory.evidence);
  expect(report.memory_retrieval.evidence.agent_memories[0].similarity).toBe(0.960123456);
});

test("retains captured keyword fallback reason without claiming semantic scores", () => {
  const { inspection, memory } = sources();
  Object.assign(memory.evidence!, { requested_mode: "semantic", fallback_reason: "Embedding model unavailable" });
  const report = JSON.parse(createExecutionReport(inspection, "json", undefined, memory).content);
  expect(report.memory_retrieval.evidence).toMatchObject({ mode: "keyword", provider: null,
    min_similarity: null, fallback_reason: "Embedding model unavailable" });
});

test("an available captured empty context remains loaded", () => {
  const { inspection, memory } = sources(); memory.evidence!.agent_memories = []; memory.evidence!.context = "";
  const report = JSON.parse(createExecutionReport(inspection, "json", undefined, memory).content);
  expect(report.memory_retrieval).toMatchObject({ status: "loaded", evidence: { context: "", agent_memories: [] } });
});

test.each(["execution", "agent", "input", "query", "memory_scope", "context"])("rejects foreign or inconsistent %s evidence", (field) => {
  const { inspection, memory } = sources();
  if (field === "execution") memory.execution_id = 99;
  if (field === "agent") memory.agent_id = 99;
  if (field === "input") memory.input = "Rust";
  if (field === "query") memory.evidence!.query = "Rust";
  if (field === "memory_scope") memory.evidence!.agent_memories[0].scope_id = 99;
  if (field === "context") memory.evidence!.context = "live replacement";
  expect(() => createExecutionReport(inspection, "json", undefined, memory)).toThrow();
});

test.each(["not_loaded", "loading", "unavailable", "failed"] as const)("%s cannot export stale loaded content", (status) => {
  const { inspection, memory } = sources(); memory.status = status;
  expect(() => createExecutionReport(inspection, "json", undefined, memory)).toThrow();
});

test("loaded evidence cannot be null", () => {
  const { inspection, memory } = sources(); memory.evidence = null;
  expect(() => createExecutionReport(inspection, "json", undefined, memory)).toThrow();
});

test("omits unrelated fields and private read errors from reports", () => {
  const { inspection, memory } = sources();
  Object.assign(memory, { error: "private endpoint secret" });
  Object.assign(memory.evidence!, { endpoint: "private endpoint secret" });
  Object.assign(memory.evidence!.agent_memories[0], { endpoint: "private endpoint secret" });
  expect(createExecutionReport(inspection, "json", undefined, memory).content).not.toContain("private endpoint secret");
});

test("Markdown fences memory content while preserving original Unicode and multiline strings", () => {
  const { inspection, memory } = sources();
  const text = 'Python 中文\n``````\n# title\n<script>alert("x")</script>';
  memory.evidence!.agent_memories[0].content = text; memory.evidence!.context = text;
  const markdown = createExecutionReport(inspection, "markdown", undefined, memory).content;
  expect(markdown).toContain("## Captured memory retrieval");
  expect(markdown).toContain("```````json");
  const parts = [...markdown.matchAll(/(`{3,})json\n([\s\S]*?)\n\1/g)].map((part) => JSON.parse(part[2]));
  expect(parts[3].evidence.context).toBe(text);
  expect(parts[3].evidence.agent_memories[0].content).toBe(text);
});

test.each(["json", "markdown"] as const)("memory is counted in the %s UTF-8 report limit", (format) => {
  const { inspection, memory } = sources();
  const text = "中".repeat(Math.ceil(MAX_EXECUTION_REPORT_BYTES / 3));
  memory.evidence!.agent_memories[0].content = text; memory.evidence!.context = text;
  expect(() => createExecutionReport(inspection, format, undefined, memory)).toThrow("10 MiB");
});
