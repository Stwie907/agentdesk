from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(
        Integer,
        primary_key=True,
        index=True
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

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    executions = relationship(
        "Execution",
        back_populates="agent",
        cascade="all, delete-orphan"
    )


    conversations = relationship(
        "Conversation",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
