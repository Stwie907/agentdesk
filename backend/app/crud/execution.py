from sqlalchemy.orm import Session

from app.models.execution import Execution
from app.schemas.execution import ExecutionCreate


def create_execution(
    db: Session,
    execution: ExecutionCreate
):

    db_execution = Execution(
    agent_id=execution.agent_id,
    input=execution.input,
    status="pending"
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


def get_executions_by_agent(
    db: Session,
    agent_id: int
):
    return (
        db.query(Execution)
        .filter(Execution.agent_id == agent_id)
        .order_by(
            Execution.created_at.desc(),
            Execution.id.desc(),
        )
        .all()
    )

def create_replay_execution(
    db: Session,
    source_execution: Execution,
):
    """
    Create a new execution that replays a previous execution snapshot.

    The original execution remains unchanged. The new execution records
    its provenance through replay_of_execution_id.
    """

    db_execution = Execution(
        agent_id=source_execution.agent_id,
        input=source_execution.input,
        status="pending",
        replay_of_execution_id=source_execution.id,
    )

    db.add(db_execution)
    db.commit()
    db.refresh(db_execution)

    return db_execution
