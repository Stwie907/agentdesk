from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.crud.message import create_message, get_messages
from app.schemas.message import MessageCreate, MessageResponse


router = APIRouter(
    prefix="/conversations",
    tags=["messages"]
)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse
)
def create(
    conversation_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db)
):
    return create_message(
        db,
        conversation_id,
        message
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageResponse]
)
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    return get_messages(
        db,
        conversation_id
    )
