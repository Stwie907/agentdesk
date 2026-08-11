from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime

from app.database import Base


class ExecutionLog(Base):

    __tablename__ = "execution_logs"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    execution_id = Column(
        Integer,
        ForeignKey("executions.id"),
        nullable=False
    )

    level = Column(
        String,
        default="info"
    )

    message = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )
