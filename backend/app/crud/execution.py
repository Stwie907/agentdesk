from sqlalchemy.orm import Session

from app.models.execution import Execution
from app.schemas.execution import ExecutionCreate


def create_execution(
    db: Session,
    execution: ExecutionCreate
):

    db_execution = Execution(
        agent_id=execution.agent_id,
        input=execution.input
    )

    db.add(db_execution)

    db.commit()

    db.refresh(db_execution)

    return db_execution



def get_execution(
    db: Session,
    execution_id: int
):

    return (
        db.query(Execution)
        .filter(
            Execution.id == execution_id
        )
        .first()
    )
