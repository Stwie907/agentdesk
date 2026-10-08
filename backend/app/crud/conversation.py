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
    conversation_id: int,
    agent_id: int | None = None,
):
    query = db.query(Conversation).filter(Conversation.id == conversation_id)
    if agent_id is not None:
        query = query.filter(Conversation.agent_id == agent_id)
    return query.first()



def get_conversations(
    db: Session,
    agent_id: int | None = None,
):
    query = db.query(Conversation)
    if agent_id is not None:
        query = query.filter(Conversation.agent_id == agent_id)
    return query.order_by(Conversation.created_at.asc(), Conversation.id.asc()).all()



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
