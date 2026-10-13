"""Disposable embeddings keyed to a scoped source row and model namespace."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text, UniqueConstraint

from app.database import Base


class MemoryVectorCache(Base):
    __tablename__ = "memory_vector_cache"
    __table_args__ = (
        UniqueConstraint("source_type", "owner_id", "memory_id", "namespace", name="uq_memory_vector_source_model"),
        CheckConstraint("source_type IN ('agent', 'user')", name="ck_memory_vector_source"),
        CheckConstraint("owner_id > 0 AND memory_id > 0", name="ck_memory_vector_identity"),
        CheckConstraint("dimensions > 0 AND dimensions <= 16384", name="ck_memory_vector_dimensions"),
    )

    id = Column(Integer, primary_key=True)
    source_type = Column(String(5), nullable=False)
    owner_id = Column(Integer, nullable=False)
    memory_id = Column(Integer, nullable=False)
    namespace = Column(String(64), nullable=False)
    model_digest = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    source_created_at = Column(DateTime, nullable=False)
    dimensions = Column(Integer, nullable=False)
    vector_json = Column(Text, nullable=False)
    vector_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
