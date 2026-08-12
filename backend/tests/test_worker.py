from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.models.agent import Agent
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog

import app.workers.execution_worker as worker


def test_worker_calculator_pipeline(monkeypatch):
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

    monkeypatch.setattr(
        worker,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        worker,
        "plan",
        lambda user_input: {
            "tool": "calculator",
            "input": "12345*6789",
        },
    )

    db = TestingSessionLocal()

    try:
        agent = Agent(
            name="Test Agent",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

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

    worker.execute_agent(execution_id)

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

        logs = (
            db.query(ExecutionLog)
            .filter(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [log.message for log in logs]

        assert "Execution started" in messages
        assert "Loading memory" in messages
        assert "Planning task" in messages
        assert "Using tool calculator" in messages
        assert "Tool result returned directly" in messages

    finally:
        db.close()

        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
