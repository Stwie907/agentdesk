from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog


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


def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


def reset_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def create_test_execution():
    db = TestingSessionLocal()

    try:
        user = User(
            username="trace-api-user",
            email="trace-api@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Trace API Project",
            description="Execution trace API test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Trace API Agent",
            description="Agent used for execution trace API tests",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="Trace this execution",
            status="completed",
            output="Trace response",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        logs = [
            ExecutionLog(
                execution_id=execution.id,
                level="info",
                message="execution_started",
            ),
            ExecutionLog(
                execution_id=execution.id,
                level="info",
                message="planner_decision: tool=none",
            ),
            ExecutionLog(
                execution_id=execution.id,
                level="info",
                message="llm_called: model=qwen2.5:7b",
            ),
            ExecutionLog(
                execution_id=execution.id,
                level="info",
                message="llm_completed: model=qwen2.5:7b",
            ),
            ExecutionLog(
                execution_id=execution.id,
                level="info",
                message="execution_completed",
            ),
        ]

        db.add_all(logs)
        db.commit()

        return execution.id

    finally:
        db.close()


def test_get_execution_logs():
    reset_database()

    app.dependency_overrides[get_db] = override_get_db

    execution_id = create_test_execution()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/executions/{execution_id}/logs"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 5

        assert body[0]["execution_id"] == execution_id
        assert body[0]["level"] == "info"
        assert body[0]["message"] == "execution_started"

        messages = [
            item["message"]
            for item in body
        ]

        assert "planner_decision: tool=none" in messages
        assert "llm_called: model=qwen2.5:7b" in messages
        assert "llm_completed: model=qwen2.5:7b" in messages
        assert "execution_completed" in messages

    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)


def test_get_execution_logs_execution_not_found():
    reset_database()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            response = client.get(
                "/executions/999999/logs"
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found"
        }

    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
