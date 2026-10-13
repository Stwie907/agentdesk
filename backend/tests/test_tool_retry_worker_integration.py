import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog
from app.runtime.executor import ToolExecutionError
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


def test_worker_does_not_retry_tool_execution_error(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="tool-retry-user",
            email="tool-retry@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="tool-retry-project",
            description="Tool retry integration test project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="tool-retry-agent",
            description="Tool retry integration test agent",
            model="qwen2.5:7b",
            allowed_tools=json.dumps(["calculator"]),
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="trigger tool failure",
            status="pending",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        execution_id = execution.id

        monkeypatch.setattr(
            execution_worker,
            "SessionLocal",
            TestingSessionLocal,
        )

        calls = {"count": 0}

        def fake_run_agent(*args, **kwargs):
            calls["count"] += 1
            raise ToolExecutionError(
                "calculator",
                "boom",
            )

        monkeypatch.setattr(
            execution_worker,
            "run_agent",
            fake_run_agent,
        )

        execution_worker.execute_agent(execution_id)

        db.expire_all()

        saved_execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        assert saved_execution is not None
        assert saved_execution.status == "failed"
        assert calls["count"] == 1

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution_id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [log.message for log in logs]

        assert not any(
            message.startswith("execution_retrying")
            for message in messages
        )

        failed_messages = [
            message
            for message in messages
            if message.startswith("execution_failed")
        ]

        assert len(failed_messages) == 1
        assert "type=tool_execution_error" in failed_messages[0]
        assert "retryable=false" in failed_messages[0]

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
