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

    retry_count: int = 0
    failure_type: str | None = None
    failure_message: str | None = None

    created_at: datetime

    model_config = {"from_attributes": True}

class ExecutionLogRead(BaseModel):
    id: int
    execution_id: int
    level: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}
