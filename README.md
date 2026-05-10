# Machine Shop Planning Software

This repository contains the V1 planning cockpit for machine shop scheduling. The first usable build covers workbook upload, validation, planning calculations, dashboards, and first-priority Excel exports.

For the full first usable build workflow, including migrations, sample data, local reset, and upload/export paths, see [First Build Developer Runbook](docs/implementation/FIRST_BUILD_RUNBOOK.md). For pilot validation, see [Pilot Validation](docs/implementation/PILOT_VALIDATION.md). For release signoff, see [Release Readiness Checklist](docs/implementation/RELEASE_READINESS.md). For backup, restore, and support troubleshooting, see [Operational Readiness Runbook](docs/implementation/OPERATIONAL_READINESS_RUNBOOK.md).

## Prerequisites

- Python 3.11 or newer
- Node.js LTS and npm
- Git and GitHub CLI

On this Windows workstation, Git and GitHub CLI were installed under:

```powershell
C:\Program Files\Git\cmd
C:\Program Files\GitHub CLI
```

Node.js LTS was installed with `winget`.

## Backend Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

Run backend lint:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
```

Run database migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Health endpoint:

```text
http://127.0.0.1:8000/api/v1/health
```

## Frontend Setup

From the repository root:

```powershell
cd frontend
npm install
npm run build
npm test
npm run dev
```

Frontend environment variables:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Runtime Data

Runtime files live under `data/` and are not committed:

- `data/app.sqlite3`
- `data/uploads/`
- `data/exports/`
- `data/backups/`

The application creates required runtime directories on startup. See the first build runbook for safe local reset steps.
