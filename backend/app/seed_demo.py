"""Create an idempotent demo User, Project, and calculator-enabled Agent."""

import json

from sqlalchemy import or_
from sqlalchemy.orm import Session

import app.models
from app.database import Base, SessionLocal, engine
from app.models.agent import Agent
from app.models.project import Project
from app.models.user import User


DEMO_USERNAME = "agentdesk-demo"
DEMO_EMAIL = "demo@agentdesk.local"
DEMO_PROJECT_NAME = "AgentDesk Demo"
DEMO_AGENT_NAME = "Demo Agent"


def seed_demo(db: Session) -> dict[str, int]:
    """Reuse matching demo records and preserve their existing settings."""
    try:
        user = db.query(User).filter(
            or_(User.username == DEMO_USERNAME, User.email == DEMO_EMAIL)
        ).first()
        if user is not None and (
            user.username != DEMO_USERNAME or user.email != DEMO_EMAIL
        ):
            raise ValueError("The demo username or email belongs to another User")

        if user is None:
            user = User(username=DEMO_USERNAME, email=DEMO_EMAIL)
            db.add(user)
            db.flush()

        project = db.query(Project).filter(
            Project.owner_id == user.id,
            Project.name == DEMO_PROJECT_NAME,
        ).first()
        if project is None:
            project = Project(
                owner_id=user.id,
                name=DEMO_PROJECT_NAME,
                description="Local AgentDesk demonstration workspace.",
            )
            db.add(project)
            db.flush()

        agent = db.query(Agent).filter(
            Agent.project_id == project.id,
            Agent.name == DEMO_AGENT_NAME,
        ).first()
        if agent is None:
            agent = Agent(
                project_id=project.id,
                name=DEMO_AGENT_NAME,
                description="Demo Agent for local Ollama or deterministic Mock mode.",
                model="qwen2.5:7b",
                allowed_tools=json.dumps(["calculator"]),
            )
            db.add(agent)
            db.flush()

        result = {"user_id": user.id, "project_id": project.id, "agent_id": agent.id}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        result = seed_demo(db)
    print(json.dumps({"agent_name": DEMO_AGENT_NAME, **result}))


if __name__ == "__main__":
    main()
