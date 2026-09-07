from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class ExecutionSnapshot(Base):
    __tablename__ = "execution_snapshots"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    execution_id = Column(
        Integer,
        ForeignKey("executions.id"),
        nullable=False,
        unique=True
    )

    input_snapshot = Column(
        Text,
        nullable=False
    )

    plan_snapshot = Column(
        Text,
        nullable=True
    )

    output_snapshot = Column(
        Text,
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    execution = relationship(
        "Execution",
        back_populates="snapshot"
    )
