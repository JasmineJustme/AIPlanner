"""add_execution_mode_to_todos

Revision ID: 6b9f1c2d4e5a
Revises: b2a52180e78f
Create Date: 2026-03-10 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b9f1c2d4e5a"
down_revision: Union[str, None] = "b2a52180e78f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "execution_mode",
                sa.String(length=20),
                nullable=False,
                server_default="system",
            )
        )


def downgrade() -> None:

    with op.batch_alter_table("todos", schema=None) as batch_op:
        batch_op.drop_column("execution_mode")
