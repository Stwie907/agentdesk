"""add execution failure metadata

Revision ID: 5e76747a8551
Revises: fd7997f4be88
Create Date: 2026-08-29 13:37:32.726941
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5e76747a8551"
down_revision: Union[str, Sequence[str], None] = "fd7997f4be88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retry and failure metadata to executions."""
    op.add_column(
        "executions",
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "executions",
        sa.Column(
            "failure_type",
            sa.String(),
            nullable=True,
        ),
    )
    op.add_column(
        "executions",
        sa.Column(
            "failure_message",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove retry and failure metadata from executions."""
    op.drop_column("executions", "failure_message")
    op.drop_column("executions", "failure_type")
    op.drop_column("executions", "retry_count")
