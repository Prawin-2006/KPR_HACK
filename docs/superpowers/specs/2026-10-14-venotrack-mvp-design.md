# VenoTrack Hackathon MVP Design

## Goal and boundaries
Build a polished, locally runnable anti-venom stockout prevention application for a hackathon demonstration. The first release is a coherent vertical slice for inventory, explainable stockout risk, nearby facility coordination, and closed-loop replenishment. It is a logistics decision-support system and makes no clinical recommendations.

The 15-page master prompt is broader than a practical first release. The MVP prioritizes a real backend, persistent database state, role-aware actions, transparent risk calculations, synthetic demo data, and reporting. Advanced user administration, full transfer fulfillment, ML forecasting, notification integrations, exhaustive evaluation labeling, and all secondary report types remain future extensions.

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
