from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.agent import Agent
from app.models.project import Project
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog


# ---------------------------------
# Isolated in-memory test database
# ---------------------------------

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


def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()

def setup_test_db_override():
    app.dependency_overrides[get_db] = override_get_db


def clear_test_db_override():
    app.dependency_overrides.pop(get_db, None)


def reset_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def create_test_data():
    db = TestingSessionLocal()

    try:
        # create project first
        project = Project(
            name="runtime-test-project",
            description="runtime test project"
        )

        db.add(project)
        db.commit()
        db.refresh(project)


        # create agent with project_id
        agent = Agent(
            project_id=project.id,
            name="runtime-test-agent",
            description="Agent used by runtime API tests",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)


        # create executions
        execution_1 = Execution(
            agent_id=agent.id,
            input="first test execution",
            output="first result",
            status="completed",
        )

        execution_2 = Execution(
            agent_id=agent.id,
            input="second test execution",
            output=None,
            status="failed",
        )


        db.add_all(
            [
                execution_1,
                execution_2
            ]
        )

        db.commit()

        db.refresh(execution_1)
        db.refresh(execution_2)


        # create logs
        log_1 = ExecutionLog(
            execution_id=execution_1.id,
            message="Execution started",
        )

        log_2 = ExecutionLog(
            execution_id=execution_1.id,
            message="Execution completed",
        )


        db.add_all(
            [
                log_1,
                log_2
            ]
        )

        db.commit()


        return {
            "agent_id": agent.id,
            "execution_id": execution_1.id,
        }


    finally:
        db.close()

def test_get_execution_success():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}"
            )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == data["execution_id"]
        assert body["agent_id"] == data["agent_id"]
        assert body["input"] == "first test execution"
        assert body["output"] == "first result"
        assert body["status"] == "completed"
    finally:
        clear_test_db_override()


def test_get_execution_not_found():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.get("/executions/999999")

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found"
        }
    finally:
        clear_test_db_override()


def test_get_agent_executions():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/agents/{data['agent_id']}/executions"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 2

        assert all(
            execution["agent_id"] == data["agent_id"]
            for execution in body
        )

        assert {
            execution["status"]
            for execution in body
        } == {
            "completed",
            "failed",
        }
    finally:
        clear_test_db_override()


def test_get_execution_logs():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/execution-logs/{data['execution_id']}"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 2

        assert body[0]["execution_id"] == data["execution_id"]
        assert body[0]["message"] == "Execution started"

        assert body[1]["execution_id"] == data["execution_id"]
        assert body[1]["message"] == "Execution completed"
    finally:
        clear_test_db_override()
