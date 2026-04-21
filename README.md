# Machine Shop Planning Software

Milestone 0 establishes the local development foundation for the V1 planning cockpit.

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

The application creates required runtime directories on startup.
