import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session as OrmSession

from app.models import Batch, Facility, Product, Replenishment, Transaction, User


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
        mismatched_batch = Batch(facility_id=facility.id, batch_number="ASV-MISMATCH-001", product="Legacy medicine label", product_id=canonical.id, expiry=None, storage_status="usable", verified=True, quality_status="verified")
        legacy_batch = Batch(facility_id=facility.id, batch_number="LEGACY-KEEP-001", product=generic.name, product_id=generic.id, expiry=None, storage_status="usable", verified=True, quality_status="verified")
        db.add_all([canonical_batch, mismatched_batch, legacy_batch])
        db.flush()
        db.add(Transaction(facility_id=facility.id, batch_id=legacy_batch.id, kind="receipt", quantity=7, reason="legacy receipt", actor_id=worker.id))
        db.add(Transaction(facility_id=facility.id, batch_id=mismatched_batch.id, kind="receipt", quantity=5, reason="mismatched legacy receipt", actor_id=worker.id))
        db.add(Replenishment(request_code="LEGACY-UNSCOPED-001", facility_id=facility.id, product_id=None, quantity=3, received=0, reason="Unscoped old request", priority="routine", status="pending", created_by=worker.id))
        legacy_batch_id = legacy_batch.id
        mismatched_batch_id = mismatched_batch.id
        legacy_product_id = generic.id
        facility_id = facility.id
        worker_id = worker.id
        db.flush()
        db.commit()

    with migration_engine.begin() as conn:
        conn.execute(text("INSERT INTO consumption_summaries (facility_id, quantity, period_days, source) VALUES (:facility, 50, 1, 'legacy unscoped demand')"), {"facility": facility_id})
        conn.execute(text("INSERT INTO alerts (facility_id, risk_key, severity, explanation, recommendation, inputs, status) VALUES (:facility, 'legacy-stockout', 'high', 'legacy alert', '', '{}', 'active')"), {"facility": facility_id})
        alert_id = conn.execute(text("SELECT MAX(id) FROM alerts")).scalar_one()
        conn.execute(text("INSERT INTO evaluation_labels (alert_id, facility_id, outcome, risk_key, evidence, reviewer_id, period_start, period_end) VALUES (:alert, :facility, 'true_positive', 'legacy-stockout', 'legacy evidence', :worker, '2026-01-01', '2026-01-02')"), {"alert": alert_id, "facility": facility_id, "worker": worker_id})
        conn.execute(text("INSERT INTO daily_stock_observations (facility_id, observed_date, usable_quantity, observed_by, evidence) VALUES (:facility, '2026-01-01', 0, :worker, 'legacy count')"), {"facility": facility_id, "worker": worker_id})

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with migration_engine.connect() as conn:
        product = conn.execute(text("SELECT identifier, name, category, unit, active FROM products WHERE id=:id"), {"id": legacy_product_id}).one()
        batch = conn.execute(text("SELECT batch_number, storage_status, quality_status, verified FROM batches WHERE id=:id"), {"id": legacy_batch_id}).one()
        mismatched = conn.execute(text("SELECT storage_status, quality_status, verified FROM batches WHERE id=:id"), {"id": mismatched_batch_id}).one()
        transaction_count = conn.execute(text("SELECT COUNT(*) FROM inventory_transactions WHERE batch_id=:id"), {"id": legacy_batch_id}).scalar_one()
        report = conn.execute(text("SELECT product_identifier, product_name, batch_identifiers, preserved_batch_count, preserved_transaction_count, original_state FROM asv_scope_migration_reports WHERE product_identifier='LEGACY-AMOXICILLIN'" )).one()
        mismatch_report = conn.execute(text("SELECT batch_identifiers, scope_action FROM asv_scope_migration_reports WHERE product_identifier='ASV-POLY-001' AND scope_action='quarantined_mismatch'" )).one()
        unscoped_demand = conn.execute(text("SELECT preserved_workflow_count FROM asv_scope_migration_reports WHERE product_identifier='UNLINKED-CONSUMPTION'" )).scalar_one()
        unscoped_request = conn.execute(text("SELECT preserved_workflow_count FROM asv_scope_migration_reports WHERE product_identifier='UNLINKED-REQUESTS'" )).scalar_one()
        unscoped_alert = conn.execute(text("SELECT preserved_workflow_count FROM asv_scope_migration_reports WHERE product_identifier='UNLINKED-ALERTS'" )).scalar_one()
        unscoped_label = conn.execute(text("SELECT preserved_workflow_count FROM asv_scope_migration_reports WHERE product_identifier='UNLINKED-EVALUATION'" )).scalar_one()
        unscoped_observation = conn.execute(text("SELECT preserved_workflow_count FROM asv_scope_migration_reports WHERE product_identifier='UNLINKED-OBSERVATIONS'" )).scalar_one()
        canonical = conn.execute(text("SELECT category, unit, active FROM products WHERE identifier='ASV-POLY-001'")).one()

    assert product == ("LEGACY-AMOXICILLIN", "Amoxicillin", "Anti-snake venom", "tablet", 0)
    assert batch == ("LEGACY-KEEP-001", "quarantined", "quarantined", 0)
    assert mismatched == ("quarantined", "quarantined", 0)
    assert json.loads(mismatch_report.batch_identifiers) == ["ASV-MISMATCH-001"]
    assert unscoped_demand == 1
    assert unscoped_request == 1
    assert unscoped_alert == 1
    assert unscoped_label == 1
    assert unscoped_observation == 1
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
        restored_mismatch = conn.execute(text("SELECT storage_status, quality_status, verified FROM batches WHERE id=:id"), {"id": mismatched_batch_id}).one()
        assert "asv_scope_migration_reports" not in inspect(conn).get_table_names()
    assert restored_product == ("Anti-snake venom", "tablet", 1)
    assert restored_batch == ("usable", "verified", 1)
    assert restored_mismatch == ("usable", "verified", 1)


def test_asv_scope_migration_creates_canonical_product_when_catalogue_is_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "catalogue-missing.sqlite"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    ini = Path(__file__).parents[1] / "alembic.ini"
    config = Config(str(ini))
    config.set_main_option("script_location", str(ini.parent / "migrations"))
    command.upgrade(config, "0002_supply_workflows")
    migration_engine = create_engine(url)
    with OrmSession(migration_engine) as db:
        db.add(Product(identifier="LEGACY-DRUG", name="Unrelated medicine", category="Medicine", unit="tablet", active=True))
        db.commit()

    command.upgrade(config, "head")
    with migration_engine.connect() as conn:
        canonical = conn.execute(text("SELECT identifier, name, category, unit, active FROM products WHERE identifier='ASV-POLY-001'")).one_or_none()
        legacy_active = conn.execute(text("SELECT active FROM products WHERE identifier='LEGACY-DRUG'")).scalar_one()

    assert canonical == ("ASV-POLY-001", "Polyvalent Anti-Snake Venom", "Anti-snake venom", "vial", 1)
    assert legacy_active == 0


def test_followup_migrations_upgrade_an_existing_0003_database(tmp_path, monkeypatch):
    db_path = tmp_path / "existing-0003.sqlite"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    ini = Path(__file__).parents[1] / "alembic.ini"
    config = Config(str(ini))
    config.set_main_option("script_location", str(ini.parent / "migrations"))
    command.upgrade(config, "0002_supply_workflows")
    migration_engine = create_engine(url)
    with OrmSession(migration_engine) as db:
        facility = Facility(code="RH-UPG", name="Existing Migration Fixture", kind="Sub-centre", district="Fixture")
        worker = User(name="Existing Fixture Worker", email="existing-migration@example.test", password_hash="unused", role="worker")
        db.add_all([facility, worker]); db.flush()
        facility_id, worker_id = facility.id, worker.id
        db.commit()
    with migration_engine.begin() as conn:
        conn.execute(text("CREATE TABLE asv_scope_migration_reports (id INTEGER PRIMARY KEY, product_identifier VARCHAR(80) NOT NULL, product_name VARCHAR(160) NOT NULL, batch_identifiers TEXT NOT NULL, preserved_batch_count INTEGER NOT NULL, preserved_transaction_count INTEGER NOT NULL, preserved_workflow_count INTEGER NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO consumption_summaries (facility_id, quantity, period_days, source) VALUES (:facility, 40, 2, 'unlinked old demand')"), {"facility": facility_id})
        conn.execute(text("INSERT INTO alerts (facility_id, risk_key, severity, explanation, recommendation, inputs, status) VALUES (:facility, 'old-risk', 'high', 'old alert', '', '{}', 'active')"), {"facility": facility_id})
        alert_id = conn.execute(text("SELECT MAX(id) FROM alerts")).scalar_one()
        conn.execute(text("INSERT INTO evaluation_labels (alert_id, facility_id, outcome, risk_key, evidence, reviewer_id, period_start, period_end) VALUES (:alert, :facility, 'true_positive', 'old-risk', 'old evidence', :worker, '2026-01-01', '2026-01-02')"), {"alert": alert_id, "facility": facility_id, "worker": worker_id})
        conn.execute(text("INSERT INTO daily_stock_observations (facility_id, observed_date, usable_quantity, observed_by, evidence) VALUES (:facility, '2026-01-01', 0, :worker, 'old count')"), {"facility": facility_id, "worker": worker_id})
    command.stamp(config, "0003_asv_only_scope")
    command.upgrade(config, "head")
    with migration_engine.connect() as conn:
        columns = {item["name"] for item in inspect(conn).get_columns("asv_scope_migration_reports")}
        product_id_columns = [
            "product_id" in {item["name"] for item in inspect(conn).get_columns(table)}
            for table in ("consumption_summaries", "alerts", "evaluation_labels", "daily_stock_observations")
        ]
        reports = conn.execute(text("SELECT product_identifier FROM asv_scope_migration_reports ORDER BY product_identifier")).scalars().all()
        canonical = conn.execute(text("SELECT identifier, name, category, unit, active FROM products WHERE identifier='ASV-POLY-001'")).one_or_none()
    assert {"scope_action", "original_state"} <= columns
    assert all(product_id_columns)
    assert {"UNLINKED-CONSUMPTION", "UNLINKED-ALERTS", "UNLINKED-EVALUATION", "UNLINKED-OBSERVATIONS"} <= set(reports)
    assert canonical == ("ASV-POLY-001", "Polyvalent Anti-Snake Venom", "Anti-snake venom", "vial", 1)
