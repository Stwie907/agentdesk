import json
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.crud.execution_snapshot import (
    create_execution_snapshot,
    get_execution_snapshot,
    update_execution_snapshot,
)
from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.schemas.execution_snapshot import ExecutionSnapshotCreate
from app.runtime.plan_executor import execute_plan
from app.crud.execution import create_replay_execution
from app.constants import CURRENT_EXECUTION_SNAPSHOT_VERSION
from app.services.execution_failure import classify_failure

def serialize_execution_plan(
    plan: ExecutionPlan,
) -> str:
    """
    Serialize a Runtime V4 ExecutionPlan into a deterministic JSON snapshot.

    Dataclass serialization preserves the structured plan, including
    step tools, arguments, inputs, and step-output references.
    """

    return json.dumps(
        asdict(plan),
        ensure_ascii=False,
        sort_keys=True,
    )

def deserialize_execution_plan(
    plan_snapshot: str,
) -> ExecutionPlan:
    """
    Restore a Runtime V4 ExecutionPlan from a persisted JSON snapshot.

    The snapshot is expected to have been produced by
    serialize_execution_plan(). Step arguments are restored unchanged,
    including nested $step_output references used for output chaining.
    """
    try:
        data = json.loads(plan_snapshot)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid execution plan snapshot JSON"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("Execution plan snapshot must contain a JSON object")

    raw_steps = data.get("steps")

    if not isinstance(raw_steps, list):
        raise ValueError("Execution plan snapshot must contain a steps list")

    steps = []

    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise ValueError("Execution plan snapshot step must be an object")

        arguments = raw_step.get("arguments", {})

        if not isinstance(arguments, dict):
            raise ValueError("Execution plan snapshot step arguments must be an object")

        steps.append(
            ExecutionStep(
                tool=raw_step.get("tool"),
                arguments=arguments,
                input=raw_step.get("input", ""),
            )
        )

    return ExecutionPlan(
        steps=steps,
    )

def _load_replayable_execution_plan(
    db: Session,
    execution_id: int,
) -> ExecutionPlan:
    """
    Load and validate the persisted Runtime V4 plan used for replay.

    Validation happens before a replay execution is created so invalid,
    incompatible, or malformed snapshots cannot leave orphaned replay
    execution records behind.
    """

    snapshot = get_execution_snapshot(
        db,
        execution_id,
    )

    if snapshot is None:
        raise ValueError("Execution snapshot not found")

    if snapshot.snapshot_version != CURRENT_EXECUTION_SNAPSHOT_VERSION:
        raise ValueError(
            "Unsupported execution snapshot version: "
            f"{snapshot.snapshot_version}; "
            f"supported version: {CURRENT_EXECUTION_SNAPSHOT_VERSION}"
        )

    if not snapshot.plan_snapshot:
        raise ValueError("Execution snapshot does not contain a plan")

    return deserialize_execution_plan(
        snapshot.plan_snapshot,
    )

def persist_execution_plan_snapshot(
    db: Session,
    execution_id: int,
    input_snapshot: str,
    plan: ExecutionPlan,
):
    """
    Persist the input and Runtime V4 execution plan for one execution.

    The operation is retry-safe. If a snapshot already exists for the
    execution, its input and plan are updated instead of inserting a
    duplicate row.
    """

    plan_snapshot = serialize_execution_plan(plan)

    existing = get_execution_snapshot(
        db,
        execution_id,
    )

    if existing is None:
        return create_execution_snapshot(
            db,
            ExecutionSnapshotCreate(
                execution_id=execution_id,
                input_snapshot=input_snapshot,
                plan_snapshot=plan_snapshot,
                output_snapshot=None,
            ),
        )

    return update_execution_snapshot(
        db,
        execution_id,
        input_snapshot=input_snapshot,
        plan_snapshot=plan_snapshot,
    )


def persist_execution_output_snapshot(
    db: Session,
    execution_id: int,
    output_snapshot: str,
):
    """
    Attach the final runtime output to an existing execution snapshot.

    Returns None when no plan snapshot has been persisted yet.
    """

    return update_execution_snapshot(
        db,
        execution_id,
        output_snapshot=output_snapshot,
    )

def replay_execution_snapshot(
    db: Session,
    execution_id: int,
    allowed_tools: list[str] | None = None,
):
    """
    Replay a persisted Runtime V4 execution plan.

    Replay uses the stored plan snapshot directly instead of invoking
    the planner again. This keeps replay tied to the original execution
    plan rather than generating a new plan from current runtime state.
    """
    plan = _load_replayable_execution_plan(
        db,
        execution_id,
    )

    return execute_plan(
        plan,
        allowed_tools=allowed_tools,
    )

def replay_execution(
    db: Session,
    source_execution,
    allowed_tools: list[str] | None = None,
):
    """
    Create and execute a new replay execution from a persisted snapshot.

    The source execution remains unchanged. The replay execution records
    its provenance through replay_of_execution_id and executes the stored
    Runtime V4 plan instead of invoking the planner again.
    """
    # Validate the persisted snapshot before creating a replay execution.
    # Compatibility or snapshot-data failures must not leave a pending
    # replay execution record behind.
    _load_replayable_execution_plan(
        db,
        source_execution.id,
    )

    replay_execution = create_replay_execution(
        db,
        source_execution,
    )

    try:
        result = replay_execution_snapshot(
            db,
            source_execution.id,
            allowed_tools=allowed_tools,
        )
    except Exception as exc:
        failure = classify_failure(exc)

        replay_execution.output = None
        replay_execution.status = "failed"
        replay_execution.failure_type = failure.failure_type.value
        replay_execution.failure_message = failure.message

        db.commit()
        db.refresh(replay_execution)

        raise

    replay_execution.output = (
        str(result.last_output)
        if result.last_output is not None
        else None
    )
    replay_execution.status = "completed"
    replay_execution.failure_type = None
    replay_execution.failure_message = None

    db.commit()
    db.refresh(replay_execution)

    return replay_execution
