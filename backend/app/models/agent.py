from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id"),
        nullable=False
    )

    name = Column(
        String,
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    model = Column(
        String,
        nullable=False
    )

    allowed_tools = Column(
        Text,
        nullable=False,
        default='["calculator", "datetime"]',
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    project = relationship(
        "Project",
        back_populates="agents"
    )

    executions = relationship(
        "Execution",
        back_populates="agent"
    )

    conversations = relationship(
        "Conversation",
        back_populates="agent"
    )
