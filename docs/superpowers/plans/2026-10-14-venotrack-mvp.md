# VenoTrack Hackathon MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable, polished VenoTrack MVP for anti-venom inventory, explainable stockout risk, facility coordination, and replenishment.

**Architecture:** React/TypeScript/Vite consumes FastAPI `/api/v1`; SQLAlchemy persists immutable inventory ledger and workflow events in SQLite by default or MySQL by URL configuration. Seeded fictional data supports the demo journey.

**Tech Stack:** React, TypeScript, Vite, Tailwind, React Router, TanStack Query, Recharts, Leaflet, Lucide; Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, JWT, Pytest; Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-14-venotrack-mvp-design.md`

## Global Constraints
- No patient or real facility data; synthetic examples must be labeled.
- Expired, quarantined, damaged, and unverified quantity does not count as usable stock.
- Stock changes are ledger transactions and use database transactions.
- Risk outputs expose assumptions and flag insufficient data; no clinical recommendations.
- Backend enforces role and facility/district access.
- Transfers are suggestions only until verified and authorized.
- No hardcoded credentials, secrets, or paid external services.

## Review Focus
- Zero/missing/stockout-suppressed consumption must not yield misleading depletion dates; risk engine reports insufficient history.
- Expired or quarantined batch quantities must never be included in usable stock; stock aggregation tests pin exclusions.
- Repeated risk runs must update active alerts rather than duplicate them; idempotency test pins behavior.
- Partial/duplicate/oversized delivery must not corrupt stock or outstanding quantities; workflow tests pin transitions.
- Unauthorized facility reads/writes and auditor writes must be rejected server-side; API tests pin role scoping.

---

### Task 1: App foundation and visual shell

**Files:** frontend package/config/src; root `.gitignore`, `.env.example`, compose configuration.

- [ ] Scaffold frontend and establish navy/teal responsive shell, navigation, shared loading/error/empty states, and synthetic-data badge.
- [ ] Add route structure for Overview, Risks, Inventory, Facilities, Replenishment, and Evaluation.
- [ ] Confirm production build succeeds and all route links resolve.

### Task 2: Backend persistence, auth, and seed data

**Files:** `backend/app/main.py`, `backend/app/db.py`, models/schemas/security/seed modules, Alembic config/migrations, backend requirements.

- [ ] Define SQLAlchemy entities and database configuration with SQLite default and MySQL URL support.
- [ ] Add initial Alembic migration, JWT login, secure password hashing, role/facility dependencies, and audit event helper.
- [ ] Seed fictional districts, facilities, user roles, ASV batches, ledger movements, risk rules, and replenishment states reproducibly.
- [ ] Verify login, seeded data, and OpenAPI docs through API calls.

### Task 3: Inventory and risk services

**Files:** inventory and risk service/router modules; corresponding pytest modules.

- [ ] Implement read endpoints for facilities, batches, ledger, dashboard summaries, risk list/details, and filters/pagination.
- [ ] Implement transaction-safe receipt, issue, reconciliation, and audit logging without balance overwrite.
- [ ] Implement risk calculations and alert deduplication with stored input snapshots and explanations.
- [ ] Verify coverage, projected stock, confidence/data-quality labels, zero-consumption, expiry exclusion, stale data, and permissions.

### Task 4: Replenishment and transfer coordination

**Files:** replenishment/transfer schemas, services, routers, tests.

- [ ] Implement request submit, review/approve/reject with reason, dispatch, partial delivery, and final receipt verification transitions.
- [ ] Ensure each delivery receipt creates a ledger transaction and updates outstanding quantity exactly once.
- [ ] Add nearby transfer suggestions ranked by Haversine distance and based on verified transferable quantities only; proposal remains pending authorization.
- [ ] Verify workflow role gates, invalid transitions, partial deliveries, audit timeline, and no auto-transfer.

### Task 5: Frontend API integration and core screens

**Files:** frontend API client/types, auth context, shared components, page modules.

- [ ] Connect login/session and role-aware navigation to the backend.
- [ ] Populate dashboard, risk detail, inventory forms/ledger, facilities map/list, and replenishment workflow from API queries and mutations.
- [ ] Add CSV reporting and evaluation calculations using backend records, with sample size, synthetic label, and undefined-metric treatment.
- [ ] Verify end-to-end worker-to-officer journey in browser including a partial delivery.

### Task 6: CSV import and operational documentation

**Files:** import router/service/tests, README, seed/reset instructions, docker compose.

- [ ] Implement CSV preview/validation with accepted/rejected row report and explicit confirmation before creating unverified legacy records.
- [ ] Document architecture, setup, env, migrations, seed/demo accounts, commands, API docs, formulas, limitations, and production considerations.
- [ ] Run relevant automated tests and frontend build; fix failures and verify documented commands from a clean local database.

### Task 7: Visual and workflow verification

**Files:** none expected unless fixes are needed.

- [ ] Run backend and frontend and inspect desktop/mobile UI in browser.
- [ ] Verify loading, empty, error, success, role-based navigation, and primary demo workflow.
- [ ] Summarize verified checks and remaining limitations without claiming unrun tests or real-world effect.
