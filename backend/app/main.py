
from fastapi import FastAPI

from app.database import Base, engine
import app.models

from app.api import (
    health,
    users,
    projects,
    agents,
    executions,
    memories,
    execution_logs,
    conversations,
    messages,
)

from app.config import APP_NAME


# create database tables
Base.metadata.create_all(
    bind=engine
)


app = FastAPI(
    title=APP_NAME
)


# register routers

app.include_router(
    health.router
)

app.include_router(
    users.router
)

app.include_router(
    projects.router
)

app.include_router(
    agents.router
)

app.include_router(
    executions.router
)

app.include_router(
    memories.router
)

app.include_router(
    execution_logs.router
)

app.include_router(
    conversations.router
)

app.include_router(
    messages.router
)
