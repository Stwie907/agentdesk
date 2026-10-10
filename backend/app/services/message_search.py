"""Literal SQLite search with bounded previews; no Runtime or model calls."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.message import Message
from app.schemas.message_search import MessageSearchItem


SNIPPET_CHARACTERS = 240
ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def ascii_lower(value: str) -> str:
    return value.translate(ASCII_LOWER)


def preview(message: Message, query: str) -> MessageSearchItem:
    position = ascii_lower(message.content).find(ascii_lower(query))
    # SQLite lower() and this translation both fold ASCII letters only.
    if position < 0:
        raise ValueError("Search result does not contain its literal query")
    start = max(0, position - (SNIPPET_CHARACTERS - len(query)) // 2)
    end = min(len(message.content), start + SNIPPET_CHARACTERS)
    start = max(0, end - SNIPPET_CHARACTERS)
    return MessageSearchItem(
        id=message.id, conversation_id=message.conversation_id, role=message.role,
        created_at=message.created_at, snippet=message.content[start:end],
        match_start=position - start, match_end=position - start + len(query),
        truncated_before=start > 0, truncated_after=end < len(message.content),
    )


def search_messages(db: Session, conversation_id: int, query: str, role: str | None, limit: int, offset: int):
    rows = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        # instr uses bound literal text: %, _, quotes and backslashes are not patterns.
        func.instr(func.lower(Message.content), ascii_lower(query)) > 0,
    )
    if role is not None:
        rows = rows.filter(Message.role == role)
    total = rows.count()
    page = rows.order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(limit).all()
    return [preview(message, query) for message in page], total
