from datetime import datetime
from typing import Literal

from pydantic import BaseModel


MessageRoleFilter = Literal["user", "assistant", "system", "tool"]


class MessageSearchItem(BaseModel):
    id: int
    conversation_id: int
    role: str
    created_at: datetime
    snippet: str
    match_start: int
    match_end: int
    truncated_before: bool
    truncated_after: bool


class MessageSearchResponse(BaseModel):
    conversation_id: int
    agent_id: int
    query: str
    role: MessageRoleFilter | None
    limit: int
    offset: int
    total: int
    has_more: bool
    items: list[MessageSearchItem]
