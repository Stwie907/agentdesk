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


def get_conversation_page(db: Session, agent_id: int, query: str, limit: int, offset: int):
    rows = db.query(Conversation).filter(Conversation.agent_id == agent_id)
    if query:
        # User text is a literal substring, including %, _, and the escape character.
        rows = rows.filter(Conversation.title.icontains(query, autoescape=True))
    total = rows.count()
    items = rows.order_by(Conversation.created_at.desc(), Conversation.id.desc()).offset(offset).limit(limit).all()
    return items, total



def update_conversation_title(db: Session, conversation: Conversation, title: str):
    conversation.title = title
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(conversation)
    return conversation


def delete_conversation(
    db: Session,
    conversation_id: int
):

    conversation = get_conversation(
        db,
        conversation_id
    )

    if conversation:
        try:
            # The ORM relationship deletes messages in the same transaction.
            db.delete(conversation)
            db.commit()
        except Exception:
            db.rollback()
            raise

    return conversation
