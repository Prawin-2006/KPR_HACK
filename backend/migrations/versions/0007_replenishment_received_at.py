"""Record the time replenishment deliveries are received."""

from alembic import op
import sqlalchemy as sa

revision = "0007_replenishment_received_at"
down_revision = "0006_asv_catalog_reconcile"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("replenishments", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("replenishments", "received_at")
