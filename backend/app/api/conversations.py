from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session


from app.database import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse
)

from app.crud.conversation import (
    create_conversation,
    get_conversation,
    get_conversations,
    delete_conversation
)


router = APIRouter(
    prefix="/conversations",
    tags=["conversations"]
)



@router.post(
    "",
    response_model=ConversationResponse
)
def create(
    conversation: ConversationCreate,
    db: Session = Depends(get_db)
):

    return create_conversation(
        db,
        conversation
    )



@router.get(
    "",
    response_model=list[ConversationResponse]
)
def list_all(
    db: Session = Depends(get_db)
):

    return get_conversations(db)



@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse
)
def read(
    conversation_id:int,
    db: Session = Depends(get_db)
):

    result = get_conversation(
        db,
        conversation_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    return result



@router.delete(
    "/{conversation_id}"
)
def remove(
    conversation_id:int,
    db: Session = Depends(get_db)
):

    result = delete_conversation(
        db,
        conversation_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    return {
        "message":"deleted"
    }
