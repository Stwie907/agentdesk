import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.agent import Agent
from app.models.project import Project
from app.models.user import User
from app.seed_demo import (
    DEMO_AGENT_NAME,
    DEMO_EMAIL,
    DEMO_PROJECT_NAME,
    DEMO_USERNAME,
    MCP_AGENT_NAME,
    TRACKING_AGENT_NAME,
    seed_demo,
)


@pytest.fixture
def demo_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine)
    try:
        with sessions() as db:
            yield db
    finally:
        engine.dispose()


def test_seed_creates_connected_calculator_demo_records(demo_db):
    result = seed_demo(demo_db)

    user = demo_db.get(User, result["user_id"])
    project = demo_db.get(Project, result["project_id"])
    agent = demo_db.get(Agent, result["agent_id"])
    assert user.username == DEMO_USERNAME
    assert user.email == DEMO_EMAIL
    assert project.name == DEMO_PROJECT_NAME
    assert project.owner_id == user.id
    assert agent.name == DEMO_AGENT_NAME
    assert agent.project_id == project.id
    assert agent.model == "qwen2.5:7b"
    assert json.loads(agent.allowed_tools) == ["calculator"]
    order_agent = demo_db.get(Agent, result["mcp_agent_id"])
    assert order_agent.name == MCP_AGENT_NAME
    assert order_agent.project_id == project.id
    assert json.loads(order_agent.allowed_tools) == ["get_order"]
    tracking_agent = demo_db.get(Agent, result["tracking_agent_id"])
    assert tracking_agent.name == TRACKING_AGENT_NAME
    assert tracking_agent.project_id == project.id
    assert json.loads(tracking_agent.allowed_tools) == ["track_order"]


def test_repeated_seed_reuses_records_and_preserves_changed_agent_settings(demo_db):
    first = seed_demo(demo_db)
    agent = demo_db.get(Agent, first["agent_id"])
    agent.allowed_tools = "[]"
    agent.model = "user-selected-model"
    demo_db.commit()

    assert seed_demo(demo_db) == first
    assert demo_db.query(User).count() == 1
    assert demo_db.query(Project).count() == 1
    assert demo_db.query(Agent).count() == 3
    assert demo_db.get(Agent, first["agent_id"]).allowed_tools == "[]"
    assert demo_db.get(Agent, first["agent_id"]).model == "user-selected-model"


def test_seed_preserves_unrelated_user_project_and_agent(demo_db):
    user = User(username="existing-user", email="existing@example.com")
    demo_db.add(user)
    demo_db.flush()
    project = Project(name=DEMO_PROJECT_NAME, owner_id=user.id)
    demo_db.add(project)
    demo_db.flush()
    agent = Agent(
        name=DEMO_AGENT_NAME,
        project_id=project.id,
        model="existing-model",
        allowed_tools="[]",
    )
    demo_db.add(agent)
    demo_db.commit()
    existing_ids = (user.id, project.id, agent.id)

    result = seed_demo(demo_db)
    assert result["user_id"] != existing_ids[0]
    assert result["project_id"] != existing_ids[1]
    assert result["agent_id"] != existing_ids[2]
    assert demo_db.query(User).count() == 2
    assert demo_db.query(Project).count() == 2
    assert demo_db.query(Agent).count() == 4
    assert demo_db.get(Agent, existing_ids[2]).model == "existing-model"
    assert demo_db.get(Agent, existing_ids[2]).allowed_tools == "[]"


@pytest.mark.parametrize("username,email", [
    (DEMO_USERNAME, "different@example.com"),
    ("different-user", DEMO_EMAIL),
])
def test_seed_rejects_conflicting_demo_identity_without_creating_records(
    demo_db, username, email,
):
    demo_db.add(User(username=username, email=email))
    demo_db.commit()

    with pytest.raises(ValueError, match="belongs to another User"):
        seed_demo(demo_db)

    assert demo_db.query(User).count() == 1
    assert demo_db.query(Project).count() == 0
    assert demo_db.query(Agent).count() == 0


def test_repeated_seed_preserves_mcp_agent_permission_changes(demo_db):
    first = seed_demo(demo_db)
    agent = demo_db.get(Agent, first["mcp_agent_id"])
    agent.allowed_tools = "[]"
    demo_db.commit()
    assert seed_demo(demo_db) == first
    assert demo_db.get(Agent, first["mcp_agent_id"]).allowed_tools == "[]"


def test_repeated_seed_preserves_logistics_agent_settings(demo_db):
    first = seed_demo(demo_db)
    agent = demo_db.get(Agent, first["tracking_agent_id"])
    agent.allowed_tools = "[]"
    agent.model = "user-selected-model"
    demo_db.commit()
    assert seed_demo(demo_db) == first
    assert demo_db.get(Agent, first["tracking_agent_id"]).allowed_tools == "[]"
    assert demo_db.get(Agent, first["tracking_agent_id"]).model == "user-selected-model"
