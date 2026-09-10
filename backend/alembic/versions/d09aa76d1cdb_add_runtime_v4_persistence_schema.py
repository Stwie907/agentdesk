"""add runtime v4 persistence schema

Revision ID: d09aa76d1cdb
Revises: 5e76747a8551
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d09aa76d1cdb"
down_revision: Union[str, Sequence[str], None] = "5e76747a8551"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Runtime V4 persistence schema."""

    # SQLite cannot add a foreign-key constraint to an existing table
    # with ALTER TABLE. Batch mode recreates the table safely.
    with op.batch_alter_table(
        "executions",
        recreate="always",
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "replay_of_execution_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_foreign_key(
            "fk_executions_replay_of_execution_id",
            "executions",
            ["replay_of_execution_id"],
            ["id"],
        )

        batch_op.create_index(
            "ix_executions_replay_of_execution_id",
            ["replay_of_execution_id"],
            unique=False,
        )

    op.create_table(
        "execution_snapshots",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "execution_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "snapshot_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "input_snapshot",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "plan_snapshot",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "output_snapshot",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
        ),
        sa.PrimaryKeyConstraint(
            "id",
        ),
        sa.UniqueConstraint(
            "execution_id",
        ),
    )

    op.create_index(
        "ix_execution_snapshots_id",
        "execution_snapshots",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove Runtime V4 persistence schema."""

    op.drop_index(
        "ix_execution_snapshots_id",
        table_name="execution_snapshots",
    )

    op.drop_table(
        "execution_snapshots",
    )

    with op.batch_alter_table(
        "executions",
        recreate="always",
    ) as batch_op:
        batch_op.drop_index(
            "ix_executions_replay_of_execution_id",
        )

        batch_op.drop_constraint(
            "fk_executions_replay_of_execution_id",
            type_="foreignkey",
        )

        batch_op.drop_column(
            "replay_of_execution_id",
        )
