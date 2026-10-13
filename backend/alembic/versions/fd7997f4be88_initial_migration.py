"""initial migration

Revision ID: fd7997f4be88
Revises:
Create Date: 2026-08-22 19:38:32.371291
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fd7997f4be88"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the core AgentDesk schema."""

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(
        op.f("ix_users_id"),
        "users",
        ["id"],
        unique=False,
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_projects_id"),
        "projects",
        ["id"],
        unique=False,
    )

    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("allowed_tools", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agents_id"),
        "agents",
        ["id"],
        unique=False,
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_executions_id"),
        "executions",
        ["id"],
        unique=False,
    )

    op.create_table(
        "execution_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_execution_logs_id"),
        "execution_logs",
        ["id"],
        unique=False,
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversations_id"),
        "conversations",
        ["id"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_messages_id"),
        "messages",
        ["id"],
        unique=False,
    )

    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memories_id"),
        "memories",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the core AgentDesk schema."""

    op.drop_index(
        op.f("ix_memories_id"),
        table_name="memories",
    )
    op.drop_table("memories")

    op.drop_index(
        op.f("ix_messages_id"),
        table_name="messages",
    )
    op.drop_table("messages")

    op.drop_index(
        op.f("ix_conversations_id"),
        table_name="conversations",
    )
    op.drop_table("conversations")

    op.drop_index(
        op.f("ix_execution_logs_id"),
        table_name="execution_logs",
    )
    op.drop_table("execution_logs")

    op.drop_index(
        op.f("ix_executions_id"),
        table_name="executions",
    )
    op.drop_table("executions")

    op.drop_index(
        op.f("ix_agents_id"),
        table_name="agents",
    )
    op.drop_table("agents")

    op.drop_index(
        op.f("ix_projects_id"),
        table_name="projects",
    )
    op.drop_table("projects")

    op.drop_index(
        op.f("ix_users_id"),
        table_name="users",
    )
    op.drop_table("users")
