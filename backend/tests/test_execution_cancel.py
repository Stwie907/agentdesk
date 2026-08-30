from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.execution import Execution
from app.workers import execution_worker


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


def test_worker_does_not_run_cancelled_execution(monkeypatch):
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="cancel-worker-user",
            email="cancel-worker@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="cancel-worker-project",
            description="cancel worker project",
            owner_id=user.id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="cancel-worker-agent",
            description="cancel worker agent",
            model="qwen2.5:7b",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="must not run",
            status="cancelled",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        monkeypatch.setattr(
            execution_worker,
            "SessionLocal",
            TestingSessionLocal,
        )

        called = {"run_agent": False}

        def fake_run_agent(*args, **kwargs):
            called["run_agent"] = True
            raise AssertionError(
                "run_agent must not be called for cancelled execution"
            )

        monkeypatch.setattr(
            execution_worker,
            "run_agent",
            fake_run_agent,
        )

        execution_worker.execute_agent(execution.id)

        db.refresh(execution)

        assert execution.status == "cancelled"
        assert called["run_agent"] is False

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
