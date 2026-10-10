export type Conversation = {
  id: number;
  agent_id: number;
  title: string;
  created_at: string;
};

export type ConversationMessage = {
  id: number;
  conversation_id: number;
  role: string;
  content: string;
  created_at: string;
};

export type ConversationPage = {
  agent_id: number;
  query: string;
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
  items: Conversation[];
};
