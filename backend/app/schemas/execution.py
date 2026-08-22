from datetime import datetime
from pydantic import BaseModel


class ExecutionCreate(BaseModel):
    agent_id: int
    input: str


class ExecutionRead(BaseModel):
    id: int
    agent_id: int
    input: str
    output: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
