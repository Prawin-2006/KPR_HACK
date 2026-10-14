"""Preserve and quarantine inventory outside the canonical ASV domain."""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0003_asv_only_scope"
down_revision = "0002_supply_workflows"
branch_labels = None
depends_on = None

ASV_IDENTIFIER = "ASV-POLY-001"
ASV_NAME = "Polyvalent Anti-Snake Venom"


def _count(conn, table, clause, parameters):
    if table not in inspect(conn).get_table_names():
        return 0
    return conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {clause}"), parameters).scalar_one()


def _preserved_workflow_count(conn, batch_ids, product_id):
    if not batch_ids:
        return _count(conn, "replenishments", "product_id=:pid", {"pid": product_id}) + _count(conn, "reorder_drafts", "product_id=:pid", {"pid": product_id})
    ids = ",".join(str(int(batch_id)) for batch_id in batch_ids)
    total = 0
    for table, column in (
        ("stock_transfers", "batch_id"),
        ("count_lines", "batch_id"),
        ("discrepancies", "batch_id"),
        ("batch_events", "batch_id"),
    ):
        total += _count(conn, table, f"{column} IN ({ids})", {})
    total += _count(conn, "replenishments", "product_id=:pid", {"pid": product_id})
    total += _count(conn, "reorder_drafts", "product_id=:pid", {"pid": product_id})
    return total


def _insert_report(conn, identifier, name, batch_rows, product_id, action, original_state):
    batch_ids = [row["id"] for row in batch_rows]
    batch_numbers = sorted(row["batch_number"] for row in batch_rows)
    ids = ",".join(str(int(batch_id)) for batch_id in batch_ids)
    transaction_count = _count(conn, "inventory_transactions", f"batch_id IN ({ids})", {}) if ids else 0
    workflow_count = _preserved_workflow_count(conn, batch_ids, product_id)
    conn.execute(
        text(
            "INSERT INTO asv_scope_migration_reports "
            "(product_identifier, product_name, batch_identifiers, preserved_batch_count, "
            "preserved_transaction_count, preserved_workflow_count, scope_action, original_state) "
            "VALUES (:identifier, :name, :batches, :batch_count, :transaction_count, :workflow_count, :action, :original_state)"
        ),
        {
            "identifier": identifier,
            "name": name,
            "batches": json.dumps(batch_numbers),
            "batch_count": len(batch_rows),
            "transaction_count": transaction_count,
            "workflow_count": workflow_count,
            "action": action,
            "original_state": json.dumps(original_state),
        },
    )


def upgrade():
    conn = op.get_bind()
    tables = set(inspect(conn).get_table_names())
    if "asv_scope_migration_reports" not in tables:
        op.create_table(
            "asv_scope_migration_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_identifier", sa.String(80), nullable=False),
            sa.Column("product_name", sa.String(160), nullable=False),
            sa.Column("batch_identifiers", sa.Text(), nullable=False),
            sa.Column("preserved_batch_count", sa.Integer(), nullable=False),
            sa.Column("preserved_transaction_count", sa.Integer(), nullable=False),
            sa.Column("preserved_workflow_count", sa.Integer(), nullable=False),
            sa.Column("scope_action", sa.String(30), nullable=False),
            sa.Column("original_state", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    products = conn.execute(text("SELECT id, identifier, name FROM products ORDER BY id")).mappings().all()
    canonical = next((row for row in products if row["identifier"] == ASV_IDENTIFIER and row["name"] == ASV_NAME), None)
    conflicting_identifier = next((row for row in products if row["identifier"] == ASV_IDENTIFIER and row["name"] != ASV_NAME), None)
    if conflicting_identifier:
        raise RuntimeError(
            f"Product identifier {ASV_IDENTIFIER} is assigned to {conflicting_identifier['name']!r}; "
            "resolve this conflict after backing up the database before retrying the ASV migration."
        )

    if canonical:
        original_product = conn.execute(
            text("SELECT category, unit, active FROM products WHERE id=:id"), {"id": canonical["id"]}
        ).mappings().one()
        original_batches = conn.execute(
            text("SELECT id, batch_number, storage_status, quality_status, verified FROM batches WHERE product_id=:pid ORDER BY batch_number"),
            {"pid": canonical["id"]},
        ).mappings().all()
        original_state = {
            "product_active": bool(original_product["active"]),
            "product_category": original_product["category"],
            "product_unit": original_product["unit"],
            "batches": [
                {"id": row["id"], "batch_number": row["batch_number"], "storage_status": row["storage_status"], "quality_status": row["quality_status"], "verified": bool(row["verified"])}
                for row in original_batches
            ],
        }
        if original_product["category"] != "Anti-snake venom" or original_product["unit"] != "vial" or not original_product["active"]:
            _insert_report(conn, ASV_IDENTIFIER, ASV_NAME, original_batches, canonical["id"], "normalized", original_state)
        conn.execute(
            text("UPDATE products SET category='Anti-snake venom', unit='vial', active=1 WHERE id=:id"),
            {"id": canonical["id"]},
        )

    for product in products:
        if canonical and product["id"] == canonical["id"]:
            continue
        batch_rows = conn.execute(
            text("SELECT id, batch_number, storage_status, quality_status, verified FROM batches WHERE product_id=:pid ORDER BY batch_number"),
            {"pid": product["id"]},
        ).mappings().all()
        original_product = conn.execute(
            text("SELECT category, unit, active FROM products WHERE id=:pid"), {"pid": product["id"]}
        ).mappings().one()
        original_state = {
            "product_active": bool(original_product["active"]),
            "product_category": original_product["category"],
            "product_unit": original_product["unit"],
            "batches": [
                {"id": row["id"], "batch_number": row["batch_number"], "storage_status": row["storage_status"], "quality_status": row["quality_status"], "verified": bool(row["verified"])}
                for row in batch_rows
            ],
        }
        _insert_report(conn, product["identifier"], product["name"], batch_rows, product["id"], "quarantined", original_state)
        conn.execute(text("UPDATE products SET active=0 WHERE id=:pid"), {"pid": product["id"]})
        conn.execute(
            text("UPDATE batches SET storage_status='quarantined', quality_status='quarantined', verified=0 WHERE product_id=:pid"),
            {"pid": product["id"]},
        )

    unlinked = conn.execute(
        text("SELECT id, batch_number, storage_status, quality_status, verified FROM batches WHERE product_id IS NULL ORDER BY batch_number")
    ).mappings().all()
    if unlinked:
        original_state = {
            "product_active": None,
            "product_category": None,
            "product_unit": None,
            "batches": [
                {"id": row["id"], "batch_number": row["batch_number"], "storage_status": row["storage_status"], "quality_status": row["quality_status"], "verified": bool(row["verified"])}
                for row in unlinked
            ],
        }
        _insert_report(conn, "UNLINKED", "Unlinked or unrecognized batch product", unlinked, -1, "quarantined", original_state)
        ids = ",".join(str(int(row["id"])) for row in unlinked)
        conn.execute(
            text(f"UPDATE batches SET storage_status='quarantined', quality_status='quarantined', verified=0 WHERE id IN ({ids})")
        )


def downgrade():
    conn = op.get_bind()
    if "asv_scope_migration_reports" not in inspect(conn).get_table_names():
        return
    rows = conn.execute(text("SELECT product_identifier, original_state FROM asv_scope_migration_reports ORDER BY id DESC")).mappings().all()
    for row in rows:
        state = json.loads(row["original_state"])
        if row["product_identifier"] != "UNLINKED":
            conn.execute(
                text("UPDATE products SET category=:category, unit=:unit, active=:active WHERE identifier=:identifier"),
                {"category": state["product_category"], "unit": state["product_unit"], "active": state["product_active"], "identifier": row["product_identifier"]},
            )
        for batch in state["batches"]:
            conn.execute(
                text("UPDATE batches SET storage_status=:storage, quality_status=:quality, verified=:verified WHERE id=:id"),
                {"storage": batch["storage_status"], "quality": batch["quality_status"], "verified": batch["verified"], "id": batch["id"]},
            )
    op.drop_table("asv_scope_migration_reports")
