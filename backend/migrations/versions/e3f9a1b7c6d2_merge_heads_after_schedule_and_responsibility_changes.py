"""merge_heads_after_schedule_and_responsibility_changes

Revision ID: e3f9a1b7c6d2
Revises: c4d8e2f1a9b7, c8d4a2f7b1e9
Create Date: 2026-03-18 09:45:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "e3f9a1b7c6d2"
down_revision: Union[str, Sequence[str], None] = ("c4d8e2f1a9b7", "c8d4a2f7b1e9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

