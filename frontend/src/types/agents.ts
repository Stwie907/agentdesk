export type Agent = {
  id: number;
  name: string;
  description: string | null;
  model: string;
  project_id: number;
  allowed_tools: string[];
  created_at: string;
};

export type AgentChatResponse = {
  execution_id: number;
  response: string;
  status: string;
};
