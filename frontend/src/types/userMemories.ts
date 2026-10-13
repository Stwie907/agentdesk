export type UserMemory = {
  id: number;
  user_id: number;
  content: string;
  created_at: string;
};

export type UserMemoryList = {
  agent_id: number;
  user_id: number;
  username: string;
  memories: UserMemory[];
};

export type UserMemorySearch = {
  agent_id: number;
  user_id: number;
  query: string;
  limit: number;
  results: { memory: UserMemory; score: number; matched_terms: string[] }[];
};
