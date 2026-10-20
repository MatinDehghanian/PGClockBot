"""Store parent-assigned volume ceiling on OrgPrincipalProvision (L2 cascade).

Revision ID: 0067_child_volume_ceiling
Revises: 0066_external_volume_allocation

NULL / missing means the child has no cascade ceiling (legacy unlimited for the
child itself; counts as zero toward the parent, with a capacity-page warning).
Idempotent; downgrade drops the column.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0067_child_volume_ceiling"
down_revision: Union[str, None] = "0066_external_volume_allocation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "org_principal_provisions"
COLUMN = "volume_ceiling_gb"


def _columns(bind: sa.Connection) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or COLUMN in _columns(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(sa.Column(COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or COLUMN not in _columns(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
