from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.execution import Execution
from app.crud.message import create_message
from app.schemas.message import MessageCreate

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


def create_test_data():
    db = TestingSessionLocal()

    try:
        user = User(
            username="conversation-runtime-user",
            email="conversation-runtime@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="conversation-runtime-project",
            description="Conversation runtime integration test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Conversation Runtime Agent",
            description="Agent used by conversation runtime tests",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        conversation = Conversation(
            agent_id=agent.id,
            title="Runtime Integration Test",
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return {
            "agent_id": agent.id,
            "conversation_id": conversation.id,
        }

    finally:
        db.close()


def fake_execute_agent(
    execution_id: int,
    conversation_history: str = "",
):
    db = TestingSessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        assert execution is not None

        execution.output = "Mocked conversation runtime response"
        execution.status = "completed"

        db.commit()

    finally:
        db.close()


def test_conversation_chat_runtime_integration():
    reset_database()

    app.dependency_overrides[get_db] = override_get_db

    data = create_test_data()

    try:
        with patch(
            "app.services.conversation_service.execute_agent",
            side_effect=fake_execute_agent,
        ) as mock_execute:

            with TestClient(app) as client:
                response = client.post(
                    f"/conversations/{data['conversation_id']}/chat",
                    json={
                        "message": "Hello from conversation runtime"
                    },
                )

        assert response.status_code == 200

        body = response.json()

        assert isinstance(body["execution_id"], int)
        assert body["response"] == "Mocked conversation runtime response"
        assert body["status"] == "completed"

        mock_execute.assert_called_once()

        db = TestingSessionLocal()

        try:
            execution = (
                db.query(Execution)
                .filter(
                    Execution.id == body["execution_id"]
                )
                .first()
            )

            assert execution is not None
            assert execution.agent_id == data["agent_id"]
            assert execution.input == "Hello from conversation runtime"
            assert execution.output == "Mocked conversation runtime response"
            assert execution.status == "completed"

            messages = (
                db.query(Message)
                .filter(
                    Message.conversation_id
                    == data["conversation_id"]
                )
                .order_by(Message.id)
                .all()
            )

            assert len(messages) == 2

            assert messages[0].role == "user"
            assert (
                messages[0].content
                == "Hello from conversation runtime"
            )

            assert messages[1].role == "assistant"
            assert (
                messages[1].content
                == "Mocked conversation runtime response"
            )

        finally:
            db.close()

    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_conversation_history_passed_to_runtime():
    reset_database()

    app.dependency_overrides[get_db] = override_get_db

    data = create_test_data()

    captured = {}

    def fake_execute_agent(
        execution_id: int,
        conversation_history: str = "",
    ):
        captured["history"] = conversation_history

        db = TestingSessionLocal()

        try:
            execution = (
                db.query(Execution)
                .filter(Execution.id == execution_id)
                .first()
            )

            assert execution is not None

            execution.output = "Your name is Tom"
            execution.status = "completed"

            db.commit()

        finally:
            db.close()

    db = TestingSessionLocal()

    try:
        create_message(
            db,
            data["conversation_id"],
            MessageCreate(
                role="user",
                content="My name is Tom",
            ),
        )

        create_message(
            db,
            data["conversation_id"],
            MessageCreate(
                role="assistant",
                content="Hello Tom",
            ),
        )

    finally:
        db.close()

    try:
        with patch(
            "app.services.conversation_service.execute_agent",
            side_effect=fake_execute_agent,
        ):
            with TestClient(app) as client:
                response = client.post(
                    f"/conversations/{data['conversation_id']}/chat",
                    json={
                        "message": "What is my name?"
                    },
                )

        assert response.status_code == 200

        assert "My name is Tom" in captured["history"]
        assert "Hello Tom" in captured["history"]

    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_conversation_chat_extracts_and_saves_memory():
    reset_database()

    app.dependency_overrides[get_db] = override_get_db

    data = create_test_data()

    def fake_execute_agent(
        execution_id: int,
        conversation_history: str = "",
    ):
        db = TestingSessionLocal()

        try:
            execution = (
                db.query(Execution)
                .filter(Execution.id == execution_id)
                .first()
            )

            assert execution is not None

            execution.output = "Nice to meet you, Tom."
            execution.status = "completed"

            db.commit()

        finally:
            db.close()

    try:
        with patch(
            "app.services.conversation_service.execute_agent",
            side_effect=fake_execute_agent,
        ):
            with TestClient(app) as client:
                response = client.post(
                    f"/conversations/{data['conversation_id']}/chat",
                    json={
                        "message": "My name is Tom"
                    },
                )

        assert response.status_code == 200

        db = TestingSessionLocal()

        try:
            from app.models.memory import Memory

            memories = (
                db.query(Memory)
                .filter(
                    Memory.agent_id == data["agent_id"]
                )
                .all()
            )

            assert len(memories) == 1
            assert memories[0].content == "User's name is Tom."

        finally:
            db.close()

    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
