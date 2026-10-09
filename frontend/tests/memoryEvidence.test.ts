import { afterEach, expect, test, vi } from "vitest";
import { getExecutionMemoryContext } from "../src/api/memoryEvidence";
import type { ExecutionMemoryContext } from "../src/types/memoryEvidence";
import { fixture, response } from "./memoryEvidenceFixtures";

afterEach(() => vi.unstubAllGlobals());

test("reads persisted evidence with the execution Agent scope and no-store", async () => {
  const body = fixture();
  const fetchMock = vi.fn(async () => response(body)); vi.stubGlobal("fetch", fetchMock);
  expect(await getExecutionMemoryContext(42, 1, "  Python  ")).toEqual(body);
  expect(fetchMock).toHaveBeenCalledWith("/executions/42/memory-context?agent_id=1", { cache: "no-store" });
});

test("accepts explicitly unavailable historical evidence", async () => {
  const body = { execution_id: 42, available: false, evidence: null };
  vi.stubGlobal("fetch", vi.fn(async () => response(body)));
  expect(await getExecutionMemoryContext(42, 1, "Python")).toEqual(body);
});

test.each(["mock", "ollama"] as const)("validates semantic evidence from %s", async provider => {
  const body = fixture(); const facts = body.evidence!;
  Object.assign(facts, { requested_mode: "semantic", mode: "semantic", provider,
    model: provider === "mock" ? "mock-fixtures-v1" : "embeddinggemma", min_similarity: 0.35 });
  Object.assign(facts.agent_memories[0], { score: null, matched_terms: [], similarity: 0.96 });
  vi.stubGlobal("fetch", vi.fn(async () => response(body)));
  expect(await getExecutionMemoryContext(42, 1, "Python")).toEqual(body);
});

const corruptions: [string, (body: ExecutionMemoryContext) => void][] = [
  ["execution", b => { b.execution_id = 99; }],
  ["version", b => { Object.assign(b.evidence!, { version: 2 }); }],
  ["Agent", b => { b.evidence!.agent_id = 2; }],
  ["query", b => { b.evidence!.query = "Rust"; }],
  ["scope", b => { b.evidence!.agent_memories[0].scope_id = 2; }],
  ["boolean identity", b => { Object.assign(b.evidence!.agent_memories[0], { memory_id: true }); }],
  ["non-finite score", b => { b.evidence!.agent_memories[0].score = Infinity; }],
  ["keyword terms", b => { b.evidence!.agent_memories[0].matched_terms = []; }],
  ["duplicate terms", b => { b.evidence!.agent_memories[0].score = 2; b.evidence!.agent_memories[0].matched_terms = ["python", "python"]; }],
  ["duplicate record", b => { b.evidence!.agent_memories.push({ ...b.evidence!.agent_memories[0] }); }],
  ["limit", b => { b.evidence!.limit = 0; }],
  ["negative limit", b => { b.evidence!.limit = -1; }],
  ["timestamp", b => { b.evidence!.recorded_at = "invalid"; }],
  ["memory timestamp", b => { b.evidence!.agent_memories[0].created_at = "invalid"; }],
  ["context", b => { b.evidence!.context = "Fresh current memory"; }],
  ["provider in keyword mode", b => { b.evidence!.provider = "ollama"; }],
  ["missing fallback reason", b => { b.evidence!.requested_mode = "semantic"; }],
  ["blank fallback reason", b => { b.evidence!.fallback_reason = "  "; }],
  ["wrong shared owner", b => {
    b.evidence!.shared_memories = [{ ...b.evidence!.agent_memories[0], scope: "user", scope_id: 4 }];
    b.evidence!.context = "Shared user memory:\nPython original.\nAgent memory:\nPython original.";
  }],
  ["reversed ranking", b => {
    b.evidence!.agent_memories.push({ ...b.evidence!.agent_memories[0], memory_id: 8 });
    b.evidence!.context = "Python original.\nPython original.";
  }],
  ["unavailable with data", b => { b.available = false; }],
  ["available without data", b => { b.evidence = null; }],
];

test.each(corruptions)("rejects invalid %s", async (_, corrupt) => {
  const body = fixture(); corrupt(body);
  vi.stubGlobal("fetch", vi.fn(async () => response(body)));
  await expect(getExecutionMemoryContext(42, 1, "Python")).rejects.toThrow("Invalid memory retrieval evidence");
});

test.each([NaN, Infinity, 0, 1.1, -0.5])("rejects invalid cosine %s", async similarity => {
  const body = fixture(); const facts = body.evidence!;
  Object.assign(facts, { requested_mode: "semantic", mode: "semantic", provider: "ollama", model: "embeddinggemma", min_similarity: 0.35 });
  Object.assign(facts.agent_memories[0], { score: null, matched_terms: [], similarity });
  vi.stubGlobal("fetch", vi.fn(async () => response(body)));
  await expect(getExecutionMemoryContext(42, 1, "Python")).rejects.toThrow("Invalid memory retrieval evidence");
});

test("surfaces the API's persisted corruption error", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({ detail: "Persisted memory evidence is invalid" }, 409)));
  await expect(getExecutionMemoryContext(42, 1, "Python")).rejects.toThrow("Persisted memory evidence is invalid");
});
