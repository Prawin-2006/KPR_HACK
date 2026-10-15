# Facility Branches and Order Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show authorized facility branches and courier-style status tracking for replenishment requests and facility-to-facility ASV transfers on Facilities & map.

**Architecture:** Reuse role-scoped facility, replenishment, and transfer APIs. Add a nullable server-maintained replenishment receipt timestamp, derive hierarchy from authorized facility `parent_id` values, and render both order types with a shared milestone timeline. The map retains all authorized facilities, draws parent/child connectors when both endpoints are visible and geocoded, and never implies real GPS or invents transfer ETAs.

**Tech Stack:** React, TypeScript, React Leaflet, FastAPI, SQLAlchemy, Alembic, SQLite/MySQL.

**Spec:** `docs/superpowers/specs/2026-10-15-facility-branches-order-tracking-design.md`

## Global Constraints

- Keep every facility in the user's authorized facilities result visible; only show hierarchy links when both facilities are authorized.
- Keep the existing officer/worker approval and receipt actions as the only source of status changes; do not automatically approve, dispatch, or receive.
- Use the replenishment request's existing expected date as a planned arrival date; do not invent a transfer ETA.
- Label the existing animated transfer route as simulated; it is not GPS or a measured position.
- Do not expose map names, stock, or links for facilities outside the signed-in user's access scope.
- Do not add or run automated tests for this change; verify with syntax/build checks and manual UI review.

## Review Focus

- A parent or child outside the authorized result must not be named or linked on the map; manually inspect officer and worker scopes.
- Facilities with missing coordinates remain visible in cards/tree but have no drawn map connector; review a no-coordinate case.
- Requests with null `expected_date` show no planned arrival date; review a request without a date.
- Existing replenishment rows receive a null `received_at` after migration; check legacy records remain readable.
- Partial receipt must show the partial state and outstanding quantity, while final receipt shows the actual server-recorded arrival time; inspect both states.

## Files and Responsibilities

- `backend/app/models.py`: add the replenishment receipt timestamp.
- `backend/migrations/versions/0007_replenishment_received_at.py`: add/drop the nullable column without rewriting existing rows.
- `backend/app/main.py`: serialize timestamps and set receipt time in the authorized receive action.
- `frontend/src/api.ts`: include `parent_id` and replenishment/transfer status fields in the client-side types used by the page.
- `frontend/src/DeliveryTimeline.tsx`: render shared milestone labels, state, and available timestamps.
- `frontend/src/Facilities.tsx`: load authorized requests, derive hierarchy and connectors, and display both courier-style workflows.
- `frontend/src/style.css`: style branch hierarchy and delivery timeline responsively.

## Tasks

### Task 1: Persist and expose replenishment arrival time

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/migrations/versions/0007_replenishment_received_at.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- `Replenishment.received_at`: nullable timezone-aware datetime, server maintained.
- `req_json`: add ISO `approved_at`, `dispatched_at`, and `received_at` values, each nullable.

- [ ] Add `received_at` as a nullable `DateTime(timezone=True)` field and Alembic migration after `0006_asv_catalog_reconcile`; downgrade drops only the new column.
- [ ] In the existing authorized `receive` action, set `received_at=datetime.now(timezone.utc)` when recording each receipt. The timestamp is never accepted from the client; on full receipt it records the final receipt. Ledger transactions continue to timestamp every partial delivery.
- [ ] Add the three stored timestamps to `req_json`; keep legacy records with null values valid.
- [ ] Run `python -m py_compile backend/app/main.py` and inspect migration upgrade/downgrade for the expected single nullable column.
- [ ] Commit as `feat: record replenishment arrival time`.

### Task 2: Derive authorized facility branches

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/Facilities.tsx`
- Modify: `frontend/src/style.css`

**Interfaces:**
- Extend `Facility` with `parent_id: number | null`.
- Derive branch relationships only from the current `/facilities` result; no new endpoint is needed.

- [ ] Build parent-child lookups from authorized facilities and keep all authorized facilities visible in both map and list.
- [ ] Highlight the selected facility's parent, direct children, and branch connectors; allow selecting an authorized parent or child from the detail view.
- [ ] Draw map connectors only when both endpoints are in the authorized result and have coordinates; missing-coordinate facilities remain in list/tree.
- [ ] Add a compact hierarchy section to selected facility details and ensure a facility with no visible parent/children has a clear root/leaf state.
- [ ] Review a worker's assigned scope and an officer's broader scope manually; confirm peer facilities remain visible after selection.
- [ ] Commit as `feat: show authorized facility branches on map`.

### Task 3: Add the shared courier-style milestone component

**Files:**
- Create: `frontend/src/DeliveryTimeline.tsx`
- Modify: `frontend/src/style.css`

**Interfaces:**
- Export `DeliveryTimeline({ steps }: { steps: Array<{ label: string; state: 'complete' | 'current' | 'upcoming'; timestamp?: string | null }> })`.
- Timestamps are displayed only when provided; no ETA calculation is performed by this component.

- [ ] Render ordered milestone labels with complete/current/upcoming states and optional localized timestamps.
- [ ] Keep the component readable at narrow widths and provide semantic progress labeling for assistive technology.
- [ ] Verify a no-timestamp milestone renders without a blank date or fabricated time.
- [ ] Commit as `feat: add courier-style delivery timeline`.

### Task 4: Track replenishment requests on Facilities & map

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/Facilities.tsx`
- Use: `frontend/src/DeliveryTimeline.tsx`

**Interfaces:**
- Load requests from the existing `GET /replenishments` endpoint and associate them with visible destination facility IDs.
- Use request fields `request_code`, `facility_id`, `quantity`, `received`, `outstanding`, `status`, `expected_date`, `created_at`, `approved_at`, `dispatched_at`, and `received_at`.

- [ ] Render submitted, approved, dispatched, partial/received, and verified/rejected states from persisted request status; show only timestamps returned by the API.
- [ ] Display destination, requested/received/outstanding vial quantities, and expected date as “planned arrival” separately from actual `received_at`.
- [ ] Do not draw a replenishment route because the request model has no source facility; show a destination marker/status card instead.
- [ ] Filter rendered request details to facilities in the current authorized facilities result; provide an empty state when no requests are present.
- [ ] Review pending, dispatched, partial, received, verified, and null expected-date cases manually.
- [ ] Commit as `feat: track replenishment requests on facilities map`.

### Task 5: Unify facility transfer tracking and finish page integration

**Files:**
- Modify: `frontend/src/Facilities.tsx`
- Modify: `frontend/src/style.css`

**Interfaces:**
- Use existing transfer fields `status`, `verified_at`, `dispatched_at`, `received_at`, `received_quantity`, and `outstanding`.
- Preserve the endpoint-pair authorization guard before showing a transfer route or facility details.

- [ ] Render transfer milestones for proposed, source verified, both-side approval, dispatched/in transit, partial receipt, received, and reconciled states; display only stored verification, dispatch, and receipt timestamps.
- [ ] Reuse `DeliveryTimeline` for both replenishment and transfer records.
- [ ] Keep nearby-support suggestion lines visually distinct from transfer routes and hierarchy connectors; retain the simulated movement label.
- [ ] Add empty states and responsive layout for no active orders, no recent arrivals, and hidden/missing-coordinate endpoints.
- [ ] Run `npm run build`, `python -m py_compile backend/app/main.py`, and manually review worker/officer pages and the request/transfer states above. Do not run automated tests.
- [ ] Commit as `feat: show courier tracking for ASV deliveries`.

## Self-Review

- Spec coverage: hierarchy connectors/tree and peer visibility are covered by Task 2; replenishment arrival timestamp and expected-date distinction by Tasks 1 and 4; transfer milestones, actual arrival, simulated route boundary, and access scope by Task 5; responsive/no-data cases by Tasks 3–5.
- Types: `parent_id` extends the existing `Facility` client type; `req_json` adds nullable ISO timestamps consumed by the replenishment tracking UI; `DeliveryTimeline` has one shared state/timestamp contract for both workflows.
- Review risks: all five conditions listed above have a manual review step in the owning task.
- Tests: no automated tests are added or run under the active developer instruction; syntax checks, frontend production build, and manual role/state review are the planned verification.
