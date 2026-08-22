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
        .all()
    )
