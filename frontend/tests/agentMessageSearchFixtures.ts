import type { MessageRoleFilter } from "../src/api/messageSearch";
import type { ConversationMessage } from "../src/types/conversations";
import { exportConversation, exportMessages } from "./conversationExportFixtures";
import { messageSearchData, searchResponse } from "./messageSearchFixtures";

export const siblingMessage: ConversationMessage = {
  id: 26, conversation_id: 92, role: "assistant", created_at: "2026-10-10T06:00:00",
  content: 'Saved sibling turn 01 — 中文 🐍\n<script>literal</script>\n',
};
export const agentHistory = [...exportMessages, siblingMessage];
export const siblingTitle = '<script>Literal sibling title</script> — 中文';

export function agentSearchData(query = "中文", role: MessageRoleFilter = null, limit = 10, offset = 0,
                                messages = agentHistory, agentId = 7) {
  const data = messageSearchData(query, role, limit, offset, messages);
  return { agent_id: agentId, query: data.query, role, limit, offset, total: data.total, has_more: data.has_more,
    items: data.items.map((row) => ({ ...row, agent_id: agentId,
      conversation_title: row.conversation_id === 91 ? exportConversation.title : siblingTitle })) };
}

export function agentSearchResponse(value: unknown = agentSearchData(), status = 200) { return searchResponse(value, status); }

export const siblingMarkdown = `# Saved message context

This is a saved-message excerpt. Import conversation requires a full conversation JSON backup.

- Export kind: agentdesk.message_context
- Export schema: 1
- Conversation ID: 92
- Agent ID: 7
- Selected message ID: 26
- Requested earlier messages: 3
- Requested later messages: 3
- Selected message index: 0
- Earlier saved messages outside excerpt: false
- Later saved messages outside excerpt: false
- Saved messages: 1

## Selected message 26

Role:

\`\`\`text
assistant
\`\`\`

Created at: 2026-10-10T06:00:00

Content:

\`\`\`text
Saved sibling turn 01 — 中文 🐍
<script>literal</script>

\`\`\`
`;
