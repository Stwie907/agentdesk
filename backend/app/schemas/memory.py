from pydantic import BaseModel
from datetime import datetime


class MemoryCreate(BaseModel):
    agent_id: int
    content: str


class MemoryResponse(BaseModel):
    id: int
    agent_id: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

