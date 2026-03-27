"""add_agent_id_to_datasources

Revision ID: 9f3c2a1d7b8e
Revises: 6b9f1c2d4e5a
Create Date: 2026-03-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f3c2a1d7b8e"
down_revision: Union[str, None] = "6b9f1c2d4e5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("datasources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("agent_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_datasources_agent_id", ["agent_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_datasources_agent_id_agents",
            "agents",
            ["agent_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("datasources", schema=None) as batch_op:
        batch_op.drop_constraint("fk_datasources_agent_id_agents", type_="foreignkey")
        batch_op.drop_index("ix_datasources_agent_id")
        batch_op.drop_column("agent_id")

