"""Search one Agent's saved messages using a bounded joined page."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.agent_message_search import AgentMessageSearchItem
from app.services.message_search import ascii_lower, preview


def search_agent_messages(db: Session, agent_id: int, query: str, role: str | None, limit: int, offset: int):
    rows = db.query(Message, Conversation.title, Conversation.agent_id).join(
        Conversation, Message.conversation_id == Conversation.id,
    ).filter(
        Conversation.agent_id == agent_id,
        func.instr(func.lower(Message.content), ascii_lower(query)) > 0,
    )
    if role is not None:
        rows = rows.filter(Message.role == role)
    total = rows.count()
    page = rows.order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(limit).all()
    return [AgentMessageSearchItem(**preview(message, query).model_dump(),
                                   conversation_title=title, agent_id=owner)
            for message, title, owner in page], total
