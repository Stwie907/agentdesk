from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.user import User
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
        # create user first
        user = User(
            username="runtime-test-user",
            email="runtime@test.com"
        )

        db.add(user)
        db.commit()
        db.refresh(user)


        # create project with owner_id
        project = Project(
            name="runtime-test-project",
            description="runtime test project",
            owner_id=user.id
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


def test_get_execution_exposes_success_metadata():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="metadata-success-user",
            email="metadata-success@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="metadata-success-project",
            description="metadata success project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="metadata-success-agent",
            description="metadata success agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="successful execution",
            output="done",
            status="completed",
            retry_count=1,
            failure_type=None,
            failure_message=None,
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{execution.id}"
            )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == execution.id
        assert body["status"] == "completed"
        assert body["retry_count"] == 1
        assert body["failure_type"] is None
        assert body["failure_message"] is None

    finally:
        db.close()
        clear_test_db_override()


def test_get_execution_exposes_failure_metadata():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="metadata-failure-user",
            email="metadata-failure@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="metadata-failure-project",
            description="metadata failure project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="metadata-failure-agent",
            description="metadata failure agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="failed execution",
            output="runtime exploded",
            status="failed",
            retry_count=2,
            failure_type="runtime_error",
            failure_message="runtime exploded",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{execution.id}"
            )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == execution.id
        assert body["status"] == "failed"
        assert body["retry_count"] == 2
        assert body["failure_type"] == "runtime_error"
        assert body["failure_message"] == "runtime exploded"

    finally:
        db.close()
        clear_test_db_override()

def test_get_agent_executions_agent_not_found():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/agents/999999/executions"
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Agent not found"
        }

    finally:
        clear_test_db_override()

def test_get_agent_executions_exposes_metadata_and_order():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="history-metadata-user",
            email="history-metadata@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="history-metadata-project",
            description="history metadata project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="history-metadata-agent",
            description="history metadata agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution_old = Execution(
            agent_id=agent.id,
            input="old execution",
            output="old result",
            status="completed",
            retry_count=0,
            failure_type=None,
            failure_message=None,
        )

        execution_new = Execution(
            agent_id=agent.id,
            input="new execution",
            output="runtime exploded",
            status="failed",
            retry_count=2,
            failure_type="runtime_error",
            failure_message="runtime exploded",
        )

        db.add(execution_old)
        db.commit()
        db.refresh(execution_old)

        db.add(execution_new)
        db.commit()
        db.refresh(execution_new)

        with TestClient(app) as client:
            response = client.get(
                f"/agents/{agent.id}/executions"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 2

        assert body[0]["id"] == execution_new.id
        assert body[0]["status"] == "failed"
        assert body[0]["retry_count"] == 2
        assert body[0]["failure_type"] == "runtime_error"
        assert body[0]["failure_message"] == "runtime exploded"

        assert body[1]["id"] == execution_old.id
        assert body[1]["status"] == "completed"
        assert body[1]["retry_count"] == 0
        assert body[1]["failure_type"] is None
        assert body[1]["failure_message"] is None

    finally:
        db.close()
        clear_test_db_override()


def test_get_agent_executions_excludes_other_agents():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="history-isolation-user",
            email="history-isolation@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="history-isolation-project",
            description="history isolation project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent_1 = Agent(
            project_id=project.id,
            name="history-agent-1",
            description="first agent",
            model="qwen2.5:7b",
        )

        agent_2 = Agent(
            project_id=project.id,
            name="history-agent-2",
            description="second agent",
            model="qwen2.5:7b",
        )

        db.add_all([agent_1, agent_2])
        db.commit()
        db.refresh(agent_1)
        db.refresh(agent_2)

        execution_1 = Execution(
            agent_id=agent_1.id,
            input="agent one execution",
            output="one",
            status="completed",
        )

        execution_2 = Execution(
            agent_id=agent_2.id,
            input="agent two execution",
            output="two",
            status="completed",
        )

        db.add_all([execution_1, execution_2])
        db.commit()
        db.refresh(execution_1)
        db.refresh(execution_2)

        with TestClient(app) as client:
            response = client.get(
                f"/agents/{agent_1.id}/executions"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 1
        assert body[0]["id"] == execution_1.id
        assert body[0]["agent_id"] == agent_1.id

    finally:
        db.close()
        clear_test_db_override()

def test_retry_failed_execution_resets_runtime_state(monkeypatch):
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="manual-retry-user",
            email="manual-retry@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="manual-retry-project",
            description="manual retry project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="manual-retry-agent",
            description="manual retry agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="retry this execution",
            output="previous failure",
            status="failed",
            retry_count=2,
            failure_type="runtime_error",
            failure_message="previous failure",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        called = {"execution_id": None}

        def fake_execute_agent(execution_id):
            called["execution_id"] = execution_id

        monkeypatch.setattr(
            "app.api.executions.execute_agent",
            fake_execute_agent,
        )

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/retry"
            )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == execution.id
        assert body["agent_id"] == agent.id
        assert body["input"] == "retry this execution"
        assert body["status"] == "pending"

        assert body["output"] is None
        assert body["retry_count"] == 0
        assert body["failure_type"] is None
        assert body["failure_message"] is None

        assert called["execution_id"] == execution.id

    finally:
        db.close()
        clear_test_db_override()


def test_retry_execution_not_found():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/executions/999999/retry"
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found"
        }

    finally:
        clear_test_db_override()


def test_retry_completed_execution_is_rejected():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="completed-retry-user",
            email="completed-retry@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="completed-retry-project",
            description="completed retry project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="completed-retry-agent",
            description="completed retry agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="already completed",
            output="done",
            status="completed",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/retry"
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Only failed executions can be retried"
        }

    finally:
        db.close()
        clear_test_db_override()


def test_retry_pending_execution_is_rejected():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="pending-retry-user",
            email="pending-retry@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="pending-retry-project",
            description="pending retry project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="pending-retry-agent",
            description="pending retry agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="still pending",
            output=None,
            status="pending",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/retry"
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Only failed executions can be retried"
        }

    finally:
        db.close()
        clear_test_db_override()

def test_retry_running_execution_is_rejected():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="running-retry-user",
            email="running-retry@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="running-retry-project",
            description="running retry project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="running-retry-agent",
            description="running retry agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="currently running",
            output=None,
            status="running",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/retry"
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Only failed executions can be retried"
        }

    finally:
        db.close()
        clear_test_db_override()

def test_cancel_pending_execution():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="cancel-pending-user",
            email="cancel-pending@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="cancel-pending-project",
            description="cancel pending project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="cancel-pending-agent",
            description="cancel pending agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="cancel me",
            output=None,
            status="pending",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/cancel"
            )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == execution.id
        assert body["agent_id"] == agent.id
        assert body["input"] == "cancel me"
        assert body["status"] == "cancelled"

    finally:
        db.close()
        clear_test_db_override()


def test_cancel_execution_not_found():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/executions/999999/cancel"
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found"
        }

    finally:
        clear_test_db_override()


def test_cancel_running_execution_is_rejected():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="cancel-running-user",
            email="cancel-running@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="cancel-running-project",
            description="cancel running project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="cancel-running-agent",
            description="cancel running agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="already running",
            output=None,
            status="running",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/cancel"
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Only pending executions can be cancelled"
        }

    finally:
        db.close()
        clear_test_db_override()


def test_cancel_completed_execution_is_rejected():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="cancel-completed-user",
            email="cancel-completed@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="cancel-completed-project",
            description="cancel completed project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="cancel-completed-agent",
            description="cancel completed agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="already completed",
            output="done",
            status="completed",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/cancel"
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Only pending executions can be cancelled"
        }

    finally:
        db.close()
        clear_test_db_override()


def test_cancel_failed_execution_is_rejected():
    setup_test_db_override()
    reset_database()

    db = TestingSessionLocal()

    try:
        user = User(
            username="cancel-failed-user",
            email="cancel-failed@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="cancel-failed-project",
            description="cancel failed project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="cancel-failed-agent",
            description="cancel failed agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="already failed",
            output="failed",
            status="failed",
            retry_count=1,
            failure_type="runtime_error",
            failure_message="failed",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{execution.id}/cancel"
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Only pending executions can be cancelled"
        }

    finally:
        db.close()
        clear_test_db_override()
