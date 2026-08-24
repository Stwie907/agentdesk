from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db

from app.crud.message import (
    create_message,
    get_messages,
)

from app.schemas.message import (
    MessageCreate,
    MessageResponse,
)

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
)

from app.services.conversation_service import run_conversation_chat


router = APIRouter(
    prefix="/conversations",
    tags=["messages"],
)


# ---------------------------------------------------------
# Create a message only
# ---------------------------------------------------------

@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
)
def create(
    conversation_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
):
    return create_message(
        db,
        conversation_id,
        message,
    )


# ---------------------------------------------------------
# List conversation messages
# ---------------------------------------------------------

@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
):
    return get_messages(
        db,
        conversation_id,
    )


# ---------------------------------------------------------
# Conversation + Agent Runtime
# ---------------------------------------------------------

@router.post(
    "/{conversation_id}/chat",
    response_model=ChatResponse,
)
def chat(
    conversation_id: int,
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    execution = run_conversation_chat(
        db,
        conversation_id,
        request.message,
    )

    if not execution:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return ChatResponse(
        execution_id=execution.id,
        response=execution.output or "",
        status=execution.status,
    )
