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


class ExecutionTraceRead(BaseModel):
    """
    Structured Runtime V4 execution trace event.

    Runtime V4 trace data is currently persisted inside
    ExecutionLog.message. This schema exposes the useful
    lifecycle fields directly to API clients so they do not
    need to parse internal log-message formatting.
    """

    id: int
    execution_id: int

    event: str

    step_index: int | None = None
    tool: str | None = None
    error: str | None = None

    message: str
    created_at: datetime
