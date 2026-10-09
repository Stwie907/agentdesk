import { requestJson } from "./executions";
import type { ExecutionMemoryContext, MemoryEvidence, MemoryEvidenceItem } from "../types/memoryEvidence";

const INVALID = "Invalid memory retrieval evidence received.";

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function positiveId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.includes("T") && Number.isFinite(Date.parse(value));
}

function requireValid(condition: unknown): asserts condition {
  if (!condition) throw new Error(INVALID);
}

function validateItems(value: unknown, scope: "agent" | "user", owner: number | null,
  facts: MemoryEvidence): asserts value is MemoryEvidenceItem[] {
  requireValid(Array.isArray(value) && value.length <= facts.limit);
  const seen = new Set<number>();
  let previous: { score: number; id: number } | null = null;
  for (const row of value) {
    requireValid(object(row) && positiveId(row.memory_id) && row.scope === scope
      && owner !== null && row.scope_id === owner && typeof row.content === "string"
      && timestamp(row.created_at) && Array.isArray(row.matched_terms));
    requireValid(!seen.has(row.memory_id));
    seen.add(row.memory_id);
    let score: number;
    if (facts.mode === "semantic") {
      requireValid(typeof row.similarity === "number" && Number.isFinite(row.similarity)
        && row.similarity > 0 && row.similarity <= 1 && facts.min_similarity !== null
        && row.similarity >= facts.min_similarity && row.score === null && row.matched_terms.length === 0);
      score = row.similarity;
    } else {
      requireValid(typeof row.score === "number" && Number.isSafeInteger(row.score)
        && row.score >= 0 && row.score === row.matched_terms.length && row.similarity === null
        && (facts.query ? row.score > 0 : row.score === 0));
      let previousTerm = "";
      for (const term of row.matched_terms) {
        requireValid(typeof term === "string" && term.length > 0 && term > previousTerm);
        previousTerm = term;
      }
      score = row.score;
    }
    if (facts.query && previous !== null) {
      requireValid(score < previous.score || (score === previous.score && row.memory_id < previous.id));
    }
    previous = { score, id: row.memory_id };
  }
}

export async function getExecutionMemoryContext(executionId: number, agentId: number,
  input: string): Promise<ExecutionMemoryContext> {
  requireValid(positiveId(executionId) && positiveId(agentId));
  const body = await requestJson<unknown>(
    `/executions/${executionId}/memory-context?agent_id=${agentId}`, { cache: "no-store" });
  requireValid(object(body) && body.execution_id === executionId && typeof body.available === "boolean");
  if (!body.available) {
    requireValid(body.evidence === null);
    return body as ExecutionMemoryContext;
  }
  const value = body.evidence;
  requireValid(object(value) && value.version === 1 && value.agent_id === agentId
    && (value.user_id === null || positiveId(value.user_id)) && value.query === input.trim()
    && typeof value.limit === "number" && Number.isSafeInteger(value.limit) && value.limit >= 0
    && timestamp(value.recorded_at) && (value.requested_mode === "keyword" || value.requested_mode === "semantic")
    && (value.mode === "keyword" || value.mode === "semantic") && typeof value.context === "string"
    && (value.fallback_reason === null || (typeof value.fallback_reason === "string" && value.fallback_reason.trim())));
  if (value.mode === "semantic") {
    requireValid(value.requested_mode === "semantic" && value.query && value.limit > 0
      && (value.provider === "mock" || value.provider === "ollama")
      && typeof value.model === "string" && value.model.trim() && value.fallback_reason === null
      && typeof value.min_similarity === "number" && Number.isFinite(value.min_similarity)
      && value.min_similarity >= 0 && value.min_similarity <= 1);
  } else {
    requireValid(value.provider === null && value.model === null && value.min_similarity === null);
    if (value.requested_mode === "semantic" && value.query && value.limit > 0) requireValid(value.fallback_reason);
  }
  const facts = value as MemoryEvidence;
  validateItems(value.agent_memories, "agent", agentId, facts);
  validateItems(value.shared_memories, "user", facts.user_id, facts);
  const agent = value.agent_memories.map(row => row.content).join("\n");
  const shared = value.shared_memories.map(row => row.content).join("\n");
  const context = shared ? `Shared user memory:\n${shared}${agent ? `\nAgent memory:\n${agent}` : ""}` : agent;
  requireValid(value.context === context);
  return body as ExecutionMemoryContext;
}
