from datetime import datetime
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    agent_id: int
    title: str | None = None


class ConversationResponse(BaseModel):
    id: int
    agent_id: int
    title: str | None
    created_at: datetime


    class Config:
        from_attributes = True
