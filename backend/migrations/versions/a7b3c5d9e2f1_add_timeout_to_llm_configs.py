"""add_timeout_to_llm_configs

Revision ID: a7b3c5d9e2f1
Revises: f2b4c6d8e1a0
Create Date: 2026-03-27 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b3c5d9e2f1"
down_revision: Union[str, None] = "f2b4c6d8e1a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    cols = _column_names("llm_configs")
    if "timeout" not in cols:
        with op.batch_alter_table("llm_configs", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("timeout", sa.Integer(), nullable=False, server_default=sa.text("180"))
            )


def downgrade() -> None:
    cols = _column_names("llm_configs")
    if "timeout" in cols:
        with op.batch_alter_table("llm_configs", schema=None) as batch_op:
            batch_op.drop_column("timeout")
