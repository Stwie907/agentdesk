import type { ExecutionMemoryContext } from "../src/types/memoryEvidence";

export function fixture(): ExecutionMemoryContext {
  return { execution_id: 42, available: true, evidence: {
    version: 1, agent_id: 1, user_id: 3, query: "Python", limit: 5,
    recorded_at: "2026-10-09T10:00:00Z", requested_mode: "keyword", mode: "keyword",
    provider: null, model: null, min_similarity: null, fallback_reason: null,
    agent_memories: [{ memory_id: 7, scope: "agent", scope_id: 1, content: "Python original.",
      created_at: "2026-10-09T09:00:00", score: 1, matched_terms: ["python"], similarity: null }],
    shared_memories: [], context: "Python original.",
  } };
}

export function response(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}
