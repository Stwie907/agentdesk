from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.api.conversations import require_conversation
from app.crud.message import create_message, get_message_cursor, get_message_page, get_messages
from app.database import get_db
from app.schemas.chat import ChatResponse, ConversationChatRequest
from app.schemas.message import MessageCreate, MessagePageResponse, MessageResponse
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


@router.get("/{conversation_id}/messages/page", response_model=MessagePageResponse)
def page_messages(
    conversation_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    agent_id: Annotated[int, Query(gt=0, le=9223372036854775807)],
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before_id: Annotated[int | None, Query(gt=0, le=9223372036854775807)] = None,
):
    require_conversation(db, conversation_id, agent_id)
    before = None
    if before_id is not None:
        before = get_message_cursor(db, conversation_id, before_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Message cursor not found in this conversation")
    items, has_more = get_message_page(db, conversation_id, limit, before)
    return MessagePageResponse(
        conversation_id=conversation_id, agent_id=agent_id, limit=limit, before_id=before_id,
        has_more=has_more, next_before_id=items[0].id if has_more else None,
        items=[MessageResponse.model_validate(row) for row in items],
    )


@router.post("/{conversation_id}/chat", response_model=ChatResponse)
def chat(conversation_id: Annotated[int, Path(gt=0)], request: ConversationChatRequest,
         db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    require_conversation(db, conversation_id, agent_id)
    execution = run_conversation_chat(db, conversation_id, request.message)
    return ChatResponse(execution_id=execution.id, response=execution.output or "", status=execution.status)
