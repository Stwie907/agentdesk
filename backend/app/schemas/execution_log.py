from datetime import datetime
from pydantic import BaseModel


class ExecutionLogRead(BaseModel):

    id: int

    execution_id: int

    message: str

    created_at: datetime


    class Config:
        from_attributes = True
