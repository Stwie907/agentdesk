from pydantic import BaseModel

from app.schemas.message import MessageResponse


class MessageContextResponse(BaseModel):
    conversation_id: int
    agent_id: int
    anchor_message_id: int
    before: int
    after: int
    anchor_index: int
    has_more_before: bool
    has_more_after: bool
    items: list[MessageResponse]
