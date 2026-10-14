# VenoTrack Supply Workflow Extension Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current workspace. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Extend VenoTrack with quality-aware stock, physical reconciliation, hierarchical facilities, explainable reordering, authorized transfers, and auditable alert response/evaluation.

**Architecture:** Evolve the current FastAPI/SQLAlchemy API and React client with additive Alembic migrations. Keep inventory derived from immutable paired ledger transactions. Build each operational workflow behind server authorization and service functions, then expose it through existing pages and test the complete workflows against an isolated seeded database.

**Tech Stack:** Existing React 18/TypeScript/Vite/TanStack Query/Leaflet; FastAPI/Pydantic/SQLAlchemy 2/Alembic; SQLite for local/test, MySQL-compatible models; Pytest.

**Spec:** `docs/superpowers/specs/2026-10-14-venotrack-mvp-design.md` (approved E-Aushadhi / DVDMS-inspired extension section)

## Global Constraints
- Online-only; all sample records are synthetic and labeled.
- Do not copy proprietary code or imply e-Aushadhi/DVMS integration or unsupported capability gaps.
- Never count expired, damaged, quarantined, rejected, or quality-pending stock as usable.
- Never overwrite balances; corrections and transfers are immutable ledger transactions.
- Indent recommendations never submit external purchase orders automatically.
- Transfers require fresh source verification, role approval, storage/transport checks, and paired source/destination ledger entries.
- Stale inventory and insufficient demand history reduce forecast confidence separately.
- Acknowledgement is not a correctness label; evaluation requires independent verified outcomes.
- Backend authorization scopes workers to assigned facilities, officers to assigned hierarchy scope, admins globally, auditors read-only.

## Review Focus
- A batch awaiting QC or with bad expiry/status must not be issued, counted as usable, or transfer-sourced; test each state in inventory and risk services.
- Count mismatch must leave the ledger unchanged until an authorized resolution adds the exact delta; test unauthorized, duplicate, and concurrent resolution.
- Hierarchy changes must reject cycles and cross-district parents; test descendant authorization after a valid re-parent.
- Reorder suggestions must include incoming stock only when confirmed and due by expected delivery; test missing dates and safety/max caps.
- Transfer quantities must be reserved and never oversubscribe current transferable balance; failed/partial transitions must keep paired balances consistent.
- Stale inventory lowers confidence even if demand history is strong; test independent confidence inputs and acknowledgement/escalation idempotency.
- Metrics with zero denominators or no verified observations remain undefined with an explicit reason and sample size.

---

### Task 1: Additive schema and migration

**Files:** `backend/app/models.py`, `backend/migrations/versions/0002_supply_workflows.py`, model tests.

- [x] Add Product, facility parent/scope policy, stock policy fields (max/reorder/expiry-warning), batch QC and override records, physical counts/discrepancies, structured audit events, indent/reorder recommendation fields, transfer proposal/reservation/approval records, alert response events, risk labels/evaluation observations.
- [x] Create an additive Alembic migration that retains existing users, facilities, batches, transactions, replenishments, and audit rows; add defaults/backfills for current rows and migrate legacy batch product strings into a default Product catalog entry.
- [x] Add downgrade that removes only new schema additions in dependency order; do not erase legacy tables or rows.
- [x] Test upgrade from a database seeded with the current schema and verify legacy stock and user logins remain intact.

### Task 2: Product, quality, expiry and ledger validation

**Files:** inventory service/router/schemas, risk service, tests.

- [x] Replace free-text product identity with product foreign keys while keeping stable API compatibility for existing batch display fields.
- [x] Implement quality-state transitions, damage/quarantine ledger operations, expiry warning acknowledgements and justified overrides; override never bypasses expiry/QC eligibility.
- [x] Validate batch IDs, expiry chronology, positive/nonnegative transaction quantity, transaction reason, and only permit issues from eligible verified stock.
- [x] Verify usable balances against every unavailable status and immutable transaction history.

### Task 3: Physical verification and stale-stock confidence

**Files:** count/discrepancy service/router/schemas, risk calculations, tests.

- [x] Add count submission comparing counted batch quantities with ledger-derived balances and create discrepancy rows without immediately altering stock.
- [x] Add authorized discrepancy resolution; atomically create adjustment transactions, audit resolution, close discrepancy, and reject duplicate/stale resolutions.
- [x] Derive facility verification timestamp and freshness; lower forecast confidence and recommend a count when stale/missing independently of demand-data confidence.
- [x] Test worker count permission, officer resolution, ledger delta arithmetic, and stale confidence.

### Task 4: Facility hierarchy and reorder/indent workflow

**Files:** facility service/router, reorder service/router, replenishment UI/API, tests.

- [x] Add parent/child facility editing with facility kinds, cycle and district consistency checks, and descendant-scope officer authorization.
- [x] Add configurable min/max/reorder/safety/lead/expiry-warning policy with admin-only mutation and validated bounds.
- [x] Calculate draft recommendations using usable stock + confirmed incoming due by delivery − estimated demand; target max or safety target; expose all inputs, quantity, and missing-data flags.
- [x] Allow authorized staff to submit the draft as an indent/request; officer approval/rejection and event timestamps remain auditable; no PO integration.
- [x] Verify scope changes, math boundaries, missing demand/incoming dates, and request status gates.

### Task 5: Complete stock transfer workflow

**Files:** transfer service/router/schemas, facility map/list UI, tests.

- [x] Add proposal from suggestions, source physical verification, reservation, source/destination approval, storage/transport suitability, dispatch, receipt, partial delivery, and reconciliation.
- [x] Use a transaction identity for atomic paired source transfer-out and destination transfer-in ledger entries at dispatch/receipt; maintain outstanding quantity and discrepancies for partials.
- [x] Revalidate transferable stock at approval and dispatch under a row lock or optimistic version check; reject over-reservation and unsuitable/expired batches.
- [x] Show status, verifier, last verification, quantity, route distance, and approvals in UI; never auto-execute suggestions.
- [x] Verify role gates, no negative/over-reserved stock, paired movement reconciliation, partials, and audit trail.

### Task 6: Alert acknowledgement, escalation and evaluation labels

**Files:** alert/event models and API, evaluation service/API/UI, tests.

- [x] Persist acknowledgement and escalation events without changing alert correctness or causing active-alert duplicates.
- [x] Add authorized evaluation labeling for independently confirmed risk events and false alerts, with reviewer, evidence notes, period, and matching facility/risk/time-window rule.
- [x] Calculate TP/FP/TN/FN and precision/recall/F1/specificity/false-alert rate with explicit undefined reasons and sample sizes; calculate stage response times and availability only from complete observations.
- [x] Verify acknowledgement never counts as truth, zero-denominator handling, escalation timestamps, and permissions.

### Task 7: Integrate screens, seed data, docs and end-to-end verification

**Files:** React pages/types/API client, seed script, README, tests.

- [x] Extend Inventory with product/QC/expiry/count/discrepancy states; Facilities with hierarchy and stock locator; Replenishment with indent recommendations; map with verified transfer proposals; Risk/Evaluation with acknowledgement, escalation, and evidence-backed metrics.
- [x] Seed fictional examples of QC-pending, damaged, expiring, stale-count discrepancy, a reorder recommendation, a transfer proposal, acknowledgement/escalation, and independently labeled evaluation outcomes. Clearly label synthetic records.
- [x] Update README with migration command, formulas, role scope, transfer and count procedures, demo accounts, and limitations.
- [x] Run tests and production build. Verify full UI path: count discrepancy → authorized adjustment; recommendation → indent approval; transfer verification → paired movement/reconciliation; alert acknowledgement/escalation → evaluation view.
- [x] Record all checks actually executed; do not claim real operational accuracy or real-world stockout reduction.
