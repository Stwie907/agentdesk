from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.crud.agent import get_agent
from app.database import get_db
from app.schemas.runtime_configuration import RuntimeConfigurationResponse
from app.services.runtime_configuration import runtime_configuration


router = APIRouter(prefix="/runtime", tags=["runtime"])
READ_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


@router.get("/config", response_model=RuntimeConfigurationResponse,
            description="Read current process configuration and optionally the selected Agent's chat model. No model or connectivity probe is performed.")
def read_configuration(
    response: Response,
    db: Session = Depends(get_db),
    agent_id: Annotated[int | None, Query(gt=0, le=9223372036854775807)] = None,
):
    agent = None if agent_id is None else get_agent(db, agent_id)
    if agent_id is not None and agent is None:
        raise HTTPException(status_code=404, detail="Agent not found", headers=READ_HEADERS)
    try:
        result = runtime_configuration(db, agent)
    except ValueError as error:
        raise HTTPException(status_code=503,
                            detail="Runtime configuration is invalid. Check LLM and memory environment settings.",
                            headers=READ_HEADERS) from error
    response.headers.update(READ_HEADERS)
    return result
