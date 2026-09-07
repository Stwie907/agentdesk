from sqlalchemy.orm import Session

from app.models.execution_snapshot import ExecutionSnapshot
from app.schemas.execution_snapshot import ExecutionSnapshotCreate


def create_execution_snapshot(
    db: Session,
    snapshot: ExecutionSnapshotCreate,
):
    """
    Persist one Runtime V4 execution snapshot.

    Each execution owns at most one snapshot. The database-level unique
    constraint on execution_id enforces that invariant.
    """

    db_snapshot = ExecutionSnapshot(
        execution_id=snapshot.execution_id,
        input_snapshot=snapshot.input_snapshot,
        plan_snapshot=snapshot.plan_snapshot,
        output_snapshot=snapshot.output_snapshot,
    )

    db.add(db_snapshot)
    db.commit()
    db.refresh(db_snapshot)

    return db_snapshot


def get_execution_snapshot(
    db: Session,
    execution_id: int,
):
    """
    Return the persisted Runtime V4 snapshot for an execution.

    Returns None when the execution does not have a snapshot.
    """

    return (
        db.query(ExecutionSnapshot)
        .filter(
            ExecutionSnapshot.execution_id == execution_id
        )
        .first()
    )

def update_execution_snapshot(
    db: Session,
    execution_id: int,
    *,
    input_snapshot: str | None = None,
    plan_snapshot: str | None = None,
    output_snapshot: str | None = None,
):
    """
    Update an existing Runtime V4 execution snapshot.

    Only explicitly provided values are updated. This allows the runtime
    to persist the input/plan before execution and attach the final output
    later without creating a second snapshot for the same execution.
    """

    snapshot = get_execution_snapshot(
        db,
        execution_id,
    )

    if snapshot is None:
        return None

    if input_snapshot is not None:
        snapshot.input_snapshot = input_snapshot

    if plan_snapshot is not None:
        snapshot.plan_snapshot = plan_snapshot

    if output_snapshot is not None:
        snapshot.output_snapshot = output_snapshot

    db.commit()
    db.refresh(snapshot)

    return snapshot
