from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from datetime import datetime

from app.database import Base


class Memory(Base):

    __tablename__ = "memories"

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

    content = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )
