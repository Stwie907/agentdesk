"""Read one consistent, scoped transcript and serialize a complete attachment."""

from collections.abc import Iterable
import json
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse


EXPORT_SCHEMA_VERSION = 1
MAX_EXPORT_MESSAGES = 10_000
MAX_EXPORT_BYTES = 10 * 1024 * 1024


def export_snapshot(db: Session, conversation_id: int, agent_id: int) -> dict:
    # One SQL statement also includes empty conversations. Title and transcript
    # therefore come from the same SQLite read snapshot, even during other writes.
    rows = (db.query(Conversation, Message)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .filter(Conversation.id == conversation_id, Conversation.agent_id == agent_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(MAX_EXPORT_MESSAGES + 1).all())
    if not rows:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = [message for _, message in rows if message is not None]
    if len(messages) > MAX_EXPORT_MESSAGES:
        raise HTTPException(status_code=413, detail="Conversation export exceeds the 10000-message limit. No partial file was created.")
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "conversation": ConversationResponse.model_validate(rows[0][0]).model_dump(mode="json"),
        "message_count": len(messages),
        "messages": [MessageResponse.model_validate(row).model_dump(mode="json") for row in messages],
    }


def literal_block(value: str) -> str:
    # Longer than every backtick run: even embedded fences/HTML remain literal.
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}\n"


def markdown_parts(snapshot: dict) -> Iterable[str]:
    conversation = snapshot["conversation"]
    yield f'# Conversation {conversation["id"]}\n\nTitle:\n\n'
    yield literal_block(conversation["title"] if conversation["title"] is not None else "(untitled)")
    yield (f'\n- Export schema: {snapshot["schema_version"]}\n'
           f'- Agent ID: {conversation["agent_id"]}\n'
           f'- Created at: {conversation["created_at"]}\n'
           f'- Saved messages: {snapshot["message_count"]}\n')
    if not snapshot["messages"]:
        yield "\nNo saved messages.\n"
    for row in snapshot["messages"]:
        yield f'\n## Message {row["id"]}\n\nRole:\n\n'
        yield literal_block(row["role"])
        yield f'\nCreated at: {row["created_at"]}\n\nContent:\n\n'
        yield literal_block(row["content"])


def serialize_export(snapshot: dict, format: str) -> bytes:
    if format == "json":
        parts = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2).iterencode(snapshot)
    elif format == "markdown":
        parts = markdown_parts(snapshot)
    else:
        raise ValueError("Unsupported conversation export format")
    content = bytearray()
    for part in parts:
        encoded = part.encode("utf-8")
        if len(content) + len(encoded) > MAX_EXPORT_BYTES:
            raise HTTPException(status_code=413, detail="Conversation export exceeds the 10 MiB file limit. No partial file was created.")
        content.extend(encoded)
    if format == "json":
        if len(content) + 1 > MAX_EXPORT_BYTES:
            raise HTTPException(status_code=413, detail="Conversation export exceeds the 10 MiB file limit. No partial file was created.")
        content.extend(b"\n")
    return bytes(content)
