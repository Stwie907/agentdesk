from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.conversations import require_conversation
from app.crud.message import create_message, get_messages
from app.database import get_db
from app.schemas.chat import ChatResponse, ConversationChatRequest
from app.schemas.message import MessageCreate, MessageResponse
from app.services.conversation_service import run_conversation_chat


router = APIRouter(prefix="/conversations", tags=["messages"])


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
def create(conversation_id: Annotated[int, Path(gt=0)], message: MessageCreate,
           db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    require_conversation(db, conversation_id, agent_id)
    return create_message(db, conversation_id, message)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(conversation_id: Annotated[int, Path(gt=0)], db: Session = Depends(get_db),
                  agent_id: Annotated[int | None, Query(gt=0)] = None):
    require_conversation(db, conversation_id, agent_id)
    return get_messages(db, conversation_id)


@router.post("/{conversation_id}/chat", response_model=ChatResponse)
def chat(conversation_id: Annotated[int, Path(gt=0)], request: ConversationChatRequest,
         db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    require_conversation(db, conversation_id, agent_id)
    execution = run_conversation_chat(db, conversation_id, request.message)
    return ChatResponse(execution_id=execution.id, response=execution.output or "", status=execution.status)
