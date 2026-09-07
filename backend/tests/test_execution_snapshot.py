from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.execution import Execution
from app.models.execution_snapshot import ExecutionSnapshot
from app.crud.execution_snapshot import (
    create_execution_snapshot,
    get_execution_snapshot,
    update_execution_snapshot,
)
from app.schemas.execution_snapshot import ExecutionSnapshotCreate
from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.services.execution_snapshot import (
    serialize_execution_plan,
    deserialize_execution_plan,
    replay_execution_snapshot,
)
from app.services import agent_runner
from app.crud.execution import create_replay_execution
from app.services.execution_snapshot import (
    serialize_execution_plan,
    deserialize_execution_plan,
    replay_execution_snapshot,
    replay_execution,
)

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


def test_create_and_get_execution_snapshot():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="snapshot test input",
            status="completed",
            output="snapshot test output",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        snapshot_create = ExecutionSnapshotCreate(
            execution_id=execution.id,
            input_snapshot="snapshot test input",
            plan_snapshot='{"steps":[{"tool":"calculator"}]}',
            output_snapshot="snapshot test output",
        )

        created = create_execution_snapshot(
            db,
            snapshot_create,
        )

        assert created.id is not None
        assert created.execution_id == execution.id
        assert created.input_snapshot == "snapshot test input"
        assert created.plan_snapshot == '{"steps":[{"tool":"calculator"}]}'
        assert created.output_snapshot == "snapshot test output"
        assert created.created_at is not None

        loaded = get_execution_snapshot(
            db,
            execution.id,
        )

        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.execution_id == execution.id
        assert loaded.input_snapshot == "snapshot test input"
        assert loaded.plan_snapshot == '{"steps":[{"tool":"calculator"}]}'
        assert loaded.output_snapshot == "snapshot test output"

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_get_execution_snapshot_returns_none_when_missing():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        snapshot = get_execution_snapshot(
            db,
            999999,
        )

        assert snapshot is None

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_execution_allows_only_one_snapshot():
    from sqlalchemy.exc import IntegrityError

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="unique snapshot test",
            status="completed",
            output="done",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        first_snapshot = ExecutionSnapshot(
            execution_id=execution.id,
            input_snapshot="first input",
            plan_snapshot=None,
            output_snapshot="first output",
        )

        db.add(first_snapshot)
        db.commit()

        second_snapshot = ExecutionSnapshot(
            execution_id=execution.id,
            input_snapshot="second input",
            plan_snapshot=None,
            output_snapshot="second output",
        )

        db.add(second_snapshot)

        try:
            db.commit()
            assert False, "Expected duplicate execution snapshot to fail"
        except IntegrityError:
            db.rollback()

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_update_execution_snapshot():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="snapshot update test",
            status="completed",
            output="final output",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        created = create_execution_snapshot(
            db,
            ExecutionSnapshotCreate(
                execution_id=execution.id,
                input_snapshot="snapshot update test",
                plan_snapshot='{"steps":[{"tool":"calculator"}]}',
                output_snapshot=None,
            ),
        )

        assert created.output_snapshot is None

        updated = update_execution_snapshot(
            db,
            execution.id,
            output_snapshot="final output",
        )

        assert updated is not None
        assert updated.id == created.id
        assert updated.execution_id == execution.id

        # Existing snapshot data must remain unchanged.
        assert updated.input_snapshot == "snapshot update test"
        assert updated.plan_snapshot == '{"steps":[{"tool":"calculator"}]}'

        # Only the final output is attached.
        assert updated.output_snapshot == "final output"

        loaded = get_execution_snapshot(
            db,
            execution.id,
        )

        assert loaded is not None
        assert loaded.output_snapshot == "final output"

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_serialize_execution_plan():
    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": "1+1",
                },
                input="calculate 1+1",
            ),
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": {
                        "$step_output": 0,
                    },
                },
                input="use previous output",
            ),
        ]
    )

    serialized = serialize_execution_plan(plan)

    assert isinstance(serialized, str)

    import json

    data = json.loads(serialized)

    assert len(data["steps"]) == 2

    assert data["steps"][0] == {
        "tool": "calculator",
        "arguments": {
            "expression": "1+1",
        },
        "input": "calculate 1+1",
    }

    assert data["steps"][1] == {
        "tool": "calculator",
        "arguments": {
            "expression": {
                "$step_output": 0,
            },
        },
        "input": "use previous output",
    }

def test_persist_execution_plan_snapshot_is_retry_safe():
    from app.services.execution_snapshot import (
        persist_execution_plan_snapshot,
    )

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="retry snapshot test",
            status="running",
            output=None,
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        first_plan = ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool="calculator",
                    arguments={
                        "expression": "1+1",
                    },
                    input="calculate 1+1",
                )
            ]
        )

        first_snapshot = persist_execution_plan_snapshot(
            db,
            execution.id,
            "retry snapshot test",
            first_plan,
        )

        assert first_snapshot is not None
        first_snapshot_id = first_snapshot.id

        second_plan = ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool="calculator",
                    arguments={
                        "expression": "2+2",
                    },
                    input="calculate 2+2",
                )
            ]
        )

        second_snapshot = persist_execution_plan_snapshot(
            db,
            execution.id,
            "retry snapshot test",
            second_plan,
        )

        assert second_snapshot is not None

        # Retry must reuse the same snapshot row.
        assert second_snapshot.id == first_snapshot_id
        assert second_snapshot.execution_id == execution.id

        # Only one snapshot may exist for this execution.
        snapshots = (
            db.query(ExecutionSnapshot)
            .filter(
                ExecutionSnapshot.execution_id == execution.id
            )
            .all()
        )

        assert len(snapshots) == 1

        # The retry should replace the stored plan snapshot.
        import json

        stored_plan = json.loads(second_snapshot.plan_snapshot)

        assert stored_plan["steps"][0]["tool"] == "calculator"
        assert stored_plan["steps"][0]["arguments"] == {
            "expression": "2+2"
        }

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_run_agent_persists_complete_execution_snapshot(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="calculate 40+2",
            status="running",
            output=None,
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        monkeypatch.setattr(
            agent_runner,
            "SessionLocal",
            TestingSessionLocal,
        )

        monkeypatch.setattr(
            agent_runner,
            "plan_execution",
            lambda user_input, allowed_tools=None: ExecutionPlan(
                steps=[
                    ExecutionStep(
                        tool="calculator",
                        arguments={
                            "expression": "40+2",
                        },
                        input=user_input,
                    )
                ]
            ),
        )

        monkeypatch.setattr(
            "app.runtime.plan_executor.execute_tool",
            lambda tool_name, tool_input, allowed_tools=None: "42",
        )

        result = agent_runner.run_agent(
            "qwen2.5:7b",
            "calculate 40+2",
            execution_id=execution.id,
            allowed_tools=["calculator"],
        )

        assert result == "42"

        snapshot = get_execution_snapshot(
            db,
            execution.id,
        )

        assert snapshot is not None
        assert snapshot.execution_id == execution.id
        assert snapshot.input_snapshot == "calculate 40+2"
        assert snapshot.output_snapshot == "42"

        import json

        stored_plan = json.loads(snapshot.plan_snapshot)

        assert stored_plan == {
            "steps": [
                {
                    "tool": "calculator",
                    "arguments": {
                        "expression": "40+2",
                    },
                    "input": "calculate 40+2",
                }
            ]
        }

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_execution_plan_snapshot_round_trip():
    original_plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": "10+5",
                },
                input="calculate 10+5",
            ),
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": {
                        "$step_output": 0,
                    },
                },
                input="reuse previous output",
            ),
            ExecutionStep(
                tool=None,
                arguments={},
                input="finish without tool",
            ),
        ]
    )

    serialized = serialize_execution_plan(original_plan)

    restored_plan = deserialize_execution_plan(serialized)

    assert isinstance(restored_plan, ExecutionPlan)
    assert len(restored_plan.steps) == 3

    assert restored_plan.steps[0].tool == "calculator"
    assert restored_plan.steps[0].arguments == {
        "expression": "10+5",
    }
    assert restored_plan.steps[0].input == "calculate 10+5"

    assert restored_plan.steps[1].tool == "calculator"
    assert restored_plan.steps[1].arguments == {
        "expression": {
            "$step_output": 0,
        }
    }
    assert restored_plan.steps[1].input == "reuse previous output"

    assert restored_plan.steps[2].tool is None
    assert restored_plan.steps[2].arguments == {}
    assert restored_plan.steps[2].input == "finish without tool"

def test_deserialize_execution_plan_rejects_non_object_snapshot():
    import pytest

    with pytest.raises(
        ValueError,
        match="Execution plan snapshot must contain a JSON object",
    ):
        deserialize_execution_plan("[]")


def test_deserialize_execution_plan_rejects_missing_steps():
    import pytest

    with pytest.raises(
        ValueError,
        match="Execution plan snapshot must contain a steps list",
    ):
        deserialize_execution_plan("{}")


def test_deserialize_execution_plan_rejects_non_list_steps():
    import pytest

    with pytest.raises(
        ValueError,
        match="Execution plan snapshot must contain a steps list",
    ):
        deserialize_execution_plan(
            '{"steps": {"tool": "calculator"}}'
        )


def test_deserialize_execution_plan_rejects_non_object_step():
    import pytest

    with pytest.raises(
        ValueError,
        match="Execution plan snapshot step must be an object",
    ):
        deserialize_execution_plan(
            '{"steps": ["invalid-step"]}'
        )


def test_deserialize_execution_plan_rejects_non_object_arguments():
    import pytest

    with pytest.raises(
        ValueError,
        match="Execution plan snapshot step arguments must be an object",
    ):
        deserialize_execution_plan(
            """
            {
                "steps": [
                    {
                        "tool": "calculator",
                        "arguments": "invalid",
                        "input": "calculate"
                    }
                ]
            }
            """
        )
def test_replay_execution_snapshot_executes_stored_plan(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="replay snapshot test",
            status="completed",
            output="42",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        plan = ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool="calculator",
                    arguments={
                        "expression": "40+2",
                    },
                    input="calculate 40+2",
                )
            ]
        )

        create_execution_snapshot(
            db,
            ExecutionSnapshotCreate(
                execution_id=execution.id,
                input_snapshot=execution.input,
                plan_snapshot=serialize_execution_plan(plan),
                output_snapshot="42",
            ),
        )

        monkeypatch.setattr(
            "app.runtime.plan_executor.execute_tool",
            lambda tool_name, tool_input, allowed_tools=None: "42",
        )

        result = replay_execution_snapshot(
            db,
            execution.id,
            allowed_tools=["calculator"],
        )

        assert result.last_output == "42"
        assert len(result.steps) == 1
        assert result.steps[0].output == "42"

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_replay_execution_snapshot_rejects_missing_snapshot():
    import pytest

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        with pytest.raises(
            ValueError,
            match="Execution snapshot not found",
        ):
            replay_execution_snapshot(
                db,
                999999,
            )
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_replay_execution_snapshot_rejects_missing_plan_snapshot():
    import pytest

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="missing plan snapshot test",
            status="completed",
            output="done",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        create_execution_snapshot(
            db,
            ExecutionSnapshotCreate(
                execution_id=execution.id,
                input_snapshot=execution.input,
                plan_snapshot=None,
                output_snapshot="done",
            ),
        )

        with pytest.raises(
            ValueError,
            match="Execution snapshot does not contain a plan",
        ):
            replay_execution_snapshot(
                db,
                execution.id,
            )
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_create_replay_execution_preserves_source_relationship():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        original = Execution(
            agent_id=1,
            input="original replay input",
            output="original output",
            status="completed",
            retry_count=2,
            failure_type=None,
            failure_message=None,
        )

        db.add(original)
        db.commit()
        db.refresh(original)

        replay = create_replay_execution(
            db,
            original,
        )

        assert replay.id != original.id
        assert replay.agent_id == original.agent_id
        assert replay.input == original.input

        assert replay.status == "pending"
        assert replay.output is None

        assert replay.retry_count == 0
        assert replay.failure_type is None
        assert replay.failure_message is None

        assert replay.replay_of_execution_id == original.id

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_replay_execution_creates_new_completed_execution(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        original = Execution(
            agent_id=1,
            input="replay service test",
            output="original result",
            status="completed",
        )

        db.add(original)
        db.commit()
        db.refresh(original)

        plan = ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool="calculator",
                    arguments={
                        "expression": "40+2",
                    },
                    input="calculate 40+2",
                )
            ]
        )

        create_execution_snapshot(
            db,
            ExecutionSnapshotCreate(
                execution_id=original.id,
                input_snapshot=original.input,
                plan_snapshot=serialize_execution_plan(plan),
                output_snapshot=original.output,
            ),
        )

        monkeypatch.setattr(
            "app.runtime.plan_executor.execute_tool",
            lambda tool_name, tool_input, allowed_tools=None: "42",
        )

        replay = replay_execution(
            db,
            original,
            allowed_tools=["calculator"],
        )

        assert replay.id != original.id
        assert replay.replay_of_execution_id == original.id

        assert replay.agent_id == original.agent_id
        assert replay.input == original.input

        assert replay.status == "completed"
        assert replay.output == "42"

        assert replay.retry_count == 0
        assert replay.failure_type is None
        assert replay.failure_message is None

        db.refresh(original)

        assert original.status == "completed"
        assert original.output == "original result"

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
