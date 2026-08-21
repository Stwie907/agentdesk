from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)

    agent_id = Column(
        Integer,
        ForeignKey("agents.id"),
        nullable=False
    )

    title = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


    agent = relationship(
        "Agent",
        back_populates="conversations"
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
