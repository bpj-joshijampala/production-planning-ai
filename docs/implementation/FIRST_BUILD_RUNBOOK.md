# First Build Developer Runbook

This runbook brings a new developer from a fresh checkout to a working first usable build. It covers the backend, frontend, migrations, sample data, local reset, and the runtime file locations used by the app.

## Scope

Use this for local developer work on the first usable build:

- FastAPI backend on `http://127.0.0.1:8000`
- React/Vite frontend on `http://127.0.0.1:5173`
- SQLite database at `data/app.sqlite3`
- Upload storage under `data/uploads/`
- Export storage under `data/exports/`

The local API uses the seeded `dev.planner` user for write and export actions. No login flow is required for this build.

## Prerequisites

Install these tools before setup:

- Python 3.11 or newer
- Node.js LTS and npm
- Git

Run all commands from the repository root unless a step says otherwise.

## One-Time Setup

Create the backend virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Create local environment files when they do not already exist:

```powershell
if (-not (Test-Path ".env")) {
  Copy-Item .env.example .env
}

if (-not (Test-Path "frontend\.env.local")) {
  Copy-Item frontend\.env.example frontend\.env.local
}
```

Install frontend dependencies:

```powershell
Set-Location frontend
npm install
Set-Location ..
```

## Configuration

The backend reads `.env` from the repository root. The default local values are:

```text
APP_ENV=local
DATABASE_URL=sqlite:///./data/app.sqlite3
UPLOAD_DIR=./data/uploads
EXPORT_DIR=./data/exports
SECRET_KEY=change-me-for-real-use
MAX_UPLOAD_SIZE_MB=25
LOG_LEVEL=INFO
```

The frontend reads `frontend/.env.local`:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Keep `DATABASE_URL`, `UPLOAD_DIR`, and `EXPORT_DIR` pointing at repository-local paths when using the reset steps below.

## Database Migrations

Run Alembic migrations before starting the app:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

This creates or updates `data/app.sqlite3` and seeds the default `dev.planner` user used by local write/export APIs.

## Start the App

Start the backend in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Check the backend:

```text
http://127.0.0.1:8000/api/v1/health
```

Start the frontend in another terminal:

```powershell
Set-Location frontend
npm run dev
```

Open the frontend:

```text
http://127.0.0.1:5173
```

## Test Data

Use the golden workbook for local smoke checks:

```text
backend/tests/fixtures/machine_shop_sample_input.xlsx
```

Manual smoke path:

1. Start the backend and frontend.
2. Upload `backend/tests/fixtures/machine_shop_sample_input.xlsx`.
3. Review validation issues; the sample should be usable for a planning run.
4. Create and calculate a planning run.
5. Generate first-build exports for machine load, subcontract plan, valve readiness, flow blocker, and daily execution.
6. Open the generated `.xlsx` files from `data/exports/<planning_run_id>/`.

API smoke path:

```powershell
$api = "http://127.0.0.1:8000"
$sample = "backend/tests/fixtures/machine_shop_sample_input.xlsx"

$upload = curl.exe -s -X POST "$api/api/v1/uploads" -F "file=@$sample" | ConvertFrom-Json
Invoke-RestMethod "$api/api/v1/uploads/$($upload.id)/validation-issues"

$runBody = @{
  upload_batch_id = $upload.id
  planning_horizon_days = 7
} | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri "$api/api/v1/planning-runs" -ContentType "application/json" -Body $runBody
$calculated = Invoke-RestMethod -Method Post -Uri "$api/api/v1/planning-runs/$($run.id)/calculate"

$reports = "MACHINE_LOAD", "SUBCONTRACT_PLAN", "VALVE_READINESS", "FLOW_BLOCKER", "DAILY_EXECUTION"
foreach ($report in $reports) {
  $exportBody = @{
    report_type = $report
    file_format = "XLSX"
  } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "$api/api/v1/planning-runs/$($calculated.id)/exports" -ContentType "application/json" -Body $exportBody
}
```

Generated upload artifacts and export files stay in `data/` and are ignored by Git.

## Verification Commands

Run backend tests and lint:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
```

Run frontend tests and build:

```powershell
Set-Location frontend
npm test
npm run build
Set-Location ..
```

## Local Data Reset

Use this only for repository-local developer state. Stop the backend and frontend first so SQLite and generated files are not open.

The reset removes:

- `data/app.sqlite3`
- generated upload files under `data/uploads/`
- generated export files under `data/exports/`

It keeps the committed `.gitkeep` files.

```powershell
if (-not (Test-Path ".env.example") -or -not (Test-Path "backend\app\main.py")) {
  throw "Run this from the repository root."
}

$dbPath = "data\app.sqlite3"
$runtimeDirs = "data\uploads", "data\exports"

Remove-Item -LiteralPath $dbPath -ErrorAction SilentlyContinue

foreach ($dir in $runtimeDirs) {
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  Get-ChildItem -LiteralPath $dir -Force |
    Where-Object { $_.Name -ne ".gitkeep" } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
}
```

After reset, rerun migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Runtime Paths

| Purpose | Default path | Config key |
| --- | --- | --- |
| SQLite database | `data/app.sqlite3` | `DATABASE_URL=sqlite:///./data/app.sqlite3` |
| Uploaded workbooks | `data/uploads/<upload_batch_id>/<filename>` | `UPLOAD_DIR=./data/uploads` |
| Generated exports | `data/exports/<planning_run_id>/<report_type>_<timestamp>.xlsx` | `EXPORT_DIR=./data/exports` |

The backend creates missing runtime directories on startup. Migrations create the SQLite file if it does not exist.

## Common Fixes

- If the health endpoint fails, confirm the backend terminal is still running and that migrations completed.
- If the frontend cannot reach the API, confirm `frontend/.env.local` has `VITE_API_BASE_URL=http://127.0.0.1:8000`.
- If SQLite reports a locked database during reset, stop the backend process and retry.
- If exports fail, calculate the planning run first and use `file_format` set to `XLSX`.
