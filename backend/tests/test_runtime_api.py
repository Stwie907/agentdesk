from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.constants import CURRENT_EXECUTION_SNAPSHOT_VERSION
from app.models.user import User
from app.models.agent import Agent
from app.models.project import Project
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog
from app.models.execution_snapshot import ExecutionSnapshot

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

def test_get_execution_trace_returns_only_runtime_v4_events():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        db.add_all(
            [
                ExecutionLog(
                    execution_id=data["execution_id"],
                    message="plan_started",
                ),
                ExecutionLog(
                    execution_id=data["execution_id"],
                    message="step_started: step=0 tool=calculator",
                ),
                ExecutionLog(
                    execution_id=data["execution_id"],
                    message="step_completed: step=0 tool=calculator",
                ),
                ExecutionLog(
                    execution_id=data["execution_id"],
                    message="plan_completed",
                ),
            ]
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/trace"
            )

        assert response.status_code == 200

        body = response.json()

        assert [
            item["message"]
            for item in body
        ] == [
            "plan_started",
            "step_started: step=0 tool=calculator",
            "step_completed: step=0 tool=calculator",
            "plan_completed",
        ]

        assert all(
            item["execution_id"] == data["execution_id"]
            for item in body
        )

    finally:
        db.close()
        clear_test_db_override()


def test_get_execution_trace_returns_empty_list_without_runtime_v4_events():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/trace"
            )

        assert response.status_code == 200
        assert response.json() == []

    finally:
        clear_test_db_override()


def test_get_execution_trace_not_found():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/executions/999999/trace"
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found"
        }

    finally:
        clear_test_db_override()

def test_get_execution_trace_returns_structured_step_fields():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        db.add(
            ExecutionLog(
                execution_id=data["execution_id"],
                message="step_started: step=0 tool=calculator",
            )
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/trace"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 1
        assert body[0]["event"] == "step_started"
        assert body[0]["step_index"] == 0
        assert body[0]["tool"] == "calculator"
        assert body[0]["error"] is None
        assert body[0]["message"] == (
            "step_started: step=0 tool=calculator"
        )

    finally:
        db.close()
        clear_test_db_override()


def test_get_execution_trace_returns_structured_failure_fields():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        db.add(
            ExecutionLog(
                execution_id=data["execution_id"],
                message=(
                    "step_failed: step=1 tool=calculator; "
                    "error=calculator exploded"
                ),
            )
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/trace"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 1
        assert body[0]["event"] == "step_failed"
        assert body[0]["step_index"] == 1
        assert body[0]["tool"] == "calculator"
        assert body[0]["error"] == "calculator exploded"
        assert body[0]["message"] == (
            "step_failed: step=1 tool=calculator; "
            "error=calculator exploded"
        )

    finally:
        db.close()
        clear_test_db_override()

def test_get_execution_trace_returns_structured_plan_failure_fields():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        db.add(
            ExecutionLog(
                execution_id=data["execution_id"],
                message=(
                    "plan_failed: step=1; "
                    "error=calculator exploded"
                ),
            )
        )
        db.commit()

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/trace"
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 1
        assert body[0]["event"] == "plan_failed"
        assert body[0]["step_index"] == 1
        assert body[0]["tool"] is None
        assert body[0]["error"] == "calculator exploded"
        assert body[0]["message"] == (
            "plan_failed: step=1; "
            "error=calculator exploded"
        )

    finally:
        db.close()
        clear_test_db_override()

def test_replay_execution_returns_404_when_execution_does_not_exist():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/executions/999999/replay",
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found",
        }

    finally:
        clear_test_db_override()

def test_replay_execution_returns_409_when_snapshot_does_not_exist():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Execution snapshot not found",
        }

    finally:
        clear_test_db_override()

def test_replay_execution_returns_409_when_snapshot_has_no_plan():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            input_snapshot="snapshot input",
            plan_snapshot=None,
            output_snapshot=None,
        )

        db.add(snapshot)
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Execution snapshot does not contain a plan",
        }

    finally:
        db.close()
        clear_test_db_override()

def test_replay_execution_returns_409_for_unsupported_snapshot_version():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        original_input = source_execution.input
        original_output = source_execution.output
        original_status = source_execution.status

        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            snapshot_version=CURRENT_EXECUTION_SNAPSHOT_VERSION + 1,
            input_snapshot="unsupported version replay input",
            plan_snapshot='{"steps":[]}',
            output_snapshot="original snapshot output",
        )

        db.add(snapshot)
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 409

        assert response.json() == {
            "detail": (
                "Unsupported execution snapshot version: "
                f"{CURRENT_EXECUTION_SNAPSHOT_VERSION + 1}; "
                "supported version: "
                f"{CURRENT_EXECUTION_SNAPSHOT_VERSION}"
            ),
        }

        db.expire_all()

        replay_executions = (
            db.query(Execution)
            .filter(
                Execution.replay_of_execution_id
                == data["execution_id"]
            )
            .all()
        )

        assert replay_executions == []

        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        assert source_execution.input == original_input
        assert source_execution.output == original_output
        assert source_execution.status == original_status
        assert source_execution.replay_of_execution_id is None

    finally:
        db.close()
        clear_test_db_override()

def test_replay_execution_creates_new_execution_from_snapshot(monkeypatch):
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            input_snapshot="first test execution",
            plan_snapshot=(
                '{"steps":['
                '{"tool":"calculator",'
                '"arguments":{"expression":"40+2"},'
                '"input":"calculate 40+2"}'
                ']}'
            ),
            output_snapshot="first result",
        )

        db.add(snapshot)
        db.commit()

        monkeypatch.setattr(
            "app.runtime.plan_executor.execute_tool",
            lambda tool_name, tool_input, allowed_tools=None: "42",
        )

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] != data["execution_id"]
        assert body["agent_id"] == data["agent_id"]
        assert body["status"] == "completed"
        assert body["output"] == "42"

        assert (
            body["replay_of_execution_id"]
            == data["execution_id"]
        )

        assert body["retry_count"] == 0
        assert body["failure_type"] is None
        assert body["failure_message"] is None

    finally:
        db.close()
        clear_test_db_override()

def test_replay_execution_does_not_modify_source_execution(monkeypatch):
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        source_execution = db.query(Execution).filter(
            Execution.id == data["execution_id"]
        ).first()

        original_input = source_execution.input
        original_output = source_execution.output
        original_status = source_execution.status
        original_retry_count = source_execution.retry_count
        original_failure_type = source_execution.failure_type
        original_failure_message = source_execution.failure_message

        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            input_snapshot="replay input",
            plan_snapshot=(
                '{"steps":['
                '{"tool":"calculator",'
                '"arguments":{"expression":"40+2"},'
                '"input":"calculate 40+2"}'
                ']}'
            ),
            output_snapshot="original snapshot output",
        )

        db.add(snapshot)
        db.commit()

        monkeypatch.setattr(
            "app.runtime.plan_executor.execute_tool",
            lambda tool_name, tool_input, allowed_tools=None: "42",
        )

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 200

        db.expire_all()

        source_execution = db.query(Execution).filter(
            Execution.id == data["execution_id"]
        ).first()

        assert source_execution.input == original_input
        assert source_execution.output == original_output
        assert source_execution.status == original_status
        assert source_execution.retry_count == original_retry_count
        assert source_execution.failure_type == original_failure_type
        assert source_execution.failure_message == original_failure_message

    finally:
        db.close()
        clear_test_db_override()

def test_replay_execution_persists_replay_lineage(monkeypatch):
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            input_snapshot="lineage replay input",
            plan_snapshot=(
                '{"steps":['
                '{"tool":"calculator",'
                '"arguments":{"expression":"6*7"},'
                '"input":"calculate 6*7"}'
                ']}'
            ),
            output_snapshot="original output",
        )

        db.add(snapshot)
        db.commit()

        monkeypatch.setattr(
            "app.runtime.plan_executor.execute_tool",
            lambda tool_name, tool_input, allowed_tools=None: "42",
        )

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 200

        replay_id = response.json()["id"]

        db.expire_all()

        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        replay_execution = (
            db.query(Execution)
            .filter(Execution.id == replay_id)
            .first()
        )

        assert source_execution.replay_of_execution_id is None

        assert replay_execution is not None
        assert replay_execution.id != source_execution.id
        assert (
            replay_execution.replay_of_execution_id
            == source_execution.id
        )

    finally:
        db.close()
        clear_test_db_override()

def test_get_execution_snapshot_returns_snapshot():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            input_snapshot="snapshot input",
            plan_snapshot='{"steps":[]}',
            output_snapshot="snapshot output",
        )

        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/snapshot",
            )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == snapshot.id
        assert body["execution_id"] == data["execution_id"]
        assert body["input_snapshot"] == "snapshot input"
        assert body["plan_snapshot"] == '{"steps":[]}'
        assert body["output_snapshot"] == "snapshot output"
        assert body["created_at"] is not None

    finally:
        db.close()
        clear_test_db_override()


def test_get_execution_snapshot_returns_404_when_execution_does_not_exist():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/executions/999999/snapshot",
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found",
        }

    finally:
        clear_test_db_override()


def test_get_execution_snapshot_returns_404_when_snapshot_does_not_exist():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/snapshot",
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution snapshot not found",
        }

    finally:
        clear_test_db_override()

def test_get_execution_replays_returns_empty_list_when_no_replays_exist():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/executions/{data['execution_id']}/replays",
            )

        assert response.status_code == 200
        assert response.json() == []

    finally:
        clear_test_db_override()


def test_get_execution_replays_returns_404_when_execution_does_not_exist():
    setup_test_db_override()
    reset_database()

    try:
        with TestClient(app) as client:
            response = client.get(
                "/executions/999999/replays",
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Execution not found",
        }

    finally:
        clear_test_db_override()


def test_get_execution_replays_returns_only_replays_for_source_execution():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        replay_execution = Execution(
            agent_id=data["agent_id"],
            input="replay input",
            output="replay output",
            status="completed",
            replay_of_execution_id=source_execution.id,
        )

        unrelated_execution = Execution(
            agent_id=data["agent_id"],
            input="unrelated input",
            output="unrelated output",
            status="completed",
        )

        db.add_all(
            [
                replay_execution,
                unrelated_execution,
            ]
        )
        db.commit()
        db.refresh(replay_execution)
        db.refresh(unrelated_execution)

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{source_execution.id}/replays",
            )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 1
        assert body[0]["id"] == replay_execution.id
        assert (
            body[0]["replay_of_execution_id"]
            == source_execution.id
        )

        returned_ids = [
            item["id"]
            for item in body
        ]

        assert unrelated_execution.id not in returned_ids

    finally:
        db.close()
        clear_test_db_override()


def test_get_execution_replays_returns_deterministic_order():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        replay_one = Execution(
            agent_id=data["agent_id"],
            input="replay one",
            output="first",
            status="completed",
            replay_of_execution_id=source_execution.id,
            created_at=source_execution.created_at,
        )

        replay_two = Execution(
            agent_id=data["agent_id"],
            input="replay two",
            output="second",
            status="completed",
            replay_of_execution_id=source_execution.id,
            created_at=source_execution.created_at,
        )

        db.add(replay_one)
        db.commit()
        db.refresh(replay_one)

        db.add(replay_two)
        db.commit()
        db.refresh(replay_two)

        with TestClient(app) as client:
            response = client.get(
                f"/executions/{source_execution.id}/replays",
            )

        assert response.status_code == 200

        body = response.json()

        assert [
            item["id"]
            for item in body
        ] == [
            replay_one.id,
            replay_two.id,
        ]

    finally:
        db.close()
        clear_test_db_override()

def test_replay_execution_returns_409_for_malformed_plan_snapshot_json():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        original_input = source_execution.input
        original_output = source_execution.output
        original_status = source_execution.status

        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            snapshot_version=CURRENT_EXECUTION_SNAPSHOT_VERSION,
            input_snapshot="malformed plan replay input",
            plan_snapshot="{this is not valid json",
            output_snapshot="original snapshot output",
        )

        db.add(snapshot)
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Invalid execution plan snapshot JSON",
        }

        db.expire_all()

        replay_executions = (
            db.query(Execution)
            .filter(
                Execution.replay_of_execution_id
                == data["execution_id"]
            )
            .all()
        )

        assert replay_executions == []

        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        assert source_execution.input == original_input
        assert source_execution.output == original_output
        assert source_execution.status == original_status
        assert source_execution.replay_of_execution_id is None

    finally:
        db.close()
        clear_test_db_override()

def test_replay_execution_returns_409_for_invalid_plan_snapshot_structure():
    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        original_input = source_execution.input
        original_output = source_execution.output
        original_status = source_execution.status

        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            snapshot_version=CURRENT_EXECUTION_SNAPSHOT_VERSION,
            input_snapshot="invalid plan structure replay input",
            plan_snapshot='{"steps":"not-a-list"}',
            output_snapshot="original snapshot output",
        )

        db.add(snapshot)
        db.commit()

        with TestClient(app) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

        assert response.status_code == 409
        assert response.json() == {
            "detail": (
                "Execution plan snapshot must contain a steps list"
            ),
        }

        db.expire_all()

        replay_executions = (
            db.query(Execution)
            .filter(
                Execution.replay_of_execution_id
                == data["execution_id"]
            )
            .all()
        )

        assert replay_executions == []

        source_execution = (
            db.query(Execution)
            .filter(Execution.id == data["execution_id"])
            .first()
        )

        assert source_execution.input == original_input
        assert source_execution.output == original_output
        assert source_execution.status == original_status
        assert source_execution.replay_of_execution_id is None

    finally:
        db.close()
        clear_test_db_override()


def test_replay_execution_returns_structured_500_for_runtime_failure(
    monkeypatch,
):
    from app.runtime.executor import ToolExecutionError

    setup_test_db_override()
    reset_database()
    data = create_test_data()

    db = TestingSessionLocal()

    try:
        source_execution = (
            db.query(Execution)
            .filter(
                Execution.id == data["execution_id"]
            )
            .first()
        )

        original_input = source_execution.input
        original_output = source_execution.output
        original_status = source_execution.status

        snapshot = ExecutionSnapshot(
            execution_id=data["execution_id"],
            snapshot_version=CURRENT_EXECUTION_SNAPSHOT_VERSION,
            input_snapshot=source_execution.input,
            plan_snapshot=(
                '{"steps":['
                '{"tool":"calculator",'
                '"arguments":{"expression":"40+2"},'
                '"input":"calculate 40+2"}'
                ']}'
            ),
            output_snapshot=source_execution.output,
        )

        db.add(snapshot)
        db.commit()

        def fail_tool(
            tool_name,
            tool_input,
            allowed_tools=None,
        ):
            raise ToolExecutionError(
                tool_name,
                "simulated replay API failure",
            )

        monkeypatch.setattr(
            "app.runtime.plan_executor.execute_tool",
            fail_tool,
        )

        with TestClient(
            app,
            raise_server_exceptions=False,
        ) as client:
            response = client.post(
                f"/executions/{data['execution_id']}/replay",
            )

            assert response.status_code == 500

            assert response.headers[
                "content-type"
            ].startswith("application/json")

            assert response.json() == {
                "detail": {
                    "failure_type": "tool_execution_error",
                    "failure_message": (
                        "Tool 'calculator' execution failed: "
                        "simulated replay API failure"
                    ),
                }
            }

            history_response = client.get(
                f"/executions/{data['execution_id']}/replays",
            )

            assert history_response.status_code == 200

        db.expire_all()

        replay_executions = (
            db.query(Execution)
            .filter(
                Execution.replay_of_execution_id
                == source_execution.id
            )
            .all()
        )

        assert len(replay_executions) == 1

        failed_replay = replay_executions[0]

        assert failed_replay.status == "failed"
        assert failed_replay.output is None
        assert (
            failed_replay.failure_type
            == "tool_execution_error"
        )
        assert (
            failed_replay.failure_message
            == (
                "Tool 'calculator' execution failed: "
                "simulated replay API failure"
            )
        )
        assert (
            failed_replay.replay_of_execution_id
            == source_execution.id
        )

        db.expire_all()

        source_execution = (
            db.query(Execution)
            .filter(
                Execution.id == data["execution_id"]
            )
            .first()
        )

        assert source_execution.input == original_input
        assert source_execution.output == original_output
        assert source_execution.status == original_status
        assert source_execution.replay_of_execution_id is None

    finally:
        db.close()
        clear_test_db_override()
