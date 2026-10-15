# Facility Map and ASV Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Facilities & map page show selected-facility ASV availability, reorder need, next batch expiry, weekly/monthly usage, and clearly simulated movement for active dispatched transfers.

**Architecture:** Extend the existing authorized facility-detail response with ledger-derived usage buckets, add dispatch timestamp to transfer JSON, and reuse the existing reorder recommendations endpoint. Update the Facilities page to select a facility from its map marker or card, fetch its detail, render the usage/expiry/reorder panel beneath the map, and animate only dispatched or partially received transfers along facility-coordinate routes with a clear simulated-tracking label.

**Tech Stack:** FastAPI, SQLAlchemy, React 18, TypeScript, React Leaflet, Recharts, Leaflet.

**Spec:** `docs/superpowers/specs/2026-10-15-facility-map-usage-design.md`

## Global Constraints

- Preserve server-side role-scoped facility access and existing transfer approval rules.
- Usable quantities exclude expired, quarantined, damaged, and quality-pending batches.
- Weekly and monthly usage counts only ledger transactions with `kind == 'issue'`; receipts and adjustments are not consumption.
- Use seven daily buckets ending today and six calendar-month buckets including the current month; missing periods are zero and missing history is identified.
- Show only recorded future batch expiry dates; do not infer or invent expiry dates.
- Show the existing reorder recommendation and its explanation/flags; do not imply that it creates or submits a purchase order.
- Simulated map movement is a repeating forward-and-back animation between facility coordinates, labeled as simulated; it is not GPS, progress, or ETA.
- Only `dispatched` and `partially_received` transfers with coordinate-bearing endpoints are animated; proposal, approval, completion, and reconciliation states are not shown as moving.
- Keep all demo records clearly labeled synthetic; add no GPS provider, dependencies, or fabricated location records.

## Review Focus

- A worker cannot retrieve another facility's detail or usage series; rely on `facility_detail`'s existing `assert_access` guard.
- Facilities with no issue history still receive complete zero-valued chart buckets and a clear no-history note.
- Upcoming expiry selection ignores batches with no remaining physical quantity and reports when there is no upcoming dated batch.
- A dispatched transfer with a missing endpoint or coordinate never creates an invalid map route or marker.
- Partial receipt displays the transfer's remaining quantity (`outstanding`), and the marker disappears after status refresh when the transfer is no longer in transit.

---

### Task 1: Add facility usage summaries and transfer dispatch context

**Files:**
- Modify: `backend/app/main.py` (`facility_detail`, `transfer_json`)

**Interfaces:**
- Extend `GET /api/v1/facilities/{fid}` with `usage.weekly: [{period: ISO-date, quantity: integer}]` (seven days ending today) and `usage.monthly: [{period: YYYY-MM, label: abbreviated month, quantity: integer}]` (six calendar months including the current month).
- Both series aggregate only supported ASV batch transactions at this facility where `kind == 'issue'`; buckets with no issues return quantity `0`.
- Extend `GET /api/v1/transfers` objects with `dispatched_at: ISO-datetime | null`.

- [x] Add an internal helper in `backend/app/main.py` that builds complete weekly and monthly buckets and aggregates ASV issue transactions by facility and transaction date.
- [x] Add the helper result to `facility_detail` after the existing `assert_access` check; query supported batches only and leave the existing `transactions` response compatible.
- [x] Add nullable `dispatched_at` serialization to `transfer_json` without changing transfer states or authorization behavior.
- [x] Review the facility-detail query for empty batches/history and inspect transfer JSON for null and populated dispatch timestamps.

### Task 2: Add selected-facility details, usage charts, and simulated transfer map

**Files:**
- Modify: `frontend/src/app.tsx` (`Facilities` and imports)
- Modify: `frontend/src/style.css` (facility-detail, transit, marker animation, and usage-chart styling)

**Interfaces:**
- Facilities page uses `GET /facilities`, `GET /facilities/{id}`, `GET /reorder/recommendations`, and `GET /transfers`.
- Detail card shows facility name/kind/district; usable ASV vials; `recommended_quantity`, `explanation`, and `data_flags`; earliest future batch expiry with batch number, quantity, and days remaining; and weekly/monthly issue charts from Task 1.
- Selecting a map marker or facility card selects the same facility. The detail card appears after the map and remains available in list mode.
- Render one active route per dispatched/partially received transfer only when source and destination facilities both have coordinates. Use an on-screen repeating forward-and-back interpolation for the marker; label it “Simulated movement · not GPS”. Show transfer code, endpoints, status, and outstanding vials without showing a progress percentage or ETA.
- Poll transfer statuses every 10 seconds and stop marker animation when the transfer leaves an in-transit state. Facilities with missing coordinates or no active transfer show the existing facility markers and a concise map note/empty state.

- [x] Query transfer state with a 10-second refresh and query scoped reorder recommendations; initialize selected facility from an explicit map/list interaction, falling back to the first visible facility.
- [x] Fetch selected facility detail by ID and render the selected-facility summary under the map with availability, recommendation explanation/data flags, and actual next-expiry batch details.
- [x] Render seven daily and six monthly issue charts from the API buckets and show a specific empty-history message when all ledger issue quantities are zero or unavailable.
- [x] Wire map markers and facility cards to one selection state; keep map/list toggle and facility search behavior intact.
- [x] Filter active transfers by status and valid endpoint coordinates, draw straight-line route polylines, and animate a distinct marker with a repeating forward-and-back on-screen position. Display the explicit simulated/non-GPS label and transfer details.
- [x] Add responsive styles for the detail panel, paired charts, in-transit card, and pulsing/blinking marker without obscuring facility markers or map controls.
- [x] Run `npm run build` from `frontend/` and review the updated Facilities page in the running demo, including selected-facility, no-history, expiry, and no-active-transfer states.

## Self-Review

- Spec coverage: Task 1 supplies real ledger buckets and dispatch context; Task 2 supplies selection, existing reorder data, actual expiry records, charts, simulated route, refresh, empty states, and responsive presentation.
- Types and fields align with current API names: `recommended_quantity`, `explanation`, `data_flags`, `outstanding`, `status`, `source_facility_id`, and `destination_facility_id`.
- No real location, ETA, procurement, or transfer authorization behavior is introduced.
- No automated tests are added or run; validation uses API inspection and the production frontend build.
- The current demo dataset has no dispatched transfer; the empty state was reviewed, and the animated marker path was inspected in code but could not be shown with a live demo record.
