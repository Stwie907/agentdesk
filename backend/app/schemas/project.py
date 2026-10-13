from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    owner_id: int


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    created_at: datetime


    model_config = {"from_attributes": True}
