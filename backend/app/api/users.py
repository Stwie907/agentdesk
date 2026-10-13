from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import UserCreate
from app.crud.user import create_user, get_user


router = APIRouter()


@router.post("/users")
def create(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    return create_user(db, user)


@router.get("/users/{user_id}")
def read(
    user_id: int,
    db: Session = Depends(get_db)
):
    return get_user(db, user_id)
