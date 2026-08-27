from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog
from app.services.execution_trace import TraceEvent, trace_event


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


def test_trace_event_persists_standardized_events():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="trace test",
            status="pending",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        trace_event(
            db,
            execution.id,
            TraceEvent.EXECUTION_STARTED,
        )

        trace_event(
            db,
            execution.id,
            TraceEvent.MEMORY_RETRIEVED,
            detail="Relevant memory loaded",
        )

        trace_event(
            db,
            execution.id,
            TraceEvent.AGENT_STARTED,
        )

        trace_event(
            db,
            execution.id,
            TraceEvent.EXECUTION_COMPLETED,
        )

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution.id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        assert messages == [
            "execution_started",
            "memory_retrieved: Relevant memory loaded",
            "agent_started",
            "execution_completed",
        ]

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_runtime_trace_records_planner_and_tool_events(monkeypatch):
    from app.services import agent_runner

    monkeypatch.setattr(
        agent_runner,
        "SessionLocal",
        TestingSessionLocal,
    )

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="计算12345*6789",
            status="pending",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        monkeypatch.setattr(
            agent_runner,
            "plan",
            lambda user_input,allowed_tools=None: {
                "tool": "calculator",
                "input": "12345*6789",
            },
        )

        monkeypatch.setattr(
            agent_runner,
            "execute_tool",
            lambda tool_name, tool_input, allowed_tools=None: "83810205",
        )

        result = agent_runner.run_agent(
            "qwen2.5:7b",
            "计算12345*6789",
            execution_id=execution.id,
        )

        assert result == "83810205"

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution.id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        assert "planner_decision: tool=calculator" in messages
        assert "tool_called: tool=calculator" in messages

        assert any(
            message.startswith(
                "tool_result: tool=calculator"
            )
            for message in messages
        )

        assert not any(
            message.startswith("llm_called")
            for message in messages
        )

        assert not any(
            message.startswith("llm_completed")
            for message in messages
        )

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_runtime_trace_records_llm_events(monkeypatch):
    from app.services import agent_runner

    monkeypatch.setattr(
        agent_runner,
        "SessionLocal",
        TestingSessionLocal,
    )

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        execution = Execution(
            agent_id=1,
            input="介绍一下 AgentDesk",
            status="pending",
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        # Planner decides that no tool is needed.
        monkeypatch.setattr(
            agent_runner,
            "plan",
            lambda user_input,allowed_tools=None: {
                "tool": None,
                "input": user_input,
            },
        )

        # Do NOT call real Ollama in tests.
        monkeypatch.setattr(
            agent_runner,
            "call_llm",
            lambda model, prompt: "Mocked LLM response",
        )

        result = agent_runner.run_agent(
            "qwen2.5:7b",
            "介绍一下 AgentDesk",
            execution_id=execution.id,
        )

        assert result == "Mocked LLM response"

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution.id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        assert "planner_decision: tool=none" in messages
        assert "llm_called: model=qwen2.5:7b" in messages
        assert "llm_completed: model=qwen2.5:7b" in messages

        # No tool should have been executed.
        assert not any(
            message.startswith("tool_called")
            for message in messages
        )

        assert not any(
            message.startswith("tool_result")
            for message in messages
        )

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
