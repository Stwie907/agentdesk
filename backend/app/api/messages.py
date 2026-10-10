from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from app.api.conversations import require_conversation
from app.crud.message import create_message, get_message_cursor, get_message_page, get_messages
from app.database import get_db
from app.schemas.chat import ChatResponse, ConversationChatRequest
from app.schemas.message import MessageCreate, MessagePageResponse, MessageResponse
from app.schemas.message_search import MessageRoleFilter, MessageSearchResponse
from app.services.conversation_service import run_conversation_chat
from app.services.message_search import search_messages


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


@router.get("/{conversation_id}/messages/search", response_model=MessageSearchResponse)
def search_saved_messages(
    conversation_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    agent_id: Annotated[int, Query(gt=0, le=9223372036854775807)],
    query: Annotated[str, Query(min_length=1, max_length=200)],
    response: Response,
    db: Session = Depends(get_db),
    role: MessageRoleFilter | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    normalized = query.strip()
    if not normalized or "\x00" in normalized:
        raise HTTPException(status_code=422, detail="Enter a message search query of 1 to 200 characters without NUL.")
    require_conversation(db, conversation_id, agent_id)
    items, total = search_messages(db, conversation_id, normalized, role, limit, offset)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return MessageSearchResponse(
        conversation_id=conversation_id, agent_id=agent_id, query=normalized, role=role,
        limit=limit, offset=offset, total=total, has_more=offset + len(items) < total, items=items,
    )


@router.get("/{conversation_id}/messages/{message_id}", response_model=MessageResponse)
def read_saved_message(
    conversation_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    message_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    agent_id: Annotated[int, Query(gt=0, le=9223372036854775807)],
    response: Response,
    db: Session = Depends(get_db),
):
    require_conversation(db, conversation_id, agent_id)
    message = get_message_cursor(db, conversation_id, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found in this conversation")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return message


@router.post("/{conversation_id}/chat", response_model=ChatResponse)
def chat(conversation_id: Annotated[int, Path(gt=0)], request: ConversationChatRequest,
         db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    require_conversation(db, conversation_id, agent_id)
    execution = run_conversation_chat(db, conversation_id, request.message)
    return ChatResponse(execution_id=execution.id, response=execution.output or "", status=execution.status)
