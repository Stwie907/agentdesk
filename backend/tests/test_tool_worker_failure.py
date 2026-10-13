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
from app.tools.base import ToolArgumentsError
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


def test_worker_persists_tool_arguments_failure(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="tool-error-test-user",
            email="tool-error-test@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)


        project = Project(
            name="tool-error-test-project",
            description="Project for tool error worker tests",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)


        agent = Agent(
            project_id=project.id,
            name="tool-error-test-agent",
            description="Agent for tool error worker tests",
            model="qwen2.5:7b",
            allowed_tools=json.dumps(["calculator"]),
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="calculate something invalid",
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

        def fake_run_agent(*args, **kwargs):
            raise ToolArgumentsError(
                "calculator arguments are invalid"
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
        assert saved_execution.output == (
            "calculator arguments are invalid"
        )

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution_id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [log.message for log in logs]

        failed_messages = [
            message
            for message in messages
            if message.startswith("execution_failed")
        ]

        assert len(failed_messages) == 1

        failed_message = failed_messages[0]

        assert "type=tool_arguments_error" in failed_message
        assert "retryable=false" in failed_message
        assert "calculator arguments are invalid" in failed_message

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
