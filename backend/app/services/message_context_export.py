"""Serialize a bounded saved-message excerpt without changing saved records."""

from collections.abc import Iterable
import json

from fastapi import HTTPException

from app.schemas.message_context import MessageContextResponse
from app.services.conversation_export import literal_block


CONTEXT_EXPORT_KIND = "agentdesk.message_context"
CONTEXT_EXPORT_SCHEMA_VERSION = 1
MAX_CONTEXT_EXPORT_BYTES = 10 * 1024 * 1024


def context_export_snapshot(context: MessageContextResponse) -> dict:
    return {"export_kind": CONTEXT_EXPORT_KIND, "schema_version": CONTEXT_EXPORT_SCHEMA_VERSION,
            "message_count": len(context.items), "context": context.model_dump(mode="json")}


def context_markdown_parts(snapshot: dict) -> Iterable[str]:
    context = snapshot["context"]
    yield "# Saved message context\n\n"
    yield "This is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n"
    yield (f'- Export kind: {snapshot["export_kind"]}\n'
           f'- Export schema: {snapshot["schema_version"]}\n'
           f'- Conversation ID: {context["conversation_id"]}\n'
           f'- Agent ID: {context["agent_id"]}\n'
           f'- Selected message ID: {context["anchor_message_id"]}\n'
           f'- Requested earlier messages: {context["before"]}\n'
           f'- Requested later messages: {context["after"]}\n'
           f'- Selected message index: {context["anchor_index"]}\n'
           f'- Earlier saved messages outside excerpt: {str(context["has_more_before"]).lower()}\n'
           f'- Later saved messages outside excerpt: {str(context["has_more_after"]).lower()}\n'
           f'- Saved messages: {snapshot["message_count"]}\n')
    for row in context["items"]:
        label = "Selected message" if row["id"] == context["anchor_message_id"] else "Saved message"
        yield f'\n## {label} {row["id"]}\n\nRole:\n\n'
        yield literal_block(row["role"])
        yield f'\nCreated at: {row["created_at"]}\n\nContent:\n\n'
        yield literal_block(row["content"])


def serialize_message_context_export(context: MessageContextResponse, format: str) -> bytes:
    snapshot = context_export_snapshot(context)
    if format == "json":
        parts = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2).iterencode(snapshot)
    elif format == "markdown":
        parts = context_markdown_parts(snapshot)
    else:
        raise ValueError("Unsupported message context export format")
    content = bytearray()
    for part in parts:
        encoded = part.encode("utf-8")
        if len(content) + len(encoded) > MAX_CONTEXT_EXPORT_BYTES:
            raise HTTPException(status_code=413, detail="Message context export exceeds the 10 MiB file limit. No partial file was created.")
        content.extend(encoded)
    if format == "json":
        if len(content) + 1 > MAX_CONTEXT_EXPORT_BYTES:
            raise HTTPException(status_code=413, detail="Message context export exceeds the 10 MiB file limit. No partial file was created.")
        content.extend(b"\n")
    return bytes(content)
