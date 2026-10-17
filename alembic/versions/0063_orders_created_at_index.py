"""Index orders by creation time for the dashboard period and trend queries.

Revision ID: 0063_orders_created_at_index
Revises: 0062_wheel_state_per_shop

The dashboard sums delivered revenue over the last 7, 30 and 60 days; without this index
each refresh scans the whole ``orders`` table. The upgrade is idempotent and the downgrade
only drops the index.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0063_orders_created_at_index"
down_revision: Union[str, None] = "0062_wheel_state_per_shop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "orders"
INDEX = "ix_orders_created_at"


def _index_names(inspector: sa.Inspector) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(TABLE)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLE) and INDEX not in _index_names(inspector):
        op.create_index(INDEX, TABLE, ["created_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLE) and INDEX in _index_names(inspector):
        op.drop_index(INDEX, table_name=TABLE)
