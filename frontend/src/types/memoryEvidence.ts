export type MemoryEvidenceItem = {
  memory_id: number;
  scope: "agent" | "user";
  scope_id: number;
  content: string;
  created_at: string;
  score: number | null;
  matched_terms: string[];
  similarity: number | null;
};

export type MemoryEvidence = {
  version: 1;
  agent_id: number;
  user_id: number | null;
  query: string;
  limit: number;
  recorded_at: string;
  requested_mode: "keyword" | "semantic";
  mode: "keyword" | "semantic";
  provider: "mock" | "ollama" | null;
  model: string | null;
  min_similarity: number | null;
  fallback_reason: string | null;
  agent_memories: MemoryEvidenceItem[];
  shared_memories: MemoryEvidenceItem[];
  context: string;
};

export type ExecutionMemoryContext = {
  execution_id: number;
  available: boolean;
  evidence: MemoryEvidence | null;
};
