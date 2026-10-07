import pytest

from app.database import SessionLocal
from app.config import LLM_ENVIRONMENT_KEYS

from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent


@pytest.fixture(autouse=True)
def isolate_llm_environment(monkeypatch):
    # Tests select providers explicitly, regardless of the developer's shell.
    for key in LLM_ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user(db):

    user = User(
        username="test-user",
        email="test@example.com"
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@pytest.fixture
def test_project(db, test_user):

    project = Project(
        name="test-project",
        description="test project",
        owner_id=test_user.id
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@pytest.fixture
def test_agent(db, test_project):

    agent = Agent(
        project_id=test_project.id,
        name="test-agent",
        description="test agent",
        model="qwen2.5:7b"
    )

    db.add(agent)
    db.commit()
    db.refresh(agent)

    return agent
