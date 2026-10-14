import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session as OrmSession

from app.models import Batch, Facility, Product, Transaction, User


def test_asv_scope_migration_preserves_and_reports_legacy_inventory(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.sqlite"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    ini = Path(__file__).parents[1] / "alembic.ini"
    config = Config(str(ini))
    config.set_main_option("script_location", str(ini.parent / "migrations"))

    command.upgrade(config, "0002_supply_workflows")
    migration_engine = create_engine(url)
    with OrmSession(migration_engine) as db:
        facility = Facility(code="RH-MIG", name="Migration Fixture", kind="Sub-centre", district="Fixture")
        db.add(facility)
        db.flush()
        worker = User(name="Fixture Worker", email="migration@example.test", password_hash="unused", role="worker", facility_id=facility.id)
        canonical = Product(identifier="ASV-POLY-001", name="Polyvalent Anti-Snake Venom", category="Legacy category", unit="box")
        generic = Product(identifier="LEGACY-AMOXICILLIN", name="Amoxicillin", category="Anti-snake venom", unit="tablet")
        db.add_all([worker, canonical, generic])
        db.flush()
        canonical_batch = Batch(facility_id=facility.id, batch_number="ASV-KEEP-001", product=canonical.name, product_id=canonical.id, expiry=None, storage_status="usable", verified=True, quality_status="verified")
        legacy_batch = Batch(facility_id=facility.id, batch_number="LEGACY-KEEP-001", product=generic.name, product_id=generic.id, expiry=None, storage_status="usable", verified=True, quality_status="verified")
        db.add_all([canonical_batch, legacy_batch])
        db.flush()
        db.add(Transaction(facility_id=facility.id, batch_id=legacy_batch.id, kind="receipt", quantity=7, reason="legacy receipt", actor_id=worker.id))
        legacy_batch_id = legacy_batch.id
        legacy_product_id = generic.id
        db.commit()

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with migration_engine.connect() as conn:
        product = conn.execute(text("SELECT identifier, name, category, unit, active FROM products WHERE id=:id"), {"id": legacy_product_id}).one()
        batch = conn.execute(text("SELECT batch_number, storage_status, quality_status, verified FROM batches WHERE id=:id"), {"id": legacy_batch_id}).one()
        transaction_count = conn.execute(text("SELECT COUNT(*) FROM inventory_transactions WHERE batch_id=:id"), {"id": legacy_batch_id}).scalar_one()
        report = conn.execute(text("SELECT product_identifier, product_name, batch_identifiers, preserved_batch_count, preserved_transaction_count, original_state FROM asv_scope_migration_reports WHERE product_identifier='LEGACY-AMOXICILLIN'" )).one()
        canonical = conn.execute(text("SELECT category, unit, active FROM products WHERE identifier='ASV-POLY-001'")).one()

    assert product == ("LEGACY-AMOXICILLIN", "Amoxicillin", "Anti-snake venom", "tablet", 0)
    assert batch == ("LEGACY-KEEP-001", "quarantined", "quarantined", 0)
    assert transaction_count == 1
    assert report.product_name == "Amoxicillin"
    assert json.loads(report.batch_identifiers) == ["LEGACY-KEEP-001"]
    assert report.preserved_batch_count == 1
    assert report.preserved_transaction_count == 1
    assert json.loads(report.original_state) == {
        "product_active": True,
        "product_category": "Anti-snake venom",
        "product_unit": "tablet",
        "batches": [{"id": legacy_batch_id, "batch_number": "LEGACY-KEEP-001", "storage_status": "usable", "quality_status": "verified", "verified": True}],
    }
    assert canonical == ("Anti-snake venom", "vial", 1)

    command.downgrade(config, "0002_supply_workflows")
    with migration_engine.connect() as conn:
        restored_product = conn.execute(text("SELECT category, unit, active FROM products WHERE id=:id"), {"id": legacy_product_id}).one()
        restored_batch = conn.execute(text("SELECT storage_status, quality_status, verified FROM batches WHERE id=:id"), {"id": legacy_batch_id}).one()
        assert "asv_scope_migration_reports" not in inspect(conn).get_table_names()
    assert restored_product == ("Anti-snake venom", "tablet", 1)
    assert restored_batch == ("usable", "verified", 1)
