from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.project import ProjectCreate
from app.crud.project import create_project, get_project


router = APIRouter()


@router.post("/projects")
def create(
    project: ProjectCreate,
    db: Session = Depends(get_db)
):
    return create_project(db, project)


@router.get("/projects/{project_id}")
def read(
    project_id: int,
    db: Session = Depends(get_db)
):
    return get_project(db, project_id)
