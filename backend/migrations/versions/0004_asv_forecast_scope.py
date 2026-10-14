"""Link consumption history to a product and report unscoped legacy demand."""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0004_asv_forecast_scope"
down_revision = "0003_asv_only_scope"
branch_labels = None
depends_on = None


def _report(conn, identifier, name, rows):
    if not rows:
        return
    columns = {item["name"] for item in inspect(conn).get_columns("asv_scope_migration_reports")}
    if "scope_action" not in columns:
        op.add_column("asv_scope_migration_reports", sa.Column("scope_action", sa.String(30), nullable=False, server_default="quarantined"))
    if "original_state" not in columns:
        op.add_column("asv_scope_migration_reports", sa.Column("original_state", sa.Text(), nullable=False, server_default="{}"))
    conn.execute(
        text("INSERT INTO asv_scope_migration_reports (product_identifier, product_name, batch_identifiers, preserved_batch_count, preserved_transaction_count, preserved_workflow_count, scope_action, original_state) VALUES (:identifier, :name, '[]', 0, 0, :count, 'unscoped_excluded', :state)"),
        {"identifier": identifier, "name": name, "count": len(rows), "state": json.dumps({"rows": [dict(row) for row in rows]})},
    )


def _add_product_link(conn, table):
    columns = {item["name"] for item in inspect(conn).get_columns(table)}
    if "product_id" in columns:
        return
    index_name = f"ix_{table}_product_id"
    fk_name = f"fk_{table}_product_id_products"
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(fk_name, "products", ["product_id"], ["id"])
        batch_op.create_index(index_name, ["product_id"])


def upgrade():
    conn = op.get_bind()
    tables = set(inspect(conn).get_table_names())
    if "consumption_summaries" not in tables:
        return

    report_columns = {item["name"] for item in inspect(conn).get_columns("asv_scope_migration_reports")}
    if "scope_action" not in report_columns:
        op.add_column("asv_scope_migration_reports", sa.Column("scope_action", sa.String(30), nullable=False, server_default="quarantined"))
    if "original_state" not in report_columns:
        op.add_column("asv_scope_migration_reports", sa.Column("original_state", sa.Text(), nullable=False, server_default="{}"))

    _add_product_link(conn, "consumption_summaries")

    demand = conn.execute(text("SELECT id, facility_id, quantity, period_days, source FROM consumption_summaries WHERE product_id IS NULL ORDER BY id")).mappings().all()
    requests = conn.execute(text("SELECT id, request_code, facility_id, quantity, received, status FROM replenishments WHERE product_id IS NULL ORDER BY id")).mappings().all() if "replenishments" in tables else []
    _report(conn, "UNLINKED-CONSUMPTION", "Unlinked historical consumption summaries", demand)
    _report(conn, "UNLINKED-REQUESTS", "Unlinked historical replenishment requests", requests)


def downgrade():
    conn = op.get_bind()
    tables = set(inspect(conn).get_table_names())
    for table in ("consumption_summaries",):
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
