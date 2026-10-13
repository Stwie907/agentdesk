from app.database import Base, engine

# 必须导入所有模型，让 SQLAlchemy 注册
from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.execution import Execution
from app.models.execution_log import ExecutionLog
from app.models.memory import Memory


print("Creating database tables...")


Base.metadata.create_all(
    bind=engine
)


print("Done.")
