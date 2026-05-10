# Release Readiness Checklist

This is the M6-E6 V1 pilot readiness checklist. It maps PRD release criteria, M6 exit criteria, verification commands, and deferred scope to concrete evidence.

Status: Ready for V1 pilot after the release verification commands pass on the release candidate.

## M6 Exit Criteria

| Criterion | Status | Evidence |
|---|---|---|
| Weekly Planning Report and A3 Planning Output are implemented or explicitly deferred | Pass | `backend/tests/test_report_exports_service.py`, `backend/tests/test_report_exports_api.py`, `backend/tests/test_m6_pilot_validation.py` |
| Open release questions are resolved or converted into tracked decisions | Pass | `docs/implementation/PRODUCT_DECISIONS.md`, PRD/TRD resolved decision lists |
| Pilot workflow can be run end to end with sample data | Pass | `docs/implementation/PILOT_VALIDATION.md`, `backend/tests/test_m6_pilot_validation.py` |
| Release checklist is complete | Pass | This document |

## PRD Release Criteria

| PRD release criterion | Status | Evidence and notes |
|---|---|---|
| Excel import works end to end | Pass | Golden workbook and upload API tests: `backend/tests/test_m5_golden_workbook_integration.py`, `backend/tests/test_m6_pilot_validation.py`, `backend/tests/test_uploads_api.py` |
| Validation issues are persisted and visible | Pass | Validation issue API and frontend validation state tests: `backend/tests/test_uploads_api.py`, `frontend/src/App.test.tsx` |
| PlanningRun and PlanningSnapshot are persisted | Pass | Planning calculation and golden workbook tests: `backend/tests/test_planning_run_calculation.py`, `backend/tests/test_m5_golden_workbook_integration.py` |
| Formulas in BUSINESS_LOGIC_FORMULAS.md are implemented and tested | Pass | Formula, planning, recommendation, readiness, throughput, and persistence tests under `backend/tests/planning/` and `backend/tests/test_planning_run_calculation.py` |
| Database schema in DATA_MODEL_REQUIREMENTS.md is implemented through migrations | Pass | Alembic migrations and schema tests: `backend/alembic/versions/`, `backend/tests/test_m1_schema.py`, `backend/tests/test_m2_*_schema.py`, `backend/tests/test_m5_report_export_schema.py` |
| User flows in USER_EXPERIENCE.md are usable end to end | Pass for pilot readiness | Frontend behavior tests plus automated pilot workflow: `frontend/src/App.test.tsx`, `backend/tests/test_m6_pilot_validation.py`; plant pilot signoff table lives in `docs/implementation/PILOT_VALIDATION.md` |
| Dashboards load from persisted database records | Pass | Dashboard API and golden/pilot tests: `backend/tests/test_dashboard_api.py`, `backend/tests/test_m5_golden_workbook_integration.py`, `backend/tests/test_m6_pilot_validation.py` |
| Planner overrides are append-only and auditable | Pass | Override API/security tests: `backend/tests/test_planner_overrides_api.py`, `backend/tests/test_m5_security_audit.py` |
| Excel exports are generated from database records | Pass | Export service/API/pilot tests: `backend/tests/test_report_exports_service.py`, `backend/tests/test_report_exports_api.py`, `backend/tests/test_m6_pilot_validation.py` |
| Golden workbook test passes using `machine_shop_sample_input.xlsx` | Pass | `backend/tests/test_m5_golden_workbook_integration.py`, `backend/tests/test_m6_pilot_validation.py` |

Known exception: no release-blocking automated test exception is currently documented. Human plant signoff remains a pilot activity, not a pre-pilot software gate.

## Release Verification Commands

Preferred one-command Windows release check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release_check.ps1
```

Equivalent manual commands:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests

Set-Location frontend
npm test
npm run build
Set-Location ..
```

Expected result:

| Command | Expected result |
|---|---|
| Backend tests | All backend tests pass |
| Ruff | `All checks passed!` |
| Frontend tests | All Vitest tests pass |
| Frontend build | TypeScript and Vite build pass |

## Resolved Release Questions

| Question | Resolution | Decision record |
|---|---|---|
| A3 PDF/HTML vs Excel | V1 ships A3 as `.xlsx`; PDF/HTML deferred | M6-E1 product decision |
| First-release roles and authentication | Seeded `dev.planner`; PLANNER writes/exports, HOD/MANAGEMENT view/export, ADMIN view-only | M6-E2 product decision |
| Stale/orphaned overrides | Show in action log only; override-driven replanning deferred | M6-E3 product decision |
| Backup location and restore process | `data/backups/` local archive plus off-machine copy; staged restore required | M6-E4 product decision |
| Accepted subcontract recommendations in exports | Included by default through recommendation status in `SUBCONTRACT_PLAN`; A3 includes planner overrides | M6-E6 product decision |
| Export packaging | Each requested report produces a workbook; Weekly Planning is the multi-sheet planning pack; A3 is a workbook with an A3 sheet | M6-E6 product decision |
| Configurable app settings UI | Deferred for V1; backend constants/config remain the source of truth | M6-E6 product decision |

## Deferred Post-V1 Scope

| Deferred item | Reason |
|---|---|
| Username/password login and session-backed current user | Seeded acting user is sufficient for pilot auditability |
| ADMIN user/settings management screens | No V1 admin surface exists yet |
| Override-driven replanning and decision replay | Requires semantic matching and planner confirmation workflow |
| Dashboard-level stale override warnings | Action-log surfacing is sufficient for pilot |
| PDF/HTML A3 print views | `.xlsx` supports V1 planning conversations |
| Scheduled/off-site backup automation | Manual archive plus off-machine copy is sufficient for pilot |
| Settings UI for formula constants | Formula constants remain backend-owned for V1 determinism |

## Release Candidate Checklist

Before tagging or handing a pilot build to users:

1. Confirm the working tree contains only intended release changes.
2. Run `scripts\release_check.ps1`.
3. Run `backend/tests/test_m6_pilot_validation.py` if the full backend test output is not being preserved.
4. Create a local runtime backup before any pilot data refresh.
5. Record the commit SHA, test command output, and pilot workbook name in the release notes or PR.
6. Review `docs/implementation/PILOT_VALIDATION.md` with planner, HOD, management, and support.
