# ASV-Only Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce that every active VenoTrack inventory workflow manages only the canonical polyvalent ASV vial product while preserving and reporting ambiguous legacy records.

**Architecture:** Add a shared server-side ASV identity/eligibility layer and an additive Alembic migration. Non-canonical legacy products are deactivated and their batches quarantined without deleting historical records; active endpoints and calculations exclude them. Remove arbitrary product creation from the UI, keep ASV batch workflows intact, and document backup and review steps.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy 2, Alembic, pytest, React 18, TypeScript, Vite.

**Spec:** `docs/superpowers/specs/2026-10-14-asv-only-enforcement-design.md`

## Global Constraints

- The supported product is `ASV-POLY-001`, “Polyvalent Anti-Snake Venom”, unit `vial`.
- Do not infer ASV identity from a legacy category alone.
- Preserve legacy product, batch, transaction, and linked workflow rows; do not silently delete or relabel them.
- Exclude inactive/non-canonical products and their batches from active APIs, stock calculations, forecasts, transfer suggestions, and reports.
- Existing expiry, quality, verification, reconciliation, risk, transfer, replenishment, role permissions, and synthetic-data behaviors continue to function.
- The application remains online-only, ASV-only, and synthetic-data labeled.

## Review Focus

- Legacy rows previously mislabeled as ASV by migration 0002 remain excluded and retain their history; test the migration from a generic-product fixture.
- A direct API request cannot create or reference another product or batch; test unsupported product creation and inactive batch transaction/request/transfer references.
- A valid ASV batch retains vial quantity consistency and eligibility rules; test that its current workflows still pass.
- Reports and aggregate inventory cannot leak quarantined legacy quantities; test dashboard totals, facility batch data, and CSV output after migration.
- Repeated migration/seed startup remains safe; test migration idempotence and the canonical product uniqueness behavior.

---

### Task 1: Canonical ASV identity and safe legacy migration

**Files:**
- Create: `backend/app/asv_scope.py`
- Create: `backend/migrations/versions/0003_asv_only_scope.py`
- Create: `backend/migrations/versions/0004_asv_forecast_scope.py`
- Create: `backend/migrations/versions/0005_asv_evaluation_scope.py`
- Create: `backend/migrations/versions/0006_asv_catalog_reconcile.py`
- Test: `backend/tests/test_asv_scope.py`
- Modify: `backend/tests/test_migrations.py` (create if absent)

**Interfaces:**
- Produces `ASV_PRODUCT_IDENTIFIER = "ASV-POLY-001"`, `ASV_PRODUCT_NAME = "Polyvalent Anti-Snake Venom"`, `ASV_CATEGORY = "Anti-snake venom"`, `ASV_UNIT = "vial"`, plus `is_supported_product(product) -> bool` and `is_supported_batch(batch, product) -> bool`.
- Migration preserves all out-of-scope rows, changes non-canonical products to inactive and batches to quarantined, links demand, alerts, labels, and stock observations to the ASV product, ensures the ASV catalog exists for databases already at revision 0003, and reports unlinked legacy rows to administrators.

- [x] **Step 1: Write failing scope and migration tests**

Add `test_supported_product_requires_exact_canonical_identity`, `test_supported_batch_requires_active_supported_product`, and a migration test that creates one canonical and one generic legacy product with a batch and receipt, upgrades to revision 0003, and asserts canonical fields are normalized while generic product/batch/history remain present, inactive/quarantined, and listed in the migration report.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_asv_scope.py tests/test_migrations.py -q`
Expected: FAIL because the scope helpers, migration, and migration tests do not yet exist.

- [x] **Step 3: Implement canonical identity and additive migration**

Create a migration report table containing product identifier/name, affected batch identifiers, preserved-row counts, and migration timestamp. Match ASV only by the exact canonical identifier and name; never promote other products based on category. Ensure exactly one supported product remains active, quarantine batches attached to other products, and preserve all existing transaction/workflow records.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend; python -m pytest tests/test_asv_scope.py tests/test_migrations.py -q`
Expected: PASS, including preservation of the generic fixture's history.

- [x] **Step 5: Commit**

Commit the helper, migration, and tests as `feat: add safe ASV-only data migration`.

### Task 2: Enforce ASV-only on API reads and writes

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`
- Test: `backend/tests/test_supply_workflows.py`
- Test: `backend/tests/test_replenishment.py`

**Interfaces:**
- Consumes the exact identity helpers from Task 1.
- Product list returns only the canonical ASV product; product writes accept only its exact identity and vial unit, with duplicate identity returning conflict.
- All write paths reject inactive or non-canonical products/batches with a client error before ledger or workflow rows are written.

- [x] **Step 1: Write failing endpoint tests**

Add tests for rejecting unrelated product creation, hiding an inactive legacy product from `/products`, rejecting issue/count/transfer proposals against an inactive batch, and rejecting replenishment receipt or reorder draft references to an inactive product. Assert these rejected writes create no transactions or workflow rows. Add a successful canonical ASV product/batch workflow assertion.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_api.py tests/test_supply_workflows.py tests/test_replenishment.py -q`
Expected: FAIL because endpoints currently expose generic products and do not consistently enforce product eligibility.

- [x] **Step 3: Implement API enforcement and active-data filtering**

Use a shared query/helper for canonical active products/batches in facility serialization, batch endpoints, ledger writes, risk/reorder calculations, replenishments, transfer suggestions/list/proposal/receipt, dashboard aggregates, and CSV/evaluation paths. Validate batch/product identity at every endpoint accepting identifiers. Return only canonical product records from `/products`, and reject unsupported `POST /products` requests.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend; python -m pytest tests/test_api.py tests/test_supply_workflows.py tests/test_replenishment.py -q`
Expected: PASS with legacy rows absent from active data and existing ASV workflows intact.

- [x] **Step 5: Commit**

Commit API and regression tests as `feat: enforce ASV-only inventory APIs`.

### Task 3: Make the frontend ASV-only and clear

**Files:**
- Modify: `frontend/src/workflows.tsx`
- Modify: `frontend/src/app.tsx`
- Modify: `frontend/src/api.ts` only if response typing requires it
- Test: `frontend` production build

**Interfaces:**
- Consumes the canonical ASV-only product response from `/products`.
- Retains batch selection and current worker/officer permissions while removing generic product creation and arbitrary product-selection affordances.

- [x] **Step 1: Inspect and record current catalogue form behavior**

Identify the workflow section that creates a product and the batch form that selects `product_id`. Confirm API clients rely on returned ASV product identifiers.

- [x] **Step 2: Update UI terminology and catalogue controls**

Remove product creation controls and their submit handler. Present the fixed ASV product as context, retain batch creation with the canonical product selected implicitly or shown read-only, and use “ASV vials” consistently for quantity labels in workflows and stock summaries.

- [x] **Step 3: Build the frontend**

Run: `cd frontend; npm run build`
Expected: Vite production build succeeds with no TypeScript errors.

- [x] **Step 4: Commit**

Commit UI changes as `feat: make inventory UI ASV-specific`.

### Task 4: Seed, reporting, documentation, and full verification

**Files:**
- Modify: `backend/app/seed.py`
- Modify: `backend/app/main.py` (migration report endpoint and ASV report headers/labels if needed)
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_supply_workflows.py`
- Modify: `README.md`

**Interfaces:**
- Migration report is administrator-only and describes preserved/excluded legacy records without returning generic stock as active inventory.
- Seed/reset always creates only the canonical ASV product and ASV batches.

- [x] **Step 1: Write failing reporting and seed tests**

Add tests that dashboard/facility/CSV outputs count only canonical ASV vials, that an administrator can inspect the migration report while a worker cannot, and that reset produces only the canonical product.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend; python -m pytest tests/test_api.py tests/test_supply_workflows.py -q`
Expected: FAIL because ASV-only totals/report labels and the admin migration report are not implemented.

- [x] **Step 3: Implement and document reporting behavior**

Ensure seed/reset is canonical and synthetic. Add the admin report endpoint, ASV-specific CSV headings/filename, and README guidance for backing up SQLite/MySQL before migration, reviewing preserved legacy exclusions, migration commands, and the fixed ASV-vial catalogue scope.

- [x] **Step 4: Run complete verification**

Run: `cd backend; python -m pytest tests -q`, then `cd frontend; npm run build`.
Expected: all backend tests pass and Vite builds successfully. Also run the migration preservation test from a generic legacy fixture.

- [x] **Step 5: Commit**

Commit seed, reports, tests, and documentation as `docs: finalize ASV-only inventory scope`.

