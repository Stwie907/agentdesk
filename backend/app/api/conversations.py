from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.crud.agent import get_agent
from app.crud.conversation import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_page,
    get_conversations,
    update_conversation_title,
)
from app.database import get_db
from app.services.conversation_export import EXPORT_SCHEMA_VERSION, export_snapshot, serialize_export
from app.services import conversation_import as importer
from app.schemas.conversation_import import ConversationImportResponse
from app.schemas.conversation import (
    ConversationCreateRequest, ConversationPageResponse, ConversationResponse, ConversationUpdateRequest,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


def require_conversation(db: Session, conversation_id: int, agent_id: int | None = None):
    conversation = get_conversation(db, conversation_id, agent_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("", response_model=ConversationResponse)
def create(conversation: ConversationCreateRequest, db: Session = Depends(get_db)):
    if get_agent(db, conversation.agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return create_conversation(db, conversation)


@router.get("", response_model=list[ConversationResponse])
def list_all(db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    if agent_id is not None and get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return get_conversations(db, agent_id)


@router.get("/page", response_model=ConversationPageResponse)
def page(
    agent_id: Annotated[int, Query(gt=0, le=9223372036854775807)],
    db: Session = Depends(get_db),
    query: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    if get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    normalized = query.strip()
    items, total = get_conversation_page(db, agent_id, normalized, limit, offset)
    return ConversationPageResponse(
        agent_id=agent_id, query=normalized, limit=limit, offset=offset, total=total,
        has_more=offset + len(items) < total,
        items=[ConversationResponse.model_validate(row) for row in items],
    )


@router.post("/import", response_model=ConversationImportResponse, status_code=201,
             description="Import a complete version-1 AgentDesk JSON export as a new conversation for the selected Agent.",
             openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"},
                 "example": {"schema_version": 1, "conversation": {"id": 1, "agent_id": 1, "title": "Saved chat", "created_at": "2026-10-10T06:00:00"},
                             "message_count": 0, "messages": []}}}}})
async def import_conversation(
    request: Request, response: Response,
    agent_id: Annotated[int, Query(gt=0, le=9223372036854775807)],
    db: Session = Depends(get_db),
):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="Use an application/json AgentDesk backup.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > importer.MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="Conversation import exceeds the 10 MiB file limit.")
        raw.extend(chunk)
    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(importer.import_archive, db, agent_id, bytes(raw))


@router.get("/{conversation_id}", response_model=ConversationResponse)
def read(conversation_id: Annotated[int, Path(gt=0)], db: Session = Depends(get_db),
         agent_id: Annotated[int | None, Query(gt=0)] = None):
    return require_conversation(db, conversation_id, agent_id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename(conversation_id: Annotated[int, Path(gt=0)], request: ConversationUpdateRequest,
           db: Session = Depends(get_db), agent_id: Annotated[int | None, Query(gt=0)] = None):
    conversation = require_conversation(db, conversation_id, agent_id)
    return update_conversation_title(db, conversation, request.title)


@router.delete("/{conversation_id}")
def remove(conversation_id: Annotated[int, Path(gt=0)], db: Session = Depends(get_db),
           agent_id: Annotated[int | None, Query(gt=0)] = None):
    require_conversation(db, conversation_id, agent_id)
    delete_conversation(db, conversation_id)
    return {"message": "deleted"}


@router.get("/{conversation_id}/export", response_class=Response)
def export_conversation(
    conversation_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    agent_id: Annotated[int, Query(gt=0, le=9223372036854775807)],
    db: Session = Depends(get_db),
    format: Literal["json", "markdown"] = "json",
):
    snapshot = export_snapshot(db, conversation_id, agent_id)
    content = serialize_export(snapshot, format)
    extension = "json" if format == "json" else "md"
    return Response(content, media_type="application/json" if format == "json" else "text/markdown", headers={
        "Content-Disposition": f'attachment; filename="conversation-{conversation_id}.{extension}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Conversation-ID": str(conversation_id),
        "X-Agent-ID": str(agent_id),
        "X-Message-Count": str(snapshot["message_count"]),
        "X-Export-Schema-Version": str(EXPORT_SCHEMA_VERSION),
    })
