"""add_responsibilities_table

Revision ID: c4d8e2f1a9b7
Revises: 9f3c2a1d7b8e
Create Date: 2026-03-13 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d8e2f1a9b7"
down_revision: Union[str, None] = "9f3c2a1d7b8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "responsibilities",
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["responsibilities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_responsibilities_parent_id"), "responsibilities", ["parent_id"], unique=False)
    op.create_index(op.f("ix_responsibilities_user_id"), "responsibilities", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_responsibilities_user_id"), table_name="responsibilities")
    op.drop_index(op.f("ix_responsibilities_parent_id"), table_name="responsibilities")
    op.drop_table("responsibilities")

