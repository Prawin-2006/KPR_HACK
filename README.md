# VenoTrack

A synthetic-data hackathon MVP for anti-snake venom (ASV) inventory visibility, explainable stockout warnings, location-aware facility coordination, and replenishment workflow tracking. VenoTrack is logistics decision support only. It does not diagnose patients or recommend treatment.

**Product scope is limited to polyvalent anti-snake venom (ASV) vials.** It does not support other medicines, formulations, or units.

## What works

- FastAPI API with JWT login, hashed demo passwords, role-aware facility access, audit records, OpenAPI docs, and SQLite persistence (MySQL-compatible `DATABASE_URL`).
- Inventory ledger with validated receipts and issues; usable stock excludes expired, quarantined, damaged, and unverified quantities.
- A fixed ASV product catalogue, batch identifiers, batch QC states, expiry-warning acknowledgements/overrides, and auditable transaction history. Historical records without an identifiable product remain preserved but are excluded from ASV totals and forecasts.
- Physical counts create discrepancies without changing stock; authorized resolution adds a ledger delta. Unresolved or stale counts lower forecast confidence.
- Explainable risk forecast: coverage, depletion estimate, lead time, projected delivery balance, safety stock and data-quality/confidence labels. Alerts are deduplicated.
- Facility hierarchy and role-scoped access, configurable stock policies, explainable reorder drafts, and officer-reviewed indents. No external purchase order is submitted.
- Facility map and fallback cards with Haversine straight-line proximity estimates. Stock-transfer suggestions require recent source verification, suitable storage/transport, source/destination approval, dispatch and receipt reconciliation.
- Alert acknowledgement and escalation events are distinct from independently reviewed evaluation labels. Zero-denominator metrics include reasons; stock availability uses dated observations only.
- Replenishment submission, officer approval/rejection, dispatch, partial receipts and verification. Receipts create inventory ledger entries.
- Dashboard, risks, inventory, facilities/map, replenishment, evaluation, audit view, and stock CSV report.
- All seeded facilities and movements are fictional and labeled as synthetic demo data. Seed coordinates are illustrative; straight-line distances are not road routes or live tracking.

## Architecture

`frontend/` is a React 18, TypeScript and Vite SPA using TanStack Query, Recharts, Leaflet, React Router and Lucide. `backend/` is a FastAPI service using Pydantic and SQLAlchemy 2. SQLite is the default local database. Set `DATABASE_URL` to a MySQL SQLAlchemy URL such as `mysql+pymysql://user:password@host/database` for a MySQL deployment. API endpoints are versioned at `/api/v1`.

Alembic manages schema revisions in `backend/migrations/versions/`. The API applies pending revisions on startup. The ASV scope migration preserves old products, batches, and transactions; disables non-ASV products; quarantines their batches; and reports preserved records and unlinked consumption, request, alert, evaluation, and stock-observation data. Historical records without a product link are never assumed to represent ASV. Administrators can review the report at `/api/v1/admin/asv-scope-migration-report` after signing in. Back up the database before upgrading, especially when it contains operational data. For a manual migration, run `alembic upgrade head` from `backend/` before seeding.

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm

## Local setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:JWT_SECRET = "use-a-long-random-value-outside-demo"
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

Open API documentation at [http://localhost:8000/docs](http://localhost:8000/docs). The default SQLite file is `backend/venotrack.db`.

### Frontend

In another terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). `VITE_API_URL` defaults to `http://localhost:8000/api/v1`.

### Docker Compose

From the repository root:

```powershell
$env:JWT_SECRET = "use-a-long-random-value-outside-demo"
docker compose up --build
```

The web app is on port 5173 and API docs on port 8000. The database is held in the `venotrack-data` volume.

### Reset synthetic records

From `backend/` run:

```powershell
python -c "from app.seed import reset; reset()"
```

This drops and recreates the demo schema. Do not run it against real operational data.

## Demo accounts

All accounts use the fictional district and password `VenoTrack2026!`:

| Role | Login |
| --- | --- |
| Facility health worker | `worker@venotrack.demo` |
| District supply officer | `officer@venotrack.demo` |
| System administrator | `admin@venotrack.demo` |
| Auditor (read-only) | `auditor@venotrack.demo` |

The demo password is for local demonstration only. Change it and `JWT_SECRET` before any shared deployment.

## Risk calculations

- **Usable stock:** transaction-derived batch balance for batches that are in date, storage status `usable`, and marked verified.
- **Quality eligibility:** a batch is usable only when its quality status is `verified`, it is in date, its storage status is usable, and it is physically verified. Expiry-warning acknowledgement or override never changes this rule.
- **Coverage:** usable quantity ÷ average daily recorded issues when a nonzero demand basis exists. Missing consumption is labeled insufficient; no depletion date is claimed.
- **Projected stock at delivery:** usable stock + confirmed incoming due by expected delivery − average daily use × configured lead days. Overdue or undated requests are excluded from confirmed incoming.
- **Reorder draft:** configured target plus estimated lead-time demand minus usable stock and confirmed incoming, rounded up and capped by configured maximum stock. The API returns each input and any missing-data flags.
- **Physical count:** counted quantity is compared with the ledger snapshot. Resolution is officer/admin-only, rejects a stale snapshot, and records the exact delta as a new adjustment transaction.
- **Transfer:** a proposal reserves eligible source stock after safety stock. Physical verification, independent source and destination officer approvals, storage/transport checks, dispatch and receipt are required. Source and destination transactions share a transfer ID; partial deliveries remain open for reconciliation.
- **Severity:** zero stock or coverage shorter than lead time is critical; below minimum or below safety stock at delivery is high; insufficient history is medium; otherwise low.
- Seeded transactions are synthetic examples, not a validated demand sample. The risk display is a rule-based planning estimate, not a trained ML model or guarantee.
- Transfer distance is Haversine straight-line distance, never a claim about travel time or road route.

## Evaluation metrics

The evaluation view uses standard precision, recall, F1, specificity, and false-alert-rate definitions from reviewer-entered evidence labels. Acknowledgement is not treated as evidence of correctness. The fictional seed includes two sample labels for demonstration only. Availability and stockout-day counts use dated facility observations; response-time averages use persisted alert events. These small synthetic samples do not establish real-world performance.

## Tests and build

From the repository root:

```powershell
cd backend
python -m pytest tests -q
cd ..\frontend
npm run build
```

Tests cover risk math and data quality, quality/expiry exclusion, physical count reconciliation, hierarchy validation, reorder inputs, transfer approvals and partial reconciliation, evidence-based evaluation, authorization, migration backfill/downgrade preservation, and alert deduplication.

## Limitations and production considerations

This is an online-only hackathon MVP, not a production healthcare system. Synthetic sample outcomes are not an operational performance claim. There is no e-Aushadhi or DVDMS integration, no access to government production data, no patient information, and no road-routing provider. Before production: configure a managed database and backups, secret rotation, TLS, rate limits, monitoring, privacy and security review, stronger session controls, complete district assignments, and operational validation with authorized health-supply stakeholders.

The workflow reference is limited to publicly documented e-Aushadhi / DVDMS supply-chain concepts: [Maharashtra MMGPA e-Aushadhi application](https://mmgpa.maharashtra.gov.in/en/service/e-aushadhi-application/) and [C-DAC DVDMS product information](https://www.cdac.gov.in/index.aspx?id=product_details&productId=DrugandVaccineDistributionManagementSystem%28DVDMS%29). VenoTrack is independently implemented and does not claim official integration.
