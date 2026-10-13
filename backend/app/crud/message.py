from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.message import Message
from app.schemas.message import MessageCreate


def create_message(
    db: Session,
    conversation_id: int,
    message: MessageCreate
):
    db_message = Message(
        conversation_id=conversation_id,
        role=message.role,
        content=message.content,
    )

    db.add(db_message)
    db.commit()
    db.refresh(db_message)

    return db_message


def get_messages(
    db: Session,
    conversation_id: int
):
    return (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )


def get_message_cursor(db: Session, conversation_id: int, message_id: int):
    return db.query(Message).filter(
        Message.conversation_id == conversation_id, Message.id == message_id,
    ).first()


def get_message_page(db: Session, conversation_id: int, limit: int, before: Message | None = None):
    query = db.query(Message).filter(Message.conversation_id == conversation_id)
    if before is not None:
        query = query.filter(or_(
            Message.created_at < before.created_at,
            and_(Message.created_at == before.created_at, Message.id < before.id),
        ))
    # One extra bounded row tells the caller whether an older page exists.
    rows = query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1).all()
    return list(reversed(rows[:limit])), len(rows) > limit
