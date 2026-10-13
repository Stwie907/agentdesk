"""Validate a bounded backup and atomically create a separate conversation."""

import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud.agent import get_agent
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import ConversationResponse
from app.schemas.conversation_import import ConversationArchive, ConversationImportResponse, UNTITLED_IMPORT
from app.services.conversation_export import MAX_EXPORT_BYTES, MAX_EXPORT_MESSAGES


MAX_IMPORT_BYTES = MAX_EXPORT_BYTES
MAX_IMPORT_MESSAGES = MAX_EXPORT_MESSAGES


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not supported")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("Non-finite JSON numbers are not supported")


def parse_archive(raw: bytes) -> ConversationArchive:
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Conversation import exceeds the 10 MiB file limit.")
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if isinstance(data, dict):
            messages, count = data.get("messages"), data.get("message_count")
            if ((isinstance(messages, list) and len(messages) > MAX_IMPORT_MESSAGES) or
                    (type(count) is int and count > MAX_IMPORT_MESSAGES)):
                raise HTTPException(status_code=413, detail="Conversation import exceeds the 10000-message limit.")
        return ConversationArchive.model_validate(data)
    except (ValueError, UnicodeError, RecursionError, ValidationError) as error:
        raise HTTPException(status_code=422, detail="Invalid AgentDesk JSON export. Use a complete, unmodified version-1 JSON backup.") from error


def import_archive(db: Session, agent_id: int, raw: bytes) -> ConversationImportResponse:
    if get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    archive = parse_archive(raw)
    conversation = Conversation(agent_id=agent_id, title=archive.conversation.title if archive.conversation.title is not None else UNTITLED_IMPORT,
                                created_at=archive.conversation.created_at)
    try:
        db.add(conversation)
        db.flush()
        db.add_all([Message(conversation_id=conversation.id, role=row.role, content=row.content, created_at=row.created_at)
                    for row in archive.messages])
        db.flush()
        # Copy the response before commit expires ORM attributes. The entire
        # write is committed once, with no refresh or other fallible read afterward.
        result = ConversationImportResponse(schema_version=1, conversation=ConversationResponse.model_validate(conversation),
                                            message_count=archive.message_count)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to import conversation. Reload conversations to check its saved state before trying again.") from error
    return result
