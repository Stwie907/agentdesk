"""Strict version-1 backup records; source IDs are never used as local keys."""

from datetime import datetime
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.conversation import ConversationResponse


SourceId = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$")
UNTITLED_IMPORT = "Imported untitled conversation"


class BackupRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def saved_timestamp(cls, value):
        if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
            raise ValueError("Use an original AgentDesk timestamp without a timezone offset")
        return datetime.fromisoformat(value)

    @field_validator("*", mode="after")
    @classmethod
    def valid_unicode(cls, value):
        if isinstance(value, str):
            value.encode("utf-8")
        return value


class BackupConversation(BackupRecord):
    id: SourceId
    agent_id: SourceId
    title: str | None


class BackupMessage(BackupRecord):
    id: SourceId
    conversation_id: SourceId
    role: str
    content: str


class ConversationArchive(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    conversation: BackupConversation
    message_count: Annotated[int, Field(strict=True, ge=0, le=10000)]
    messages: list[BackupMessage]

    @model_validator(mode="after")
    def complete_history(self):
        if len(self.messages) != self.message_count:
            raise ValueError("Message count does not match the complete transcript")
        seen = set()
        previous = None
        for message in self.messages:
            if message.conversation_id != self.conversation.id or message.id in seen:
                raise ValueError("Messages must belong to the source conversation and have unique IDs")
            key = (message.created_at, message.id)
            if previous is not None and key <= previous:
                raise ValueError("Messages must retain their original timestamp and ID order")
            seen.add(message.id)
            previous = key
        return self


class ConversationImportResponse(BaseModel):
    schema_version: int
    conversation: ConversationResponse
    message_count: int
