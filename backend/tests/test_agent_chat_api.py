from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.agent import Agent
from app.models.execution import Execution


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




def reset_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def create_test_agent():
    db = TestingSessionLocal()

    try:
        agent = Agent(
            name="chat-test-agent",
            description="Agent used by chat API tests",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        return agent.id
    finally:
        db.close()


def fake_execute_agent(execution_id: int):
    db = TestingSessionLocal()

    try:
        execution = db.query(Execution).filter(
            Execution.id == execution_id
        ).first()

        execution.output = "Mocked AI response"
        execution.status = "completed"

        db.commit()
    finally:
        db.close()


def test_chat_with_agent_success():
    reset_database()
    app.dependency_overrides[get_db] = override_get_db
    agent_id = create_test_agent()

    with patch(
        "app.api.agents.execute_agent",
        side_effect=fake_execute_agent,
    ) as mock_execute:
        with TestClient(app) as client:
            response = client.post(
                f"/agents/{agent_id}/chat",
                json={
                    "message": "Hello AgentDesk"
                },
            )

    assert response.status_code == 200

    body = response.json()

    assert body["response"] == "Mocked AI response"
    assert body["status"] == "completed"
    assert isinstance(body["execution_id"], int)

    mock_execute.assert_called_once_with(body["execution_id"])

    db = TestingSessionLocal()

    try:
        execution = db.query(Execution).filter(
            Execution.id == body["execution_id"]
        ).first()

        assert execution is not None
        assert execution.agent_id == agent_id
        assert execution.input == "Hello AgentDesk"
        assert execution.output == "Mocked AI response"
        assert execution.status == "completed"
    finally:
        db.close()
    app.dependency_overrides.pop(get_db, None)

def test_chat_with_agent_not_found():
    reset_database()
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.api.agents.execute_agent") as mock_execute:
        with TestClient(app) as client:
            response = client.post(
                "/agents/999999/chat",
                json={
                    "message": "Hello"
                },
            )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Agent not found"
    }

    mock_execute.assert_not_called()
    app.dependency_overrides.pop(get_db, None)
