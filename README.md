# VenoTrack

A synthetic-data hackathon MVP for anti-snake venom (ASV) inventory visibility, explainable stockout warnings, location-aware facility coordination, and replenishment workflow tracking. VenoTrack is logistics decision support only. It does not diagnose patients or recommend treatment.

## What works

- FastAPI API with JWT login, hashed demo passwords, role-aware facility access, audit records, OpenAPI docs, and SQLite persistence (MySQL-compatible `DATABASE_URL`).
- Inventory ledger with validated receipts and issues; usable stock excludes expired, quarantined, damaged, and unverified quantities.
- Explainable risk forecast: coverage, depletion estimate, lead time, projected delivery balance, safety stock and data-quality/confidence labels. Alerts are deduplicated.
- Facility map and fallback cards with Haversine straight-line proximity estimates. Transfers are suggestions and require verification and approval.
- Replenishment submission, officer approval/rejection, dispatch, partial receipts and verification. Receipts create inventory ledger entries.
- Dashboard, risks, inventory, facilities/map, replenishment, evaluation, audit view, and stock CSV report.
- All seeded facilities and movements are fictional and labeled as synthetic demo data.

## Architecture

`frontend/` is a React 18, TypeScript and Vite SPA using TanStack Query, Recharts, Leaflet, React Router and Lucide. `backend/` is a FastAPI service using Pydantic and SQLAlchemy 2. SQLite is the default local database. Set `DATABASE_URL` to a MySQL SQLAlchemy URL such as `mysql+pymysql://user:password@host/database` for a MySQL deployment. API endpoints are versioned at `/api/v1`.

Alembic provides the initial schema revision in `backend/migrations/versions/0001_initial.py`. For local setup, the API also creates missing tables on startup for convenience.

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
- **Coverage:** usable quantity ÷ average daily recorded issues when a nonzero demand basis exists. Missing consumption is labeled insufficient; no depletion date is claimed.
- **Projected stock at delivery:** usable stock + confirmed incoming quantity − average daily use × configured lead days.
- **Severity:** zero stock or coverage shorter than lead time is critical; below minimum or below safety stock at delivery is high; insufficient history is medium; otherwise low.
- Seeded transactions are synthetic examples, not a validated demand sample. The risk display is a planning estimate, not a guarantee.
- Transfer distance is Haversine straight-line distance, never a claim about travel time or road route.

## Evaluation metrics

The evaluation view uses standard precision, recall, F1, specificity, and false-alert-rate definitions. This seed has no independently verified true/false event labels, so those values are explicitly not calculable. Alert acknowledgement is not treated as evidence of correctness. Fulfilment is received requested quantity divided by total requested quantity where requests exist. Facility-days, stockout days, expiry losses and response-time percentiles require longitudinal observations not included in this MVP.

## Tests and build

From the repository root:

```powershell
cd backend
python -m pytest tests -q
cd ..\frontend
npm run build
```

Critical tests cover risk math, insufficient history, unusable batch exclusion, authorization, issue validation, and active alert deduplication.

## Limitations and production considerations

This is a hackathon MVP, not a production healthcare system. Advanced incident management, full transfer fulfillment, CSV import, user/facility administration, scheduled evaluation, notification delivery, comprehensive role assignment, statistically validated forecasting, and production-ready Alembic revisions remain future work. There is no real message integration, no patient information, no road-routing provider, and no real-world effectiveness claim. Before production: configure a managed MySQL database, robust migrations/backups, secret rotation, TLS, rate limits, monitoring, privacy and security review, stronger session controls, complete district assignment policy, and operational validation with authorized health-supply stakeholders.
