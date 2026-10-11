from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from app.crud.agent import get_agent
from app.database import get_db
from app.schemas.agent_message_search import AgentMessageSearchResponse
from app.schemas.message_search import MessageRoleFilter
from app.services.agent_message_search import search_agent_messages


router = APIRouter(prefix="/agents", tags=["messages"])


@router.get("/{agent_id}/messages/search", response_model=AgentMessageSearchResponse)
def search_saved_agent_messages(
    agent_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    query: Annotated[str, Query(min_length=1, max_length=200)],
    response: Response,
    db: Session = Depends(get_db),
    role: MessageRoleFilter | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    normalized = query.strip()
    if not normalized or "\x00" in normalized:
        raise HTTPException(status_code=422, detail="Enter a message search query of 1 to 200 characters without NUL.")
    if get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    items, total = search_agent_messages(db, agent_id, normalized, role, limit, offset)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return AgentMessageSearchResponse(
        agent_id=agent_id, query=normalized, role=role, limit=limit, offset=offset,
        total=total, has_more=offset + len(items) < total, items=items,
    )
