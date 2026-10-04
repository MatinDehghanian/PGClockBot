"""Add optional sales-plan categories without changing existing catalogs."""

from alembic import op
import sqlalchemy as sa

revision = "0031_plan_categories"
down_revision = "0030_legacy_wallet_isolation_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline metadata includes new columns on a fresh installation.
    bind = op.get_bind()
    if "category" not in {c["name"] for c in sa.inspect(bind).get_columns("plans")}:
        op.add_column("plans", sa.Column("category", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "category")
