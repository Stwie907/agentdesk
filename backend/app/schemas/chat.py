from typing import Annotated

from pydantic import BaseModel, StringConstraints


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    execution_id: int
    response: str
    status: str


class ConversationChatRequest(ChatRequest):
    message: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4000)]
