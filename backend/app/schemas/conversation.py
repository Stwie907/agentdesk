from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class ConversationCreate(BaseModel):
    agent_id: int
    title: str | None = None


class ConversationResponse(BaseModel):
    id: int
    agent_id: int
    title: str | None
    created_at: datetime


    model_config = {"from_attributes": True}


class ConversationCreateRequest(BaseModel):
    agent_id: Annotated[int, Field(strict=True, gt=0)]
    title: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)]
