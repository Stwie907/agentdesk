from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base

from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent

from app.services.memory_service import (
    build_memory_context,
    save_agent_memory,
)


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


def test_memory_service_builds_runtime_context():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="memory-service-user",
            email="memory-service@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Memory Service Project",
            description="Memory service test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Memory Service Agent",
            description="Agent used to test persistent memory",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        save_agent_memory(
            db,
            agent.id,
            "The user's name is Tom.",
        )

        save_agent_memory(
            db,
            agent.id,
            "The user likes Python.",
        )

        memory_context = build_memory_context(
            db,
            agent.id,
        )

        assert "The user's name is Tom." in memory_context
        assert "The user likes Python." in memory_context

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_save_agent_memory_deduplicates():
    from app.models.memory import Memory

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        # Create user
        user = User(
            username="memory-dedup-user",
            email="memory-dedup@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        # Create project
        project = Project(
            name="Memory Dedup Project",
            description="Memory deduplication test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        # Create agent
        agent = Agent(
            project_id=project.id,
            name="Memory Dedup Agent",
            description="Agent used to test memory deduplication",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        # Save exactly the same memory twice.
        first_memory = save_agent_memory(
            db,
            agent.id,
            "User's name is Tom.",
        )

        second_memory = save_agent_memory(
            db,
            agent.id,
            "User's name is Tom.",
        )

        memories = (
            db.query(Memory)
            .filter(Memory.agent_id == agent.id)
            .all()
        )

        # Only one database record should exist.
        assert len(memories) == 1

        # The existing memory should be reused.
        assert first_memory.id == second_memory.id

        assert memories[0].content == "User's name is Tom."

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_save_agent_memory_updates_conflicting_name():
    from app.models.memory import Memory

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="memory-update-user",
            email="memory-update@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Memory Update Project",
            description="Memory update test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Memory Update Agent",
            description="Agent used to test memory updates",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        first_memory = save_agent_memory(
            db,
            agent.id,
            "User's name is Tom.",
        )

        second_memory = save_agent_memory(
            db,
            agent.id,
            "User's name is Jerry.",
        )

        memories = (
            db.query(Memory)
            .filter(Memory.agent_id == agent.id)
            .all()
        )

        assert len(memories) == 1

        assert first_memory.id == second_memory.id

        assert memories[0].content == "User's name is Jerry."

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()

def test_retrieve_relevant_memories():
    from app.models.memory import Memory
    from app.services.memory_service import retrieve_relevant_memories

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="memory-retrieval-user",
            email="memory-retrieval@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Memory Retrieval Project",
            description="Memory retrieval test project",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Memory Retrieval Agent",
            description="Agent used to test memory retrieval",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        db.add_all(
            [
                Memory(
                    agent_id=agent.id,
                    content="The user's name is Tom.",
                ),
                Memory(
                    agent_id=agent.id,
                    content="The user likes Python.",
                ),
                Memory(
                    agent_id=agent.id,
                    content="The user lives in Tokyo.",
                ),
            ]
        )

        db.commit()

        memories = retrieve_relevant_memories(
            db,
            agent.id,
            "What is the user's name?",
        )

        assert len(memories) >= 1

        contents = [
            memory.content
            for memory in memories
        ]

        assert "The user's name is Tom." in contents

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_retrieve_memories_respects_limit():
    from app.models.memory import Memory
    from app.services.memory_service import retrieve_relevant_memories

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="memory-limit-user",
            email="memory-limit@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Memory Limit Project",
            description="Memory retrieval limit test",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Memory Limit Agent",
            description="Agent used to test retrieval limit",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        db.add_all(
            [
                Memory(
                    agent_id=agent.id,
                    content="The user likes Python.",
                ),
                Memory(
                    agent_id=agent.id,
                    content="The user likes Java.",
                ),
                Memory(
                    agent_id=agent.id,
                    content="The user likes Go.",
                ),
            ]
        )

        db.commit()

        memories = retrieve_relevant_memories(
            db,
            agent.id,
            "What does the user like?",
            limit=2,
        )

        assert len(memories) == 2

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_retrieve_relevant_memories_returns_empty_when_no_match():
    from app.models.memory import Memory
    from app.services.memory_service import retrieve_relevant_memories

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    try:
        user = User(
            username="memory-no-match-user",
            email="memory-no-match@example.com",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        project = Project(
            name="Memory No Match Project",
            description="Memory no-match retrieval test",
            owner_id=user.id,
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        agent = Agent(
            project_id=project.id,
            name="Memory No Match Agent",
            description="Agent used to test no-match retrieval",
            model="qwen2.5:7b",
        )

        db.add(agent)
        db.commit()
        db.refresh(agent)

        db.add(
            Memory(
                agent_id=agent.id,
                content="The user likes Python.",
            )
        )

        db.commit()

        memories = retrieve_relevant_memories(
            db,
            agent.id,
            "What is the weather today?",
        )

        assert memories == []

    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
