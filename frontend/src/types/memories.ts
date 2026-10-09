export type Memory = {
  id: number;
  agent_id: number;
  content: string;
  created_at: string;
};

export type MemorySearchResult = {
  memory: Memory;
  score: number;
  matched_terms: string[];
};

export type MemorySearchResponse = {
  agent_id: number;
  query: string;
  limit: number;
  results: MemorySearchResult[];
};
