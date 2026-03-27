"""add_recurrence_fields_to_todos

Revision ID: c8d4a2f7b1e9
Revises: 9f3c2a1d7b8e
Create Date: 2026-03-13 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8d4a2f7b1e9"
down_revision: Union[str, None] = "9f3c2a1d7b8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("recurrence_cron", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("recurrence_count", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.drop_column("recurrence_count")
        batch_op.drop_column("recurrence_cron")
        batch_op.drop_column("is_recurring")

