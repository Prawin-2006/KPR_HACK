# VenoTrack Hackathon MVP Design

## Goal and boundaries
The initial VenoTrack hackathon MVP already delivers a locally runnable slice for inventory, explainable stockout risk, nearby facility coordination, and replenishment. This approved extension defines the next release that fills out quality control, physical reconciliation, hierarchical inventory, reorder/indent, authorized transfer, and evidence-based evaluation workflows. VenoTrack remains logistics decision support and makes no clinical recommendations.

The first release prioritizes a real backend, persistent database state, role-aware actions, transparent risk calculations, synthetic demo data, and reporting. ML forecasting, external notification integrations, and secondary report types remain future extensions.

## Architecture
- React + TypeScript + Vite frontend with a responsive operations dashboard and focused pages for overview, risks, inventory, facilities/map, replenishment, and evaluation.
- FastAPI backend under `/api/v1`, SQLAlchemy 2 models, Pydantic schemas, secure password hashes, signed JWT sessions, and role/facility authorization.
- SQLite is the zero-configuration local default. `DATABASE_URL` permits MySQL deployment. Docker Compose documents and runs the app stack.
- Backend owns inventory balances and risk calculations. Every stock change is an immutable transaction; receipts/issues and deliveries use database transactions. Alerts deduplicate by active facility/risk key.
- Synthetic seed data is labeled throughout. The map uses OpenStreetMap-compatible Leaflet tiles and keeps a list fallback.

## Main workflows
1. Demo user signs in and sees assigned/authorized facilities and actual API-derived summary metrics.
2. Staff records an issue or receipt; backend validates and records a transaction, then updates risk.
3. Risk page explains usable quantity, consumption basis, coverage, estimated depletion, expected delivery, safety stock, confidence/data quality, and next action.
4. Map/list displays facility coordinates, stock verification age, risk, and conservative nearby transfer candidates. Proposals require review and stock verification; no automatic movement occurs.
5. Staff submits replenishment; officer reviews/approves, records dispatch, and records one or more deliveries. Each delivery updates stock through a receipt ledger transaction and leaves outstanding quantity until fulfilled. Verification is required to close.
6. Reports export backend-derived CSV. Evaluation displays only metrics supported by persisted events/labels and identifies synthetic sample data and undefined denominators.

## MVP screens
- Login with seeded demo roles.
- Overview dashboard: facility and stock status, active critical alerts, expiry warning, requests, movements, and risk distribution from backend data.
- Risks: severity filters and explainable risk details with acknowledge/run-check actions.
- Inventory: facility/batch list and validated receipt/issue/physical-count actions with transaction history.
- Facilities/map: Leaflet view with risk markers and stale/unverified status; list works when coordinates/tiles are unavailable.
- Replenishment: request list, submission, approval/rejection, dispatch, partial delivery, and receipt verification according to role.
- Evaluation/reports: operational counts, response durations where events exist, explicit sample size and methodology; CSV exports.

## Data and risk model
Core entities: users, facilities, assignments, suppliers, products, batches, inventory transactions, physical counts, risk rules/evaluations, alerts/acknowledgements, incidents, replenishment requests/events/deliveries, transfer proposals, notifications, evaluation labels/runs, audit events, and configuration. Use foreign keys, indexes, unique facility/batch identifiers, timezone-aware timestamps, and transaction boundaries.

Usable stock excludes expired, quarantined, damaged, and unverified quantities. Stock is derived from immutable transactions and batch state, never silently overwritten. Coverage is usable stock / average daily consumption when consumption is sufficient and nonzero. Projected stock at delivery = usable stock + confirmed incoming before delivery − expected consumption before delivery. Low history or stockout-suppressed history is labeled unreliable; deterministic minimum-stock/zero-stock rules remain active. Each alert stores inputs, rule version, explanation, action, confidence/data quality, and timestamps. Re-evaluation updates a matching active alert rather than duplicating it.

## Security and roles
Roles: administrator, facility worker, supply officer, auditor. Enforce access in API dependencies and constrain records to facility/district assignments. Passwords are hashed; JWT secret is environment supplied; CORS is explicit; operational writes create audit entries. Auditor is read-only. Replenishment transitions are validated server-side.

## Visual direction
Quiet, high-trust operations console: warm off-white surfaces, deep navy text/nav, teal primary actions, amber/red severity, crisp typography, dense but scannable tables, restrained borders/shadows, responsive sidebar/header. Synthetic data is visibly labeled. Accessibility includes keyboard focus, semantic controls, readable contrast, and reduced-motion behavior.

## Validation and limits
Use backend tests for risk math, expired/quarantined exclusion, authorization, duplicate alert handling, receipt/issue and partial delivery ledger behavior, and CSV validation if included. Run the available application checks and verify the principal interaction path in the browser. No real clinical data, patient data, or external delivery claims. Road distance/travel time is not inferred from straight-line map distance. The MVP is not a validated clinical or supply-chain forecasting model.


## E-Aushadhi / DVDMS-inspired workflow extension (approved 2026-10-14)

### Reference and scope
Use publicly documented e-Aushadhi / DVDMS drug-supply workflow concepts as a functional reference for VenoTrack. Public documentation describes drug classification/codification, expiry alerts, indent/reorder planning, hierarchical store networks, transfers, damaged stock, physical stock verification, and quality control. This is a workflow reference only: do not copy proprietary code, imply official integration, assume undocumented internal database structures, or claim government systems lack capabilities. VenoTrack's differentiator remains an ASV-focused, explainable stockout warning connected to location-aware coordination, alert escalation, verified replenishment closure, and measurable operations. Online-only; synthetic data; no patient records.

Reference sources: [Maharashtra Medical Goods Procurement Authority: e-Aushadhi application](https://mmgpa.maharashtra.gov.in/en/service/e-aushadhi-application/) and [C-DAC: DVDMS product information](https://www.cdac.gov.in/index.aspx?id=product_details&productId=DrugandVaccineDistributionManagementSystem%28DVDMS%29).

### Inventory and quality controls
- Add a product catalogue with product identifier, name, category, unit, and active status. Batches reference a product and facility; identifiers remain unique within a facility/product scope.
- Track batch physical balance from immutable transactions and derive usable balance. Batch quality states include awaiting quality verification, verified, quarantined, damaged, and rejected. Expiry is an independent eligibility check. Only in-date, verified-quality, undamaged, non-quarantined stock is usable.
- Add configurable expiry-warning days and persistent warning acknowledgement/override records with actor, timestamp, reason, and batch. An override never changes an expired batch into usable stock.
- Support receipt, issue, damage, quarantine/release, count, and adjustment ledger entries. Count corrections create audited delta transactions; no direct balance overwrite.

### Physical count and stale-data handling
- Record a physical count with counted quantities by batch, counter, time, and notes. Compare with ledger-calculated balances and create discrepancy records.
- Require authorized officer/admin resolution with disposition and explanation. Resolution adds a ledger adjustment and closes the discrepancy atomically.
- Facility stock freshness is derived from most recent physical count. Stale or missing verification lowers forecast confidence and adds a verification recommendation, independent of demand-history confidence.

### Reorder and indent
- Facility policy contains minimum, maximum, reorder point, safety stock, and lead days; values are validated and configurable by authorized admin.
- Calculate recommendation quantity from target/max stock minus usable and confirmed incoming stock at/before expected delivery, with a nonnegative cap and an explanation of every input. Unknown demand/incoming dates are explicitly flagged.
- Recommendations are drafts only. Authorized users review and submit an indent/request; approval/rejection, reason, actor, and timestamps remain auditable. No external PO is created.

### Hierarchy and authorization
- Add parent-child facility relationships among district warehouse, hospital, PHC, and rural sub-centre, with cycle prevention and district consistency validation.
- Officers may query assigned scope and its descendants. Workers remain restricted to assigned facilities. Admin retains global access; auditor is read-only.

### Transfer workflow
- Preserve suggestions as non-operative. Add proposal, source physical verification, quantity reservation, source/destination officer authorization, storage/transport suitability checks, dispatch, receipt, and reconciliation states.
- On dispatch/receipt, create paired source and destination stock ledger entries with transfer identity and audit records in atomic database work. Reject quantity above verified transferable stock after safety stock. Partial transfer and discrepancies remain explicit states. Never dispatch based on model output alone.

### Alert response and evaluation
- Store acknowledgement separately from alert lifecycle and record actor/timestamp/note. Support escalation records with target role, reason, timestamp, and status. Re-evaluation must remain idempotent for the same active risk condition.
- Add independently verified risk labels and evaluation runs. Match alerts to verified risk events using documented facility + time-window/risk-type rules; acknowledgement is never correctness evidence. Calculate confusion counts, precision, recall, F1, specificity, false-alert rate, and response-time statistics only when labels/observations exist; return explicit undefined reasons and sample sizes otherwise. Service availability and stockout-day metrics require daily observation records.

### Implementation path and acceptance
Deliver in vertical increments: (1) schema/migration and inventory quality/count services; (2) product/hierarchy and scoped authorization; (3) reorder recommendation and indent; (4) fully authorized transfers; (5) alert acknowledgement/escalation and evaluation labels; (6) connected UI, synthetic examples, documentation, and end-to-end tests. Preserve existing SQLite demo data through an Alembic migration; never drop or silently rewrite ledger history.

Acceptance requires tests showing: unavailable batches excluded; pending quality cannot be used; expired warning acknowledgement/override is audited but does not change eligibility; count discrepancies resolve only through authorized delta transactions; stale inventory lowers confidence; reorder math is transparent; hierarchy is acyclic and scope-limited; transfers cannot oversubscribe verified stock and create paired movements only on authorized transition; alert acknowledgement/escalation timestamps persist and alert dedupe works; evaluation metrics honor explicit labels and zero denominators; auditor writes are rejected. End-to-end UI demo covers stock count/discrepancy resolution, indent approval, transfer review/receipt, and verified closure using synthetic data.
