from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base

from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog

import app.workers.execution_worker as worker


def test_worker_calculator_pipeline(monkeypatch):
    # ---------------------------------------------------------
    # Isolated in-memory database
    # ---------------------------------------------------------
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    Base.metadata.create_all(bind=test_engine)

    # ---------------------------------------------------------
    # Replace worker database session
    # ---------------------------------------------------------
    monkeypatch.setattr(
        worker,
        "SessionLocal",
        TestingSessionLocal,
    )

    # ---------------------------------------------------------
    # Mock Agent Runtime
    #
    # Worker no longer calls plan() / execute_tool() directly.
    # Planner and executor are now handled inside run_agent().
    # ---------------------------------------------------------
    monkeypatch.setattr(
        worker,
        "run_agent",
        lambda model, user_input, memory_text="": "83810205",
    )

    db = TestingSessionLocal()

    try:
        # -----------------------------------------------------
        # Create user
        # -----------------------------------------------------
        user = User(
            username="worker-test-user",
            email="worker@test.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        # -----------------------------------------------------
        # Create project
        # -----------------------------------------------------
        project = Project(
            name="worker-test-project",
            description="worker test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        # -----------------------------------------------------
        # Create agent
        # -----------------------------------------------------
        agent = Agent(
            project_id=project.id,
            name="Test Agent",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        # -----------------------------------------------------
        # Create execution
        # -----------------------------------------------------
        execution = Execution(
            agent_id=agent.id,
            input="计算12345*6789",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        execution_id = execution.id

    finally:
        db.close()

    # ---------------------------------------------------------
    # Execute worker
    # ---------------------------------------------------------
    worker.execute_agent(execution_id)

    # ---------------------------------------------------------
    # Verify execution
    # ---------------------------------------------------------
    db = TestingSessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        assert execution is not None

        assert execution.status == "completed"
        assert execution.output == "83810205"

        # -----------------------------------------------------
        # Verify execution logs
        # -----------------------------------------------------
        logs = (
            db.query(ExecutionLog)
            .filter(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [log.message for log in logs]

        assert "Execution started" in messages
        assert "Loading memory" in messages
        assert "Running agent" in messages
        assert "Execution completed" in messages

    finally:
        db.close()

        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
