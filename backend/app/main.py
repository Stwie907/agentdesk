from fastapi import FastAPI
from app.database import Base, engine
from app import models
from app.api.health import router as health_router
from app.api.users import router as user_router
from app.api.projects import router as project_router
from app.api.agents import router as agent_router
from app.api.executions import router as execution_router
from app.api.memories import router as memory_router
from app.api.execution_logs import router as execution_logs_router
from app.config import APP_NAME

Base.metadata.create_all(bind=engine)

app = FastAPI(title=APP_NAME)
app.include_router(health_router)
app.include_router(user_router)
app.include_router(project_router)
app.include_router(agent_router)
app.include_router(execution_router)
app.include_router(execution_logs_router)
app.include_router(memory_router)
