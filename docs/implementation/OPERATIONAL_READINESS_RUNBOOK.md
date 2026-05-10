# Operational Readiness Runbook

This runbook covers V1 backup, restore, and common support recovery steps for the Production Planning AI pilot.

## Scope

Runtime state has three required parts:

| Runtime data | Default path | Config key |
| --- | --- | --- |
| SQLite database | `data/app.sqlite3` | `DATABASE_URL=sqlite:///./data/app.sqlite3` |
| Uploaded workbooks | `data/uploads/` | `UPLOAD_DIR=./data/uploads` |
| Generated exports | `data/exports/` | `EXPORT_DIR=./data/exports` |

Local backup archives are written to `data/backups/` by default. For pilot use, copy each backup archive to an off-machine location after creation. A backup left only on the application machine does not protect against workstation or disk loss.

## Backup

Run from the repository root. The command reads the current `.env` settings unless explicit paths are supplied.

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m app.operations.backup create --backup-dir data\backups --label pilot-smoke
```

The command prints the generated `.zip` path. The archive contains:

- `manifest.json`
- `database/app.sqlite3`
- `uploads/...`
- `exports/...`

If a backup with the same timestamp and label already exists, the command writes the next available suffixed filename instead of overwriting the earlier archive.

Inspect a backup manifest:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m app.operations.backup inspect data\backups\<backup-file>.zip
```

Operational rule:

- Create a backup before local reset, release validation, pilot data refresh, or any manual runtime-file cleanup.
- Keep at least the latest known-good backup plus the pre-change backup.
- Copy pilot backup archives off the application machine.

## Restore Smoke Test

Always prove a backup in a test location before restoring over active runtime data.

```powershell
$env:PYTHONPATH = "backend"
$backup = "data\backups\<backup-file>.zip"
$restoreRoot = "tmp\restore-smoke"

New-Item -ItemType Directory -Force -Path $restoreRoot | Out-Null

.\.venv\Scripts\python.exe -m app.operations.backup restore $backup `
  --database-path "$restoreRoot\app.sqlite3" `
  --upload-dir "$restoreRoot\uploads" `
  --export-dir "$restoreRoot\exports"
```

Smoke-check the restored database:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; db=r'tmp\restore-smoke\app.sqlite3'; connection=sqlite3.connect(db); print(connection.execute('PRAGMA integrity_check').fetchone()[0]); print(connection.execute('select count(*) from users').fetchone()[0]); connection.close()"
```

Expected result:

- `PRAGMA integrity_check` prints `ok`.
- `users` count is at least `1` because migrations seed `dev.planner`.
- `tmp\restore-smoke\uploads` contains restored uploaded workbook files when the source had uploads.
- `tmp\restore-smoke\exports` contains restored export files when the source had exports.

## Restore Over Local Runtime Data

Use this only after the restore smoke test passes.

1. Stop the backend and frontend.
2. Create a fresh pre-restore backup if the current runtime data might be needed.
3. Restore with `--force`.
4. Start the backend.
5. Open `/api/v1/health`.
6. Open the frontend and check the latest planning run, reports, and recommendations.

```powershell
$env:PYTHONPATH = "backend"
$backup = "data\backups\<backup-file>.zip"

.\.venv\Scripts\python.exe -m app.operations.backup restore $backup `
  --database-path data\app.sqlite3 `
  --upload-dir data\uploads `
  --export-dir data\exports `
  --force
```

The restore command stages the archive in a temporary location and runs a SQLite integrity check before replacing runtime data. Malformed archives leave the current runtime paths untouched. The command refuses to overwrite an existing database or populated upload/export directories unless `--force` is supplied.

## Troubleshooting

### Upload Validation Failure

Symptoms:

- UI shows blocking validation issues.
- API returns validation issue rows from `/api/v1/uploads/{upload_batch_id}/validation-issues`.
- Planning run setup remains disabled.

Checks:

- Confirm the file extension is `.xlsx`.
- Open validation details and separate `BLOCKING` rows from `WARNING` rows.
- Fix missing required sheets, missing columns, invalid dates/numbers, duplicate component identity, or broken references in the workbook.
- Upload the corrected workbook as a new upload; do not edit runtime upload files directly.

Recovery:

- If validation details are temporarily unavailable, use the UI retry action.
- If the upload API fails before validation, check `MAX_UPLOAD_SIZE_MB`, backend logs, and that `UPLOAD_DIR` exists and is writable.

### Database Connection Failure

Symptoms:

- Health endpoint fails.
- Backend startup logs mention SQLite path, migration, or connection errors.
- API calls return 500 before reaching business validation.

Checks:

- Confirm `.env` has a file-backed SQLite URL, for example `DATABASE_URL=sqlite:///./data/app.sqlite3`.
- Confirm the database parent directory exists.
- Run migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

- If SQLite reports a locked database, stop any running backend process and retry.

Recovery:

- Restore from a known-good backup into a test path first.
- After the smoke test passes, restore over local runtime data with `--force`.

### Export Failure

Symptoms:

- UI export card shows an error.
- API returns an export error from `/api/v1/planning-runs/{planning_run_id}/exports`.
- No `.xlsx` appears under `data/exports/<planning_run_id>/`.

Checks:

- Confirm the planning run status is `CALCULATED`.
- Confirm the request uses `file_format` = `XLSX`.
- Confirm the acting role is allowed to export: `PLANNER`, `HOD`, or `MANAGEMENT`.
- Confirm `EXPORT_DIR` exists and is writable.

Recovery:

- Recalculate the planning run if it is not calculated.
- Retry the export from the UI.
- If the export directory contains partial files from a failed manual run, back up the runtime data first, then remove only the affected generated file or empty run-specific export directory.

### Calculation Failure

Symptoms:

- Planning run status becomes `FAILED`.
- Dashboard, blockers, machine load, valve, recommendation, and export views do not show calculated data for that run.

Checks:

- Confirm the source upload status is `VALIDATED`.
- Review backend logs for the failed calculation exception.
- Check canonical row counts on the planning run.
- Review workbook data for missing routing, missing machines, invalid capacity, or dates outside the planning horizon.

Recovery:

- Fix the source workbook and upload it as a new upload.
- Create and calculate a new planning run.
- Keep the failed planning run for audit unless a local reset is intentionally being performed.

## Verification Commands

Targeted operational backup smoke test:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_operational_backup.py
```

Full backend verification:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
```
