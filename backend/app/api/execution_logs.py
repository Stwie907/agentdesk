from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.database import get_db

from app.crud.execution_log import get_logs

from app.schemas.execution_log import ExecutionLogRead



router = APIRouter(
    prefix="/execution-logs",
    tags=["execution-logs"]
)



@router.get(
    "/{execution_id}",
    response_model=list[ExecutionLogRead]
)
def read_logs(
    execution_id:int,
    db:Session=Depends(get_db)
):

    return get_logs(
        db,
        execution_id
    )

