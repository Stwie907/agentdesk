from datetime import datetime

from pydantic import BaseModel


class ExecutionSnapshotCreate(BaseModel):
    """
    Internal schema used when persisting a Runtime V4 execution snapshot.

    A snapshot captures the execution state needed for deterministic
    inspection and future replay support.
    """

    execution_id: int
    input_snapshot: str
    plan_snapshot: str | None = None
    output_snapshot: str | None = None


class ExecutionSnapshotRead(BaseModel):
    """
    API representation of a persisted Runtime V4 execution snapshot.
    """

    id: int
    execution_id: int

    input_snapshot: str
    plan_snapshot: str | None = None
    output_snapshot: str | None = None

    created_at: datetime

    model_config = {"from_attributes": True}
