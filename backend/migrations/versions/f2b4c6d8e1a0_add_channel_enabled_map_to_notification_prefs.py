"""add_channel_enabled_map_to_notification_prefs

Revision ID: f2b4c6d8e1a0
Revises: d1a7e4c9b2f3
Create Date: 2026-03-18 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b4c6d8e1a0"
down_revision: Union[str, None] = "d1a7e4c9b2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
	bind = op.get_bind()
	inspector = sa.inspect(bind)
	return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
	cols = _column_names("notification_prefs")
	if "channel_enabled_map" not in cols:
		with op.batch_alter_table("notification_prefs", schema=None) as batch_op:
			batch_op.add_column(
				sa.Column("channel_enabled_map", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
			)

	op.execute(
		"""
		UPDATE notification_prefs
		SET channel_enabled_map =
			'{"in_app":' || CASE WHEN in_app_enabled THEN 'true' ELSE 'false' END ||
			',"email_workflow":' || CASE WHEN email_enabled THEN 'true' ELSE 'false' END ||
			',"wechat_workflow":' || CASE WHEN wechat_enabled THEN 'true' ELSE 'false' END ||
			'}'
		WHERE channel_enabled_map IS NULL OR channel_enabled_map = '{}'
		"""
	)


def downgrade() -> None:
	cols = _column_names("notification_prefs")
	if "channel_enabled_map" in cols:
		with op.batch_alter_table("notification_prefs", schema=None) as batch_op:
			batch_op.drop_column("channel_enabled_map")


