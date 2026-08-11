from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id")
    )

    name = Column(String, nullable=False)

    description = Column(String)

    model = Column(String, default="qwen2.5")

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
        back_populates="agent",
        cascade="all, delete-orphan"
    )
