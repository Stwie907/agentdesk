from pydantic import BaseModel
from datetime import datetime


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    model: str = "qwen2.5"
    project_id: int


class AgentResponse(BaseModel):
    id: int
    name: str
    description: str | None
    model: str
    project_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
