from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class Execution(Base):
    __tablename__ = "executions"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    agent_id = Column(
        Integer,
        ForeignKey("agents.id"),
        nullable=False
    )

    input = Column(
        Text,
        nullable=False
    )

    output = Column(
        Text
    )

    status = Column(
        String,
        default="pending"
    )

    logs = relationship(
        "ExecutionLog",
        backref="execution"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    agent = relationship(
        "Agent",
        back_populates="executions"
    )
