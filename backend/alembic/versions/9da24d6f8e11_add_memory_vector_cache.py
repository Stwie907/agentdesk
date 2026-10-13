"""Add disposable memory vectors and adopt a matching runtime-created table.

Revision ID: 9da24d6f8e11
Revises: c84f31a920de
"""

import re

from alembic import op
import sqlalchemy as sa

revision = "9da24d6f8e11"
down_revision = "c84f31a920de"
branch_labels = None
depends_on = None


CHECKS = {
    "ck_memory_vector_source": "source_type IN ('agent', 'user')",
    "ck_memory_vector_identity": "owner_id > 0 AND memory_id > 0",
    "ck_memory_vector_dimensions": "dimensions > 0 AND dimensions <= 16384",
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("memory_vector_cache"):
        columns = {row["name"]: row for row in inspector.get_columns("memory_vector_cache")}
        expected = {"id": sa.Integer, "source_type": sa.String, "owner_id": sa.Integer,
                    "memory_id": sa.Integer, "namespace": sa.String, "model_digest": sa.String,
                    "content_hash": sa.String, "source_created_at": sa.DateTime, "dimensions": sa.Integer,
                    "vector_json": sa.Text, "vector_hash": sa.String, "created_at": sa.DateTime}
        if set(columns) != set(expected) or any(not isinstance(columns[name]["type"], kind)
                                               or columns[name]["nullable"] for name, kind in expected.items()):
            raise RuntimeError("Existing memory_vector_cache schema does not match this migration")
        for name, length in (("source_type", 5), ("namespace", 64), ("model_digest", 64), ("content_hash", 64), ("vector_hash", 64)):
            if columns[name]["type"].length != length:
                raise RuntimeError("Existing memory_vector_cache has an invalid key length")
        if inspector.get_pk_constraint("memory_vector_cache")["constrained_columns"] != ["id"]:
            raise RuntimeError("Existing memory_vector_cache has an invalid identity")
        if not any(row["column_names"] == ["source_type", "owner_id", "memory_id", "namespace"]
                   for row in inspector.get_unique_constraints("memory_vector_cache")):
            raise RuntimeError("Existing memory_vector_cache is missing its source/model uniqueness constraint")
        actual = {row["name"]: row["sqltext"] for row in inspector.get_check_constraints("memory_vector_cache")}
        normalize = lambda value: re.sub(r"\s+", "", value).lower()
        if any(name not in actual or normalize(actual[name]) != normalize(expression) for name, expression in CHECKS.items()):
            raise RuntimeError("Existing memory_vector_cache has invalid source or dimension constraints")
        return
    op.create_table("memory_vector_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(5), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("memory_id", sa.Integer(), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False),
        sa.Column("model_digest", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_created_at", sa.DateTime(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.Text(), nullable=False),
        sa.Column("vector_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "owner_id", "memory_id", "namespace", name="uq_memory_vector_source_model"),
        *(sa.CheckConstraint(expression, name=name) for name, expression in CHECKS.items()),
    )


def downgrade():
    op.drop_table("memory_vector_cache")
