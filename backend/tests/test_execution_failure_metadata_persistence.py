import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.execution import Execution
from app.workers import execution_worker


TEST_DATABASE_URL = "sqlite:///"

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


def create_execution():
    db = TestingSessionLocal()

    user = User(
        username="metadata-user",
        email="metadata@example.com",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    project = Project(
        name="metadata-project",
        description="Execution metadata test project",
        owner_id=user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    agent = Agent(
        project_id=project.id,
        name="metadata-agent",
        description="Execution metadata test agent",
        model="qwen2.5:7b",
        allowed_tools=json.dumps(["calculator"]),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    execution = Execution(
        agent_id=agent.id,
        input="metadata test",
        status="pending",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    execution_id = execution.id
    db.close()

    return execution_id


def test_successful_execution_persists_clean_metadata(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    execution_id = create_execution()

    monkeypatch.setattr(
        execution_worker,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        execution_worker,
        "build_memory_context",
        lambda *args, **kwargs: "",
    )

    monkeypatch.setattr(
        execution_worker,
        "run_agent",
        lambda *args, **kwargs: "success",
    )

    execution_worker.execute_agent(execution_id)

    db = TestingSessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        assert execution is not None
        assert execution.status == "completed"
        assert execution.retry_count == 0
        assert execution.failure_type is None
        assert execution.failure_message is None

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_failed_execution_persists_failure_metadata(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    execution_id = create_execution()

    monkeypatch.setattr(
        execution_worker,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        execution_worker,
        "build_memory_context",
        lambda *args, **kwargs: "",
    )

    def fake_run_agent(*args, **kwargs):
        raise RuntimeError("runtime failed")

    monkeypatch.setattr(
        execution_worker,
        "run_agent",
        fake_run_agent,
    )

    execution_worker.execute_agent(execution_id)

    db = TestingSessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        assert execution is not None
        assert execution.status == "failed"
        assert execution.retry_count == 0
        assert execution.failure_type == "runtime_error"
        assert execution.failure_message == "runtime failed"

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_retryable_failure_persists_retry_count(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    execution_id = create_execution()

    monkeypatch.setattr(
        execution_worker,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        execution_worker,
        "build_memory_context",
        lambda *args, **kwargs: "",
    )

    calls = {
        "count": 0,
    }

    def fake_run_agent(*args, **kwargs):
        calls["count"] += 1

        if calls["count"] < 3:
            raise TimeoutError("temporary timeout")

        return "recovered"

    monkeypatch.setattr(
        execution_worker,
        "run_agent",
        fake_run_agent,
    )

    execution_worker.execute_agent(execution_id)

    db = TestingSessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        assert execution is not None
        assert execution.status == "completed"
        assert execution.retry_count == 2
        assert execution.failure_type is None
        assert execution.failure_message is None

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_retry_exhaustion_persists_retry_and_failure_metadata(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    execution_id = create_execution()

    monkeypatch.setattr(
        execution_worker,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        execution_worker,
        "build_memory_context",
        lambda *args, **kwargs: "",
    )

    calls = {
        "count": 0,
    }

    def fake_run_agent(*args, **kwargs):
        calls["count"] += 1
        raise TimeoutError("timeout after retries")

    monkeypatch.setattr(
        execution_worker,
        "run_agent",
        fake_run_agent,
    )

    execution_worker.execute_agent(execution_id)

    db = TestingSessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        assert execution is not None

        # Initial attempt + 2 retries.
        assert calls["count"] == 3

        # Final execution state.
        assert execution.status == "failed"

        # Both retries must be persisted.
        assert execution.retry_count == 2

        # Final structured failure must also be persisted.
        assert execution.failure_type == "timeout"
        assert execution.failure_message == "timeout after retries"

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
