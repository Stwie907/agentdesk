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

export type ConversationMessagePage = {
  conversation_id: number;
  agent_id: number;
  limit: number;
  before_id: number | null;
  has_more: boolean;
  next_before_id: number | null;
  items: ConversationMessage[];
};
