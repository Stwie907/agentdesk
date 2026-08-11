from sqlalchemy.orm import Session

from app.models.execution_log import ExecutionLog


def create_log(
    db: Session,
    execution_id: int,
    message: str,
    level: str = "info"
):

    log = ExecutionLog(
        execution_id=execution_id,
        message=message,
        level=level
    )

    db.add(log)

    db.commit()

    db.refresh(log)

    return log



def get_logs(
    db: Session,
    execution_id: int
):

    return (
        db.query(ExecutionLog)
        .filter(
            ExecutionLog.execution_id == execution_id
        )
        .all()
    )
