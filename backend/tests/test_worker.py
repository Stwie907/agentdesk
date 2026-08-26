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
from app.models.memory import Memory
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
        lambda model,
        user_input,
        memory_text="",
        conversation_history="",
        execution_id=None: "83810205",
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

        assert "execution_started" in messages
        assert "memory_retrieval_started" in messages
        assert any(
            message.startswith("memory_retrieved")
            for message in messages
        )
        assert "agent_started" in messages
        assert "execution_completed" in messages

    finally:
        db.close()

        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_worker_passes_memory_to_agent_runtime(monkeypatch):
    # ---------------------------------------------------------
    # Isolated in-memory database
    # ---------------------------------------------------------
    test_engine = create_engine(
        "sqlite:///",
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
    # Capture arguments passed to Agent Runtime
    # ---------------------------------------------------------
    captured = {}

    def fake_run_agent(
        model,
        user_input,
        memory_text="",
        conversation_history="",
        execution_id=None,
 ):
        captured["model"] = model
        captured["user_input"] = user_input
        captured["memory_text"] = memory_text
        captured["conversation_history"] = conversation_history
        captured["execution_id"] = execution_id

        return "Your name is Tom"

    monkeypatch.setattr(
        worker,
        "run_agent",
        fake_run_agent,
    )

    db = TestingSessionLocal()

    try:
        # ---------------------------------------------------------
        # Create user
        # ---------------------------------------------------------
        user = User(
            username="worker-memory-user",
            email="worker-memory@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        # ---------------------------------------------------------
        # Create project
        # ---------------------------------------------------------
        project = Project(
            name="worker-memory-project",
            description="Worker memory integration test",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        # ---------------------------------------------------------
        # Create agent
        # ---------------------------------------------------------
        agent = Agent(
            project_id=project.id,
            name="Memory Runtime Agent",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        # ---------------------------------------------------------
        # Create persistent memories
        # ---------------------------------------------------------
        memory_1 = Memory(
            agent_id=agent.id,
            content="The user's name is Tom.",
        )

        memory_2 = Memory(
            agent_id=agent.id,
            content="The user likes Python.",
        )

        db.add_all(
            [
                memory_1,
                memory_2,
            ]
        )
        db.commit()

        # ---------------------------------------------------------
        # Create execution
        # ---------------------------------------------------------
        execution = Execution(
            agent_id=agent.id,
            input="What is the user's name?",
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
    # Verify memory reached Agent Runtime
    # ---------------------------------------------------------
    assert "memory_text" in captured

    assert "The user's name is Tom." in captured["memory_text"]
    assert "The user likes Python." not in captured["memory_text"]
    assert captured["model"] == "qwen2.5:7b"
    assert captured["user_input"] == "What is the user's name?"

    # ---------------------------------------------------------
    # Verify execution result
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
        assert execution.output == "Your name is Tom"

    finally:
        db.close()

        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_worker_records_retryable_timeout_failure(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.user import User
    from app.models.project import Project
    from app.models.agent import Agent
    from app.models.execution import Execution
    from app.models.execution_log import ExecutionLog

    import app.workers.execution_worker as worker

    test_engine = create_engine(
        "sqlite:///",
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
        "run_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            TimeoutError("Ollama request timed out")
        ),
    )

    db = TestingSessionLocal()

    try:
        user = User(
            username="timeout-test-user",
            email="timeout-test@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Timeout Test Project",
            description="Worker timeout failure test",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Timeout Test Agent",
            description="Agent used for timeout test",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="trigger timeout",
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
        assert execution.status == "failed"
        assert execution.output == "Ollama request timed out"

        logs = (
            db.query(ExecutionLog)
            .filter(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        assert any(
            "execution_failed" in message
            and "type=timeout" in message
            and "retryable=true" in message
            and "Ollama request timed out" in message
            for message in messages
        )

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_worker_records_non_retryable_runtime_failure(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.user import User
    from app.models.project import Project
    from app.models.agent import Agent
    from app.models.execution import Execution
    from app.models.execution_log import ExecutionLog

    import app.workers.execution_worker as worker

    test_engine = create_engine(
        "sqlite:///",
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
        "run_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Agent runtime failed")
        ),
    )

    db = TestingSessionLocal()

    try:
        user = User(
            username="runtime-failure-user",
            email="runtime-failure@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Runtime Failure Project",
            description="Worker runtime failure test",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Runtime Failure Agent",
            description="Agent used for runtime failure test",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="trigger runtime failure",
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
        assert execution.status == "failed"
        assert execution.output == "Agent runtime failed"

        logs = (
            db.query(ExecutionLog)
            .filter(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        assert any(
            "execution_failed" in message
            and "type=runtime_error" in message
            and "retryable=false" in message
            and "Agent runtime failed" in message
            for message in messages
        )

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_worker_retries_timeout_then_succeeds(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.user import User
    from app.models.project import Project
    from app.models.agent import Agent
    from app.models.execution import Execution
    from app.models.execution_log import ExecutionLog

    import app.workers.execution_worker as worker

    test_engine = create_engine(
        "sqlite:///",
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

    calls = {
        "count": 0,
    }

    def fake_run_agent(*args, **kwargs):
        calls["count"] += 1

        if calls["count"] == 1:
            raise TimeoutError("temporary timeout")

        return "Recovered successfully"

    monkeypatch.setattr(
        worker,
        "run_agent",
        fake_run_agent,
    )

    db = TestingSessionLocal()

    try:
        user = User(
            username="retry-success-user",
            email="retry-success@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Retry Success Project",
            description="Retry success test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Retry Success Agent",
            description="Agent used for retry success test",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="trigger temporary timeout",
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
        assert execution.output == "Recovered successfully"

        # Initial attempt + one retry.
        assert calls["count"] == 2

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution_id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        retry_messages = [
            message
            for message in messages
            if message.startswith("execution_retrying")
        ]

        assert len(retry_messages) == 1

        assert "attempt=1" in retry_messages[0]
        assert "type=timeout" in retry_messages[0]
        assert "temporary timeout" in retry_messages[0]

        assert "execution_completed" in messages

        assert not any(
            message.startswith("execution_failed")
            for message in messages
        )

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_worker_stops_after_max_retries(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.user import User
    from app.models.project import Project
    from app.models.agent import Agent
    from app.models.execution import Execution
    from app.models.execution_log import ExecutionLog

    import app.workers.execution_worker as worker

    test_engine = create_engine(
        "sqlite:///",
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

    calls = {
        "count": 0,
    }

    def fake_run_agent(*args, **kwargs):
        calls["count"] += 1
        raise TimeoutError("persistent timeout")

    monkeypatch.setattr(
        worker,
        "run_agent",
        fake_run_agent,
    )

    db = TestingSessionLocal()

    try:
        user = User(
            username="retry-exhausted-user",
            email="retry-exhausted@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Retry Exhausted Project",
            description="Retry exhausted test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Retry Exhausted Agent",
            description="Agent used for retry exhaustion test",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="always timeout",
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

        # max_retries=2:
        # initial attempt + 2 retries = 3 total calls
        assert calls["count"] == 3

        assert execution.status == "failed"
        assert "persistent timeout" in execution.output

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution_id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        retry_messages = [
            message
            for message in messages
            if message.startswith("execution_retrying")
        ]

        assert len(retry_messages) == 2

        assert "attempt=1" in retry_messages[0]
        assert "attempt=2" in retry_messages[1]

        failed_messages = [
            message
            for message in messages
            if message.startswith("execution_failed")
        ]

        assert len(failed_messages) == 1

        assert "type=timeout" in failed_messages[0]
        assert "retryable=true" in failed_messages[0]
        assert "retries=2" in failed_messages[0]
        assert "persistent timeout" in failed_messages[0]

        assert "execution_completed" not in messages

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_worker_does_not_retry_non_retryable_failure(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models.user import User
    from app.models.project import Project
    from app.models.agent import Agent
    from app.models.execution import Execution
    from app.models.execution_log import ExecutionLog

    import app.workers.execution_worker as worker

    test_engine = create_engine(
        "sqlite:///",
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

    calls = {
        "count": 0,
    }

    def fake_run_agent(*args, **kwargs):
        calls["count"] += 1
        raise RuntimeError("non retryable runtime failure")

    monkeypatch.setattr(
        worker,
        "run_agent",
        fake_run_agent,
    )

    db = TestingSessionLocal()

    try:
        user = User(
            username="no-retry-user",
            email="no-retry@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="No Retry Project",
            description="Non retryable failure test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="No Retry Agent",
            description="Agent used for non retryable failure test",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        execution = Execution(
            agent_id=agent.id,
            input="trigger runtime failure",
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

        # Non-retryable failures must stop immediately.
        assert calls["count"] == 1

        assert execution.status == "failed"
        assert execution.output == "non retryable runtime failure"

        logs = (
            db.query(ExecutionLog)
            .filter(
                ExecutionLog.execution_id == execution_id
            )
            .order_by(ExecutionLog.id)
            .all()
        )

        messages = [
            log.message
            for log in logs
        ]

        assert not any(
            message.startswith("execution_retrying")
            for message in messages
        )

        failed_messages = [
            message
            for message in messages
            if message.startswith("execution_failed")
        ]

        assert len(failed_messages) == 1

        assert "type=runtime_error" in failed_messages[0]
        assert "retryable=false" in failed_messages[0]
        assert "retries=0" in failed_messages[0]
        assert "non retryable runtime failure" in failed_messages[0]

        assert "execution_completed" not in messages

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
