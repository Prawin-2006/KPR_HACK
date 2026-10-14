"""Link alerts, labels, and stock observations to the ASV product."""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0005_asv_evaluation_scope"
down_revision = "0004_asv_forecast_scope"
branch_labels = None
depends_on = None


def _add_product_link(conn, table):
    if "product_id" in {item["name"] for item in inspect(conn).get_columns(table)}:
        return
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(f"fk_{table}_product_id_products", "products", ["product_id"], ["id"])
        batch_op.create_index(f"ix_{table}_product_id", ["product_id"])


def _report(conn, identifier, name, rows):
    if not rows:
        return
    conn.execute(
        text("INSERT INTO asv_scope_migration_reports (product_identifier, product_name, batch_identifiers, preserved_batch_count, preserved_transaction_count, preserved_workflow_count, scope_action, original_state) VALUES (:identifier, :name, '[]', 0, 0, :count, 'unscoped_excluded', :state)"),
        {"identifier": identifier, "name": name, "count": len(rows), "state": json.dumps({"rows": [dict(row) for row in rows]})},
    )


def upgrade():
    conn = op.get_bind()
    tables = set(inspect(conn).get_table_names())
    for table in ("alerts", "evaluation_labels", "daily_stock_observations"):
        if table in tables:
            _add_product_link(conn, table)

    alerts = conn.execute(text("SELECT id, facility_id, risk_key, severity, status FROM alerts WHERE product_id IS NULL ORDER BY id")).mappings().all() if "alerts" in tables else []
    labels = conn.execute(text("SELECT id, alert_id, facility_id, outcome, risk_key FROM evaluation_labels WHERE product_id IS NULL ORDER BY id")).mappings().all() if "evaluation_labels" in tables else []
    observations = conn.execute(text("SELECT id, facility_id, observed_date, usable_quantity FROM daily_stock_observations WHERE product_id IS NULL ORDER BY id")).mappings().all() if "daily_stock_observations" in tables else []
    _report(conn, "UNLINKED-ALERTS", "Unlinked historical alerts", alerts)
    _report(conn, "UNLINKED-EVALUATION", "Unlinked historical evaluation labels", labels)
    _report(conn, "UNLINKED-OBSERVATIONS", "Unlinked historical stock observations", observations)


def downgrade():
    conn = op.get_bind()
    tables = set(inspect(conn).get_table_names())
    for table in ("daily_stock_observations", "evaluation_labels", "alerts"):
        if table not in tables or "product_id" not in {item["name"] for item in inspect(conn).get_columns(table)}:
            continue
        with op.batch_alter_table(table) as batch_op:
            index_name = f"ix_{table}_product_id"
            if index_name in {idx["name"] for idx in inspect(conn).get_indexes(table)}:
                batch_op.drop_index(index_name)
            fk = next((item for item in inspect(conn).get_foreign_keys(table) if item.get("constrained_columns") == ["product_id"]), None)
            if fk and fk.get("name"):
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
            batch_op.drop_column("product_id")
