from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

from app.models.agent import Agent
from app.models.project import Project
from app.models.user import User


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


def create_test_agent():
    db = TestingSessionLocal()

    try:
        user = User(
            username="memory-test-user",
            email="memory-test@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Memory Test Project",
            description="Project used by memory tests",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Memory Test Agent",
            description="Agent used by memory tests",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        return agent.id

    finally:
        db.close()


def test_memory_crud():
    reset_database()

    app.dependency_overrides[get_db] = override_get_db

    agent_id = create_test_agent()

    try:
        with TestClient(app) as client:

            # 1. Create memory
            response = client.post(
                "/memories",
                json={
                    "agent_id": agent_id,
                    "content": "The user's name is Tom.",
                },
            )

            assert response.status_code == 200

            memory = response.json()

            assert isinstance(memory["id"], int)
            assert memory["agent_id"] == agent_id
            assert memory["content"] == "The user's name is Tom."

            memory_id = memory["id"]

            # 2. Get memories
            response = client.get(
                f"/memories/{agent_id}"
            )

            assert response.status_code == 200

            memories = response.json()

            assert len(memories) == 1
            assert memories[0]["id"] == memory_id
            assert memories[0]["agent_id"] == agent_id
            assert memories[0]["content"] == "The user's name is Tom."

            # 3. Delete memory
            response = client.delete(
                f"/memories/item/{memory_id}"
            )

            assert response.status_code == 200

            # 4. Confirm deletion
            response = client.get(
                f"/memories/{agent_id}"
            )

            assert response.status_code == 200
            assert response.json() == []

    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
