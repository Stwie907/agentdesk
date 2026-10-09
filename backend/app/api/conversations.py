from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.crud.agent import get_agent
from app.crud.conversation import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversations,
    update_conversation_title,
)
from app.database import get_db
from app.schemas.conversation import ConversationCreateRequest, ConversationResponse, ConversationUpdateRequest


router = APIRouter(prefix="/conversations", tags=["conversations"])


def require_conversation(db: Session, conversation_id: int, agent_id: int | None = None):
    conversation = get_conversation(db, conversation_id, agent_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("", response_model=ConversationResponse)
def create(conversation: ConversationCreateRequest, db: Session = Depends(get_db)):
    if get_agent(db, conversation.agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return create_conversation(db, conversation)


@router.get("", response_model=list[ConversationResponse])
def list_all(db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    if agent_id is not None and get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return get_conversations(db, agent_id)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def read(conversation_id: Annotated[int, Path(gt=0)], db: Session = Depends(get_db),
         agent_id: Annotated[int | None, Query(gt=0)] = None):
    return require_conversation(db, conversation_id, agent_id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename(conversation_id: Annotated[int, Path(gt=0)], request: ConversationUpdateRequest,
           db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    conversation = require_conversation(db, conversation_id, agent_id)
    return update_conversation_title(db, conversation, request.title)


@router.delete("/{conversation_id}")
def remove(conversation_id: Annotated[int, Path(gt=0)], db: Session = Depends(get_db),
           agent_id: Annotated[int | None, Query(gt=0)] = None):
    require_conversation(db, conversation_id, agent_id)
    delete_conversation(db, conversation_id)
    return {"message": "deleted"}
