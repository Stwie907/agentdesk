from pydantic import BaseModel

from app.schemas.message_search import MessageRoleFilter, MessageSearchItem


class AgentMessageSearchItem(MessageSearchItem):
    agent_id: int
    conversation_title: str


class AgentMessageSearchResponse(BaseModel):
    agent_id: int
    query: str
    role: MessageRoleFilter | None
    limit: int
    offset: int
    total: int
    has_more: bool
    items: list[AgentMessageSearchItem]
