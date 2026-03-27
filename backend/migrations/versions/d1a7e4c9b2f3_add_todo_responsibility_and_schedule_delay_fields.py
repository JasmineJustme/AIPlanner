"""add_todo_responsibility_and_schedule_delay_fields

Revision ID: d1a7e4c9b2f3
Revises: e3f9a1b7c6d2
Create Date: 2026-03-18 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1a7e4c9b2f3"
down_revision: Union[str, None] = "e3f9a1b7c6d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    schedule_cols = _column_names("schedule_tasks")
    with op.batch_alter_table("schedule_tasks", schema=None) as batch_op:
        if "original_scheduled_at" not in schedule_cols:
            batch_op.add_column(sa.Column("original_scheduled_at", sa.DateTime(), nullable=True))
        if "current_scheduled_at" not in schedule_cols:
            batch_op.add_column(sa.Column("current_scheduled_at", sa.DateTime(), nullable=True))
        if "delay_count" not in schedule_cols:
            batch_op.add_column(sa.Column("delay_count", sa.Integer(), nullable=False, server_default="0"))

    schedule_cols = _column_names("schedule_tasks")
    if "original_scheduled_at" in schedule_cols:
        op.execute("UPDATE schedule_tasks SET original_scheduled_at = scheduled_at WHERE original_scheduled_at IS NULL")
    if "current_scheduled_at" in schedule_cols:
        op.execute("UPDATE schedule_tasks SET current_scheduled_at = scheduled_at WHERE current_scheduled_at IS NULL")

    schedule_cols = _column_names("schedule_tasks")
    with op.batch_alter_table("schedule_tasks", schema=None) as batch_op:
        if "original_scheduled_at" in schedule_cols:
            batch_op.alter_column("original_scheduled_at", existing_type=sa.DateTime(), nullable=False)
        if "current_scheduled_at" in schedule_cols:
            batch_op.alter_column("current_scheduled_at", existing_type=sa.DateTime(), nullable=False)

    todo_cols = _column_names("todos")
    with op.batch_alter_table("todos", schema=None) as batch_op:
        if "responsibility_ids" not in todo_cols:
            batch_op.add_column(sa.Column("responsibility_ids", sa.JSON(), nullable=True))
        if "responsibility_titles" not in todo_cols:
            batch_op.add_column(sa.Column("responsibility_titles", sa.JSON(), nullable=True))


def downgrade() -> None:
    schedule_cols = _column_names("schedule_tasks")
    with op.batch_alter_table("schedule_tasks", schema=None) as batch_op:
        if "delay_count" in schedule_cols:
            batch_op.drop_column("delay_count")
        if "current_scheduled_at" in schedule_cols:
            batch_op.drop_column("current_scheduled_at")
        if "original_scheduled_at" in schedule_cols:
            batch_op.drop_column("original_scheduled_at")

    todo_cols = _column_names("todos")
    with op.batch_alter_table("todos", schema=None) as batch_op:
        if "responsibility_titles" in todo_cols:
            batch_op.drop_column("responsibility_titles")
        if "responsibility_ids" in todo_cols:
            batch_op.drop_column("responsibility_ids")


