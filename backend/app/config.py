import os


APP_NAME = "AgentDesk Backend"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./agentdesk.db",
)
