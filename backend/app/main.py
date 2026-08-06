from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import APP_NAME

app = FastAPI(title=APP_NAME)
app.include_router(health_router)
