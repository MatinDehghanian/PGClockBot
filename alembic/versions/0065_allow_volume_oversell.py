"""Add ResellerProfile.allow_volume_oversell for the L1 volume allocation gate.

Revision ID: 0065_allow_volume_oversell
Revises: 0064_settlement_notified_at

Existing shops keep oversell on (server_default true) so behaviour does not change
until an Owner turns the switch off. New shops get false in application code.
Idempotent on SQLite and PostgreSQL; downgrade drops the column and keeps rows.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0065_allow_volume_oversell"
down_revision: Union[str, None] = "0064_settlement_notified_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "reseller_profiles"
COLUMN = "allow_volume_oversell"


def _columns(bind: sa.Connection) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or COLUMN in _columns(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(
            sa.Column(
                COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or COLUMN not in _columns(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
