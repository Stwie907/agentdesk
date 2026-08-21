from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.schemas.conversation import ConversationCreate


def create_conversation(
    db: Session,
    conversation: ConversationCreate
):

    db_conversation = Conversation(
        agent_id=conversation.agent_id,
        title=conversation.title
    )

    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)

    return db_conversation



def get_conversation(
    db: Session,
    conversation_id: int
):

    return (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id
        )
        .first()
    )



def get_conversations(
    db: Session
):

    return (
        db.query(Conversation)
        .all()
    )



def delete_conversation(
    db: Session,
    conversation_id: int
):

    conversation = get_conversation(
        db,
        conversation_id
    )

    if conversation:
        db.delete(conversation)
        db.commit()

    return conversation
