"""Ensure databases already at the ASV quarantine revision have the canonical catalog row."""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "0006_asv_catalog_reconcile"
down_revision = "0005_asv_evaluation_scope"
branch_labels = None
depends_on = None

IDENTIFIER = "ASV-POLY-001"
NAME = "Polyvalent Anti-Snake Venom"
CATEGORY = "Anti-snake venom"
UNIT = "vial"


def upgrade():
    conn = op.get_bind()
    products = conn.execute(text("SELECT id, identifier, name, category, unit, active FROM products ORDER BY id")).mappings().all()
    conflict = next((row for row in products if row["identifier"] == IDENTIFIER and row["name"] != NAME), None)
    if conflict:
        raise RuntimeError(f"Product identifier {IDENTIFIER} is assigned to {conflict['name']!r}; resolve this catalog conflict after backing up the database before retrying the ASV migration.")

    canonical = next((row for row in products if row["identifier"] == IDENTIFIER and row["name"] == NAME), None)
    if canonical:
        if canonical["category"] == CATEGORY and canonical["unit"] == UNIT and canonical["active"]:
            return
        original_state = {"product_active": bool(canonical["active"]), "product_category": canonical["category"], "product_unit": canonical["unit"], "batches": []}
        conn.execute(
            text("INSERT INTO asv_scope_migration_reports (product_identifier, product_name, batch_identifiers, preserved_batch_count, preserved_transaction_count, preserved_workflow_count, scope_action, original_state) VALUES (:identifier, :name, '[]', 0, 0, 0, 'normalized', :state)"),
            {"identifier": IDENTIFIER, "name": NAME, "state": json.dumps(original_state)},
        )
        conn.execute(text("UPDATE products SET category=:category, unit=:unit, active=1 WHERE id=:id"), {"category": CATEGORY, "unit": UNIT, "id": canonical["id"]})
        return

    conn.execute(
        text("INSERT INTO products (identifier, name, category, unit, active) VALUES (:identifier, :name, :category, :unit, 1)"),
        {"identifier": IDENTIFIER, "name": NAME, "category": CATEGORY, "unit": UNIT},
    )
    conn.execute(
        text("INSERT INTO asv_scope_migration_reports (product_identifier, product_name, batch_identifiers, preserved_batch_count, preserved_transaction_count, preserved_workflow_count, scope_action, original_state) VALUES (:identifier, :name, '[]', 0, 0, 0, 'created_canonical', :state)"),
        {"identifier": IDENTIFIER, "name": NAME, "state": json.dumps({"created_by_migration": True})},
    )


def downgrade():
    # Keep the canonical catalogue row on downgrade: application data created
    # since this revision may now reference it, so removing it would be unsafe.
    pass
