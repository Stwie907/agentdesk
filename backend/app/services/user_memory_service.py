"""Shared memory belongs to the owner of an Agent's Project."""

from hashlib import sha256

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.project import Project
from app.models.user import User
from app.models.user_memory import UserMemory
from app.services.memory_retrieval import rank_memory_rows
from app.services.memory_vector_cache import invalidate_memory_vectors


class UserMemoryConflict(ValueError):
    pass


def owner_for_agent(db: Session, agent_id: int) -> User | None:
    return db.query(User).join(Project, Project.owner_id == User.id).join(
        Agent, Agent.project_id == Project.id,
    ).filter(Agent.id == agent_id).first()


def list_user_memories(db: Session, user_id: int) -> list[UserMemory]:
    return db.query(UserMemory).filter(UserMemory.user_id == user_id).order_by(
        UserMemory.created_at.asc(), UserMemory.id.asc(),
    ).all()


def content_key(content: str) -> str:
    if content.startswith("User's name is "):
        return "profile:name"
    return sha256(content.encode("utf-8")).hexdigest()


def save_user_memory(db: Session, user_id: int, content: str) -> UserMemory:
    normalized = content.strip()
    key = content_key(normalized)
    existing = db.query(UserMemory).filter_by(user_id=user_id, content_key=key).first()
    if existing:
        if existing.content == normalized:
            return existing
        raise UserMemoryConflict("A shared name memory already exists. Edit that memory instead.")
    saved = UserMemory(user_id=user_id, content=normalized, content_key=key)
    try:
        db.add(saved)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # A parallel duplicate save may have won the database uniqueness check.
        existing = db.query(UserMemory).filter_by(user_id=user_id, content_key=key).first()
        if existing is not None and existing.content == normalized:
            return existing
        raise UserMemoryConflict("Shared memory changed during the save. Reload shared memories.") from error
    except Exception:
        db.rollback()
        raise
    db.refresh(saved)
    return saved


def update_user_memory(db: Session, memory: UserMemory, content: str, expected_content: str) -> UserMemory:
    normalized = content.strip()
    if memory.content != expected_content:
        raise UserMemoryConflict("Shared memory changed since it was loaded. Reload shared memories before editing again.")
    key = content_key(normalized)
    existing = db.query(UserMemory).filter(UserMemory.user_id == memory.user_id,
                                           UserMemory.content_key == key, UserMemory.id != memory.id).first()
    if existing is not None:
        raise UserMemoryConflict("An identical shared memory or shared name already exists. Use different content.")
    try:
        changed = db.query(UserMemory).filter(UserMemory.id == memory.id,
            UserMemory.user_id == memory.user_id, UserMemory.content == expected_content,
        ).update({UserMemory.content: normalized, UserMemory.content_key: key}, synchronize_session=False)
        if changed != 1:
            raise UserMemoryConflict("Shared memory changed since it was loaded. Reload shared memories before editing again.")
        invalidate_memory_vectors(db, "user", memory.user_id, memory.id)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise UserMemoryConflict("An identical shared memory or shared name already exists. Reload shared memories.") from error
    except Exception:
        db.rollback()
        raise
    db.refresh(memory)
    return memory


def delete_user_memory(db: Session, memory: UserMemory) -> None:
    try:
        invalidate_memory_vectors(db, "user", memory.user_id, memory.id)
        db.delete(memory)
        db.commit()
    except Exception:
        db.rollback()
        raise


def ranked_user_memories_for_agent(db: Session, agent_id: int, query: str, limit: int = 5):
    owner = owner_for_agent(db, agent_id)
    if owner is None or limit <= 0:
        return []
    return rank_memory_rows(list_user_memories(db, owner.id), query, limit)


def user_memory_context(db: Session, agent_id: int, query: str, limit: int = 5) -> str:
    if not query.strip():
        owner = owner_for_agent(db, agent_id)
        rows = [] if owner is None else list_user_memories(db, owner.id)[:max(0, limit)]
    else:
        rows = [match.memory for match in ranked_user_memories_for_agent(db, agent_id, query, limit)]
    return "\n".join(row.content for row in rows)
