"""Add shared user memories; preserve a matching runtime-created table.

Revision ID: c84f31a920de
Revises: d09aa76d1cdb
"""

from alembic import op
import sqlalchemy as sa

revision = "c84f31a920de"
down_revision = "d09aa76d1cdb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("user_memories"):
        columns = {row["name"]: row for row in inspector.get_columns("user_memories")}
        required = {"id": sa.Integer, "user_id": sa.Integer, "content": sa.Text,
                    "content_key": sa.String, "created_at": sa.DateTime}
        if set(columns) != set(required) or any(not isinstance(columns[name]["type"], kind)
                                              or columns[name]["nullable"] for name, kind in required.items()):
            raise RuntimeError("Existing user_memories schema does not match this migration")
        if inspector.get_pk_constraint("user_memories")["constrained_columns"] != ["id"] or columns["content_key"]["type"].length != 64:
            raise RuntimeError("Existing user_memories has an invalid identity or content key")
        foreign_keys = inspector.get_foreign_keys("user_memories")
        if not any(row["constrained_columns"] == ["user_id"] and row["referred_table"] == "users"
                   and row["referred_columns"] == ["id"] for row in foreign_keys):
            raise RuntimeError("Existing user_memories is missing its owner foreign key")
        if not any(row["column_names"] == ["user_id", "content_key"] for row in inspector.get_unique_constraints("user_memories")):
            raise RuntimeError("Existing user_memories is missing its duplicate constraint")
        existing_indexes = {row["name"]: row for row in inspector.get_indexes("user_memories")}
        for name, column in (("ix_user_memories_id", "id"), ("ix_user_memories_user_id", "user_id")):
            if name not in existing_indexes:
                op.create_index(name, "user_memories", [column], unique=False)
            elif existing_indexes[name]["column_names"] != [column] or existing_indexes[name]["unique"]:
                raise RuntimeError("Existing user_memories has an invalid index")
        return
    op.create_table("user_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "content_key", name="uq_user_memories_user_key"),
    )
    op.create_index("ix_user_memories_id", "user_memories", ["id"], unique=False)
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_memories_user_id", table_name="user_memories")
    op.drop_index("ix_user_memories_id", table_name="user_memories")
    op.drop_table("user_memories")
