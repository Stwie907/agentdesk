"""Read bounded neighbouring messages in timestamp/ID order without writes."""

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.message import Message


def get_message_context(db: Session, anchor: Message, before: int, after: int):
    scoped = db.query(Message).filter(Message.conversation_id == anchor.conversation_id)
    earlier = scoped.filter(or_(
        Message.created_at < anchor.created_at,
        and_(Message.created_at == anchor.created_at, Message.id < anchor.id),
    )).order_by(Message.created_at.desc(), Message.id.desc()).limit(before + 1).all()
    later = scoped.filter(or_(
        Message.created_at > anchor.created_at,
        and_(Message.created_at == anchor.created_at, Message.id > anchor.id),
    )).order_by(Message.created_at.asc(), Message.id.asc()).limit(after + 1).all()
    selected_before = list(reversed(earlier[:before]))
    return selected_before + [anchor] + later[:after], len(selected_before), len(earlier) > before, len(later) > after
