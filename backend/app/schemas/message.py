from datetime import datetime
from pydantic import BaseModel


class MessageCreate(BaseModel):
    role: str
    content: str


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessagePageResponse(BaseModel):
    conversation_id: int
    agent_id: int
    limit: int
    before_id: int | None
    has_more: bool
    next_before_id: int | None
    items: list[MessageResponse]
