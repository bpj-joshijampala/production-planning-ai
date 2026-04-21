# Implementation Plan: Machine Shop Planning Software V1

## 1. Document Control

| Field | Value |
|---|---|
| Product | Machine Shop Planning Software |
| Document | Implementation Plan |
| Version | V1 baseline |
| Date | 2026-04-20 |
| Status | Draft for implementation |
| Requirements baseline | `docs/requirements` |

## 2. Purpose

This document converts the V1 requirements baseline into an end-to-end implementation roadmap.

It organizes the build into milestones, epics, user stories, acceptance criteria, and exit criteria so the team can implement in a controlled sequence without mixing UI, database, formulas, and exports randomly.

## 3. Source Documents

Implementation must follow the canonical requirements baseline:

- `docs/requirements/PRD.md`
- `docs/requirements/TECHNICAL_REQUIREMENTS.md`
- `docs/requirements/DATA_MODEL_REQUIREMENTS.md`
- `docs/requirements/BUSINESS_LOGIC_FORMULAS.md`
- `docs/requirements/USER_EXPERIENCE.md`

Do not implement from archived notes or older drafts.

## 4. Delivery Principles

V1 implementation must follow these principles:

- Backend owns all business calculations.
- SQLite is the system of record.
- Excel is import/export only.
- Every PlanningRun and calculated output must be reproducible.
- The calculation engine must be built before UI richness.
- Formula correctness is more important than visual polish.
- Use test-driven development for deterministic backend logic, import validation, APIs, and exports.
- Planner overrides are append-only and do not automatically recalculate V1 plans.
- The first usable build must produce correct persisted outputs before adding later V1 exports.

## 5. TDD Implementation Policy

V1 must be implemented using test-driven development where behavior is deterministic.

The default workflow is:

```text
1. Write or update the test that describes the required behavior.
2. Run the test and confirm it fails for the expected reason.
3. Implement the smallest production change that makes the test pass.
4. Refactor while keeping the test green.
5. Run the relevant regression set before closing the story.
```

TDD is mandatory for:

- Excel parsing and validation rules.
- SQLite schema constraints and migration behavior.
- Business formulas in `BUSINESS_LOGIC_FORMULAS.md`.
- PlanningRun calculation and output persistence.
- Recommendation assignment and explanation logic.
- Planner override behavior.
- API contracts and structured error responses.
- Export sheets, columns, and metadata.

TDD is recommended, but may be lighter, for:

- simple UI layout and styling
- short-lived scaffolding
- exploratory spikes
- developer tooling

Exploratory spikes must not be merged as production behavior until covered by tests.

## 6. Milestone Overview

| Milestone | Name | Outcome |
|---|---|---|
| M0 | Project Foundation | Developers can run backend, frontend, database, tests, and local configuration |
| M1 | Data Foundation and Excel Import | Valid Excel data can be uploaded, validated, staged, promoted, and tied to a PlanningRun |
| M2 | Planning Engine Core | Readiness, priority, routing, queue, machine load, assembly risk, and throughput are calculated |
| M3 | Recommendations and Planner Decisions | Flow blockers, alternate machine logic, subcontract logic, recommendations, and overrides work |
| M4 | API and Planning Cockpit UI | Core dashboards and decision flows are usable through the app |
| M5 | First Usable Build | First-priority exports, integration tests, performance checks, and dev runbook are complete |
| M6 | V1 Completion and Pilot Readiness | Later V1 exports, pilot workflow, and release readiness checks are complete |

Each milestone contains no more than 6 epics.

## 7. Global Definition of Done

A story is done only when:

- Tests were written or updated before the production behavior where TDD applies.
- The first failing test, or a note explaining why test-first was not practical, is captured in the implementation notes or pull request.
- Code is implemented in the correct backend, frontend, or data module.
- Behavior matches the owning requirements document.
- Backend calculations are covered by unit or integration tests where applicable.
- Database changes are implemented through migrations.
- API responses are typed and validated.
- Errors are visible and actionable.
- No core calculation is duplicated in the frontend.
- The change can be run locally by another developer.

## 8. M0: Project Foundation

Goal: establish the application skeleton and developer workflow.

### M0 Exit Criteria

- Backend starts locally.
- Frontend starts locally.
- SQLite database file can be created.
- Health endpoint works.
- Test command runs.
- Project directories match the TRD structure closely enough for implementation.

### Epic M0-E1: Repository Structure and Tooling

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M0-E1-US1 | As a developer, I can see a clear backend/frontend/project folder structure so I know where to place new code. | Backend, frontend, migrations, tests, uploads, exports, and docs folders exist or are intentionally mapped. |
| M0-E1-US2 | As a developer, I can run one setup flow for local development. | Setup instructions exist; required Python and Node commands are documented; missing dependencies fail clearly. |
| M0-E1-US3 | As a developer, I can run lint or formatting checks. | Formatting/lint command exists for backend and frontend or a documented placeholder explains what will be added. |

### Epic M0-E2: Backend Scaffold

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M0-E2-US1 | As a developer, I can start the FastAPI backend. | Backend starts without import errors; `/api/v1/health` returns success. |
| M0-E2-US2 | As a developer, I can use typed settings. | Settings support database path, upload directory, export directory, environment name, and log level. |
| M0-E2-US3 | As a developer, I can see structured logs. | Startup logs include app version, environment, database path, and upload/export directories. |

### Epic M0-E3: Frontend Scaffold

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M0-E3-US1 | As a planner, I can open the app shell. | React app loads a basic shell with app name and placeholder navigation. |
| M0-E3-US2 | As a developer, I can configure the API base URL. | Frontend reads API base URL from environment/config and can call the health endpoint. |
| M0-E3-US3 | As a user, I see a clear unavailable state if backend is down. | Frontend displays a friendly connection error instead of a blank page. |

### Epic M0-E4: Local SQLite and Migration Baseline

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M0-E4-US1 | As a developer, I can initialize an empty SQLite database. | Migration tooling creates the database file and metadata table. |
| M0-E4-US2 | As a developer, I can run migrations repeatedly. | Migrations are idempotent through the migration tool; repeated command leaves DB valid. |
| M0-E4-US3 | As the backend, I enforce SQLite foreign keys. | `PRAGMA foreign_keys = ON` is applied for application connections. |

### Epic M0-E5: Baseline Automated Test Harness

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M0-E5-US1 | As a developer, I can run backend tests. | Test command runs and includes at least health/settings/database smoke tests. |
| M0-E5-US2 | As a developer, I can run frontend tests or a frontend build check. | Frontend build/test command runs in local environment. |
| M0-E5-US3 | As a developer, I can add formula tests later without route dependencies. | Test structure supports pure function tests for planning logic. |

## 9. M1: Data Foundation and Excel Import

Goal: import the workbook into a reliable SQLite-backed data model.

### M1 Exit Criteria

- Standard `.xlsx` upload is accepted.
- Non-supported formats are rejected.
- Raw upload artifact is stored.
- Required sheets and columns are validated.
- Staging rows and validation issues are persisted.
- Canonical tables are populated only after blocking errors are cleared.
- PlanningRun and PlanningSnapshot records are created.

### Epic M1-E1: Schema and Migrations

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M1-E1-US1 | As the system, I can store users and upload metadata. | `users`, `upload_batches`, and `raw_upload_artifacts` tables exist with required fields. |
| M1-E1-US2 | As the system, I can store staging and validation results. | `import_staging_rows` and `import_validation_issues` tables exist with indexes from the data model. |
| M1-E1-US3 | As the system, I can store canonical input data. | `valves`, `component_statuses`, `routing_operations`, `machines`, and `vendors` tables exist. |
| M1-E1-US4 | As the system, I can store planning run control records. | `planning_runs`, `planning_snapshots`, and `master_data_versions` tables exist. |

### Epic M1-E2: Upload Artifact Handling

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M1-E2-US1 | As a planner, I can upload an `.xlsx` workbook. | Backend accepts `.xlsx`, stores file, records filename, size, hash, uploader, and timestamp. |
| M1-E2-US2 | As a planner, I am blocked from uploading unsupported files. | `.xls`, `.xlsm`, `.csv`, and `.tsv` are rejected with clear error response. |
| M1-E2-US3 | As an auditor, I can trace uploaded data to a file artifact. | UploadBatch links to RawUploadArtifact and local storage path. |

### Epic M1-E3: Workbook Parsing and Staging

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M1-E3-US1 | As the importer, I can parse all required sheets. | `Valve_Plan`, `Component_Status`, `Routing_Master`, `Machine_Master`, and `Vendor_Master` are parsed. |
| M1-E3-US2 | As the importer, I can normalize column names. | Case, repeated spaces, and spaces/underscores are normalized per TRD/data model. |
| M1-E3-US3 | As the importer, I can store source row payloads. | Each parsed row creates an `import_staging_rows` record with sheet name, row number, and JSON payload. |
| M1-E3-US4 | As the importer, I can handle extra sheets safely. | Extra sheets are ignored unless explicitly supported later. |

### Epic M1-E4: Validation Rules

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M1-E4-US1 | As a planner, I see missing sheets and columns before planning runs. | Missing required sheets/columns create blocking validation issues. |
| M1-E4-US2 | As a planner, I see invalid dates and numbers. | Invalid required dates/numbers create row-level blocking issues. |
| M1-E4-US3 | As a planner, I see broken references. | Missing Valve_ID, Component, Machine_Type, Alt_Machine, and vendor mappings are flagged per requirements. |
| M1-E4-US4 | As the importer, I preserve repeated component names safely. | `component_line_no` is imported or generated; duplicates within same Valve_ID are blocking. |
| M1-E4-US5 | As a planner, I can proceed with warnings. | Warning issues remain visible but do not block promotion or PlanningRun creation. |

### Epic M1-E5: Canonical Promotion

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M1-E5-US1 | As the system, I promote valid staged data into canonical tables. | Canonical records are created only when no blocking issues exist. |
| M1-E5-US2 | As the system, I recalculate derived import fields. | `effective_hours_day` and `effective_lead_days` are computed by backend, not Excel formulas. |
| M1-E5-US3 | As an auditor, I can trace canonical rows back to an upload. | Canonical records are associated with PlanningRun/upload path. |

### Epic M1-E6: PlanningRun and Snapshot Creation

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M1-E6-US1 | As a planner, I can create a PlanningRun from a validated upload. | API creates PlanningRun with start date and 7/14-day horizon. |
| M1-E6-US2 | As the system, I store a reproducible snapshot. | PlanningSnapshot captures canonical input/settings needed to reproduce calculations. |
| M1-E6-US3 | As the system, I prevent planning on invalid uploads. | PlanningRun creation fails if blocking validation issues exist. |

## 10. M2: Planning Engine Core

Goal: implement deterministic backend calculations and persist outputs.

### M2 Exit Criteria

- Calculation engine runs from PlanningRun ID.
- All core formula groups are implemented and unit-tested.
- Persisted outputs are generated for incoming load, valve readiness, planned operations, machine load, vendor load, throughput, recommendations placeholder, and flow blockers placeholder where applicable.
- Results are deterministic for same input.

### Epic M2-E1: Planning Input Loader and Settings

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M2-E1-US1 | As the calculation engine, I can load all canonical input for a PlanningRun. | Loader returns valves, components, routings, machines, vendors, and run settings. |
| M2-E1-US2 | As the calculation engine, I use valid default settings. | Default horizon is 7 days; allowed horizons are 7 and 14; start date may be overridden. |
| M2-E1-US3 | As a developer, I can test calculations without API routes. | Calculation functions can run from test fixtures and PlanningRun input objects. |

### Epic M2-E2: Readiness and Assembly Risk

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M2-E2-US1 | As a planner, I can see component readiness. | Current-ready flag follows fabrication rules from formulas. |
| M2-E2-US2 | As a planner, I can see full-kit and near-ready status. | Full-kit and near-ready flags match formula thresholds. |
| M2-E2-US3 | As management, I can see assembly risk. | `otd_risk_flag` means assembly-date risk and is surfaced as Assembly Risk in API/UI. |
| M2-E2-US4 | As the system, I persist valve readiness summaries. | `valve_readiness_summaries` rows include counts, expected completion, delay, status, and risk reason. |

### Epic M2-E3: Priority Score

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M2-E3-US1 | As the planner, full-kit and near-ready jobs receive priority. | Kit status bonuses are included exactly as formula specifies. |
| M2-E3-US2 | As the planner, urgent and high-value work is ranked consistently. | Assembly urgency, priority class, critical flag, waiting age, starvation uplift, value score, and confidence penalty are applied. |
| M2-E3-US3 | As a developer, I can reproduce sorting. | Stable sort tie-breakers produce deterministic `sort_sequence`. |

### Epic M2-E4: Routing Expansion

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M2-E4-US1 | As the engine, I expand planned components into operations. | Each component creates planned operations by routing rows sorted by Operation_No. |
| M2-E4-US2 | As the engine, I preserve component identity. | Each operation carries Valve_ID, component_line_no, Component, and Operation_No. |
| M2-E4-US3 | As a planner, missing routing is visible. | Missing routing creates MISSING_ROUTING blocker and excludes affected load. |
| M2-E4-US4 | As the engine, I calculate operation hours. | `operation_hours = Qty * Std_Total_Hrs`, with setup+run fallback where allowed. |

### Epic M2-E5: Queue Simulation and Machine Load

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M2-E5-US1 | As the engine, I calculate machine-type capacity. | Active machines aggregate by Machine_Type using effective hours/day. |
| M2-E5-US2 | As the engine, I simulate queue wait. | Operation arrival, scheduled start, internal wait, processing time, and completion match formulas. |
| M2-E5-US3 | As a planner, I can see overload and underutilization. | Machine load summary includes load days, buffer days, overload, spare capacity, and underutilization. |
| M2-E5-US4 | As a planner, I can see approximation warnings. | Machine-type queue limitation is available to API/UI copy. |

### Epic M2-E6: Throughput Summary and Recalculation

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M2-E6-US1 | As management, I can see throughput gap. | Throughput target is 2.5 Cr for 7 days and 5.0 Cr for 14 days by default. |
| M2-E6-US2 | As the engine, I persist throughput output. | `throughput_summaries` includes target, planned value, gap, and risk flag. |
| M2-E6-US3 | As the system, I can recalculate a PlanningRun deterministically. | Prior calculated outputs are deleted/superseded transactionally and recreated from same inputs. |
| M2-E6-US4 | As the system, I preserve overrides during recalculation. | Planner overrides are not deleted and stale targets are detectable. |

## 11. M3: Recommendations and Planner Decisions

Goal: generate explainable planning actions and support planner authority.

### M3 Exit Criteria

- Flow blockers are generated with correct severity.
- Alternate machine recommendations are generated before subcontract recommendations.
- Subcontract recommendations use vendor comparison rules.
- Vendor load limitation is explicit.
- Overrides are recorded without automatic recalculation.

### Epic M3-E1: Flow Blockers

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M3-E1-US1 | As a planner, I can see missing data blockers. | MISSING_ROUTING and MISSING_MACHINE blockers are created with CRITICAL severity. |
| M3-E1-US2 | As a planner, I can see flow blockers. | FLOW_GAP, VALVE_FLOW_IMBALANCE, EXTREME_DELAY, and BATCH_RISK are generated per formulas. |
| M3-E1-US3 | As a planner, I can sort blockers by severity. | Severity mapping matches `BUSINESS_LOGIC_FORMULAS.md`. |
| M3-E1-US4 | As a user, each blocker has an action. | `cause` and `recommended_action` are stored for every blocker. |

### Epic M3-E2: Alternate Machine Recommendations

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M3-E2-US1 | As a planner, I can see when alternate machines are feasible. | USE_ALTERNATE recommendation is created when alternate load remains within buffer. |
| M3-E2-US2 | As the engine, I prefer alternate machines before vendors. | Subcontract is not recommended if a valid alternate is feasible. |
| M3-E2-US3 | As a planner, I can understand why alternate was selected. | Explanation includes primary overload and alternate capacity condition. |

### Epic M3-E3: Subcontract Recommendations

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M3-E3-US1 | As a planner, I can see vendor recommendations when internal completion is worse. | SUBCONTRACT recommendation requires approved vendor and vendor completion earlier than internal completion. |
| M3-E3-US2 | As a planner, I can see suggested vendor. | Vendor selection sorts by lead time, reliability, capacity rating, and vendor name. |
| M3-E3-US3 | As a planner, I can see vendor gain. | Recommendation includes internal wait, internal completion, vendor total days, and vendor gain days. |
| M3-E3-US4 | As a planner, I am warned about vendor model limits. | API/UI can display that external pending load and vendor timing are only partially modeled. |

### Epic M3-E4: Batch and Vendor Load Logic

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M3-E4-US1 | As a planner, I can identify subcontract batching opportunities. | BATCH_SUBCONTRACT_OPPORTUNITY is flagged when candidate count >= 2. |
| M3-E4-US2 | As a planner, I can see same-day batch risk. | BATCH_RISK blocker/recommendation is generated from same-day load threshold. |
| M3-E4-US3 | As a planner, I can see V1 vendor load. | Vendor load summary counts recommendations in current run and flags VENDOR_OVERLOADED by capacity rating. |

### Epic M3-E5: Recommendation Assignment and Explanation

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M3-E5-US1 | As the system, each affected operation gets the correct recommendation type. | Type assignment order follows formulas. |
| M3-E5-US2 | As a planner, I can see reason codes. | Recommendations include machine-readable reason_codes_json. |
| M3-E5-US3 | As a planner, I can read plain explanation text. | Explanation includes the numeric values needed to audit the recommendation. |
| M3-E5-US4 | As the system, recommendations reference stable entities. | Recommendation rows include planned_operation_id where available and component_line_no for component traceability. |

### Epic M3-E6: Planner Overrides

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M3-E6-US1 | As a planner, I can accept, reject, or override a recommendation. | Override endpoint records user, timestamp, target, original recommendation, decision, reason, and remarks. |
| M3-E6-US2 | As the system, I require a reason. | Override creation fails if reason is blank. |
| M3-E6-US3 | As the system, I do not recalculate after override. | Planned operations, machine load, throughput, and generated recommendations remain unchanged after override save. |
| M3-E6-US4 | As an auditor, I can list overrides for a PlanningRun. | Planner overrides endpoint returns append-only records. |

## 12. M4: API and Planning Cockpit UI

Goal: expose persisted planning outputs through usable workflows.

### M4 Exit Criteria

- Planner can upload workbook, validate, create run, calculate, and reach dashboard.
- Core dashboard APIs return persisted data.
- UI shows upload, validation, home, machine load, queue, readiness, assembly risk, recommendations, blockers, vendor, and action log views.
- UI does not duplicate backend formulas.

### Epic M4-E1: API Schemas and Dashboard Endpoints

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M4-E1-US1 | As the frontend, I can upload and validate workbooks through APIs. | Upload endpoints return upload status and validation issues. |
| M4-E1-US2 | As the frontend, I can create and calculate PlanningRuns. | PlanningRun endpoints support create, calculate, detail, and list latest. |
| M4-E1-US3 | As the frontend, I can query dashboards. | Endpoints exist for home, incoming load, machine load, queue, valve readiness, assembly risk, recommendations, blockers, vendor load, and throughput. |
| M4-E1-US4 | As a user, large tables remain usable. | List endpoints support pagination, sorting, and key filters. |

### Epic M4-E2: Upload and Validation UX

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M4-E2-US1 | As a planner, I can upload the latest Excel workbook. | Upload screen accepts `.xlsx`, shows progress, and shows upload result. |
| M4-E2-US2 | As a planner, I can understand validation results. | Blocking errors and warnings are clearly separated with sheet, row, field, and message where available. |
| M4-E2-US3 | As a planner, I cannot run planning on invalid data. | Create PlanningRun action is disabled or blocked when blocking errors exist. |

### Epic M4-E3: Planning Run and Home Dashboard UX

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M4-E3-US1 | As a planner, I can choose start date and horizon. | PlanningRun screen supports planning_start_date and 7/14-day horizon. |
| M4-E3-US2 | As a planner, I can run calculations. | UI starts calculation, shows loading state, and navigates to dashboard on success. |
| M4-E3-US3 | As management, I can triage the plan from home. | Home shows active valves, active value, throughput gap, overloads, underutilization, flow blockers, assembly risk, subcontract recommendations, and batch risks. |

### Epic M4-E4: Machine Load and Queue UX

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M4-E4-US1 | As HOD, I can see machine load by machine type. | Machine Load view shows total hours, capacity, load days, buffer days, overload, spare capacity, underutilization, and batch risk. |
| M4-E4-US2 | As planner, I can drill into a machine queue. | Queue detail shows operation-level rows sorted by priority sequence. |
| M4-E4-US3 | As planner, I see the machine-type approximation. | Queue screen displays aggregation warning from UX requirements. |

### Epic M4-E5: Valve, Component, and Assembly Risk UX

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M4-E5-US1 | As planner, I can see valve readiness. | View shows component counts, full kit, near ready, expected completion, status, and risk reason. |
| M4-E5-US2 | As planner, I can drill to component status. | Component Status view shows component line, location, dates, confidence, next operation, and blockers. |
| M4-E5-US3 | As management, I can review assembly risk. | Assembly Risk view uses assembly-date risk wording and sorts by delay, assembly date, and value. |

### Epic M4-E6: Recommendations, Vendor, and Action Log UX

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M4-E6-US1 | As planner, I can review recommendations. | Recommendation screen shows type, component, operation, machine, vendor, numeric explanation, and status. |
| M4-E6-US2 | As planner, I can make decisions. | Accept/reject/override actions require reason and update recommendation status. |
| M4-E6-US3 | As planner, I can see vendor exposure. | Vendor dashboard shows recommended jobs, capacity limit, status, reliability/notes, and V1 limitation warning. |
| M4-E6-US4 | As auditor, I can view action log. | Planner Action Log shows user, timestamp, entity, recommendation, decision, reason, and remarks. |

## 13. M5: First Usable Build

Goal: produce a usable planning loop with first-priority exports and quality gates.

### M5 Exit Criteria

- First usable build exports are generated from database records.
- Golden workbook import and planning test passes.
- Core workflows pass integration tests.
- Performance targets are checked against V1 data volume.
- Basic developer run instructions exist.

### Epic M5-E1: Export Service Foundation

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M5-E1-US1 | As the system, I can generate `.xlsx` exports from database records. | Export service creates workbook files without Excel desktop automation. |
| M5-E1-US2 | As an auditor, I can trace exports. | `report_exports` record stores report type, file path, generated by, and timestamp. |
| M5-E1-US3 | As a user, every export includes metadata. | Export_Info sheet includes PlanningRun ID, upload filename, start date, horizon, generated timestamp, and user. |

### Epic M5-E2: First Usable Build Export Reports

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M5-E2-US1 | As HOD, I can export Machine Load Report. | Export includes machine load fields from data model. |
| M5-E2-US2 | As planner, I can export Subcontract Plan. | Export includes subcontract and batch opportunity recommendations. |
| M5-E2-US3 | As management, I can export Valve Readiness Report. | Export includes readiness, assembly risk, and flow imbalance fields. |
| M5-E2-US4 | As planner, I can export Flow Blocker Report. | Export includes severity, blocker type, cause, and recommended action. |
| M5-E2-US5 | As planner, I can export Daily Execution Plan. | Export includes date, machine type, queue sequence, operation, action, wait, completion, and extreme delay. |

### Epic M5-E3: Golden Workbook and Integration Tests

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M5-E3-US1 | As developer, I can run a golden workbook test. | `machine_shop_sample_input.xlsx` imports, validates, promotes, calculates, and produces outputs. |
| M5-E3-US2 | As developer, I can test core formula groups. | Unit tests cover readiness, priority, routing, queue, machine load, vendor comparison, blockers, throughput. |
| M5-E3-US3 | As developer, I can test end-to-end planning. | Integration test covers upload through dashboard output. |
| M5-E3-US4 | As developer, I can test exports. | Export files are generated and contain expected sheets/columns. |

### Epic M5-E4: Performance and Reliability Hardening

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M5-E4-US1 | As planner, calculations complete within target. | Planning calculation meets TRD performance target for 50 to 100 valves. |
| M5-E4-US2 | As planner, upload validation completes within target. | Validation meets TRD performance target for V1 workbook size. |
| M5-E4-US3 | As user, failures are recoverable. | Calculation/import/export failures set status, log error, and show actionable message. |
| M5-E4-US4 | As developer, database writes are transactional where required. | Promotion and calculation output persistence do not leave partial successful state on failure. |

### Epic M5-E5: Security, Audit, and Basic Roles

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M5-E5-US1 | As the system, I can identify the acting user. | Development may use default planner user if auth decision is pending, but all audit records store user_id. |
| M5-E5-US2 | As auditor, I can trace uploads, calculations, overrides, and exports. | Audit fields are populated for upload, PlanningRun, override, and export records. |
| M5-E5-US3 | As admin/developer, I can restrict file types. | Upload service accepts only supported `.xlsx` files. |

### Epic M5-E6: Developer Runbook for First Build

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M5-E6-US1 | As developer, I can start the full app. | Instructions cover backend, frontend, migrations, and test data. |
| M5-E6-US2 | As developer, I can reset local dev data. | Safe local reset steps exist and do not mention production data. |
| M5-E6-US3 | As developer, I know where files are stored. | Upload, export, and SQLite paths are documented. |

## 14. M6: V1 Completion and Pilot Readiness

Goal: complete remaining V1 scope and prepare for plant pilot.

### M6 Exit Criteria

- Weekly Planning Report and A3 Planning Output are implemented or explicitly deferred by product decision.
- Open release questions are resolved or converted into tracked decisions.
- Pilot workflow can be run end to end with sample data.
- Release checklist is complete.

### Epic M6-E1: Later V1 Exports

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M6-E1-US1 | As management, I can export Weekly Planning Report. | Export includes weekly summary, machine load, valve readiness, recommendations, blockers, and throughput. |
| M6-E1-US2 | As team lead, I can export A3 Planning Output. | A3 workbook/sheet includes throughput, flow blockers, overloads, subcontract actions, batch risks, assembly risk, and overrides. |
| M6-E1-US3 | As product owner, I can decide if PDF/HTML is needed. | A3 format decision from PRD open questions is resolved or tracked. |

### Epic M6-E2: Role and Authentication Decision

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M6-E2-US1 | As product owner, I decide first-release roles. | Decision is recorded for planner-only vs HOD/management views. |
| M6-E2-US2 | As user, I can access allowed screens. | Implemented role behavior matches decision and TRD role table. |
| M6-E2-US3 | As auditor, user identity is consistent. | Uploads, PlanningRuns, overrides, and exports all reference valid users. |

### Epic M6-E3: Stale Override and Recalculation UX

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M6-E3-US1 | As planner, I can see stale overrides after recalculation. | Stale/orphaned override policy is resolved and implemented in action log or dashboard warnings. |
| M6-E3-US2 | As product owner, I can defer override-driven replanning. | Replanning with overrides remains outside first build unless explicitly added. |

### Epic M6-E4: Backup and Operational Readiness

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M6-E4-US1 | As admin, I know how to back up the app. | SQLite, upload directory, and export directory backup location/process are documented. |
| M6-E4-US2 | As admin, I can restore from backup in a test environment. | Restore steps are documented and smoke-tested. |
| M6-E4-US3 | As support, I can troubleshoot common failures. | Runbook includes upload validation failure, DB connection failure, export failure, and calculation failure. |

### Epic M6-E5: Pilot Validation

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M6-E5-US1 | As planner, I can run a full pilot workflow. | Upload, validate, plan, dashboard review, recommendation action, override, export works end to end. |
| M6-E5-US2 | As HOD, I can compare machine load manually. | Machine load calculations are manually verifiable against sample workbook. |
| M6-E5-US3 | As management, I can review pilot metrics. | Pilot captures throughput gap, overload count, subcontract count, assembly risk count, and flow blockers. |

### Epic M6-E6: Release Readiness

User stories:

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| M6-E6-US1 | As product owner, I can confirm V1 release criteria. | Every PRD release criterion is checked as pass/fail with notes. |
| M6-E6-US2 | As developer, I can run all tests before release. | Unit, integration, golden workbook, API, frontend, and export tests pass or known exceptions are documented. |
| M6-E6-US3 | As product owner, I can review unresolved scope. | Remaining open questions are resolved, deferred, or converted into post-V1 backlog items. |

## 15. Cross-Milestone Dependencies

| Dependency | Required Before |
|---|---|
| M0 backend scaffold | M1 upload/import APIs |
| M0 migrations | M1 schema implementation |
| M1 canonical import | M2 planning engine |
| M2 queue and machine load | M3 recommendations |
| M2/M3 persisted outputs | M4 dashboard APIs |
| M4 dashboard APIs | M4 frontend dashboard screens |
| M3 recommendations and M4 action APIs | M5 exports and action log |
| M5 first usable build | M6 pilot readiness |

## 16. Implementation Assumptions

The plan assumes:

- Local development may begin with a default planner user while authentication decisions remain open.
- Backend and frontend may be built in parallel only after API contracts are stable.
- The calculation engine should be developed with fixtures before UI integration.
- For deterministic behavior, tests are written first and production code follows.
- First usable build exports are mandatory before Weekly Planning and A3 exports.
- Component identity uses `component_line_no` from the beginning.
- Assembly Risk is the user-facing label for V1 OTD risk.
- The vendor model is limited to current-run recommendations and must warn users accordingly.

## 17. Risks and Mitigations

| Risk | Likely Impact | Mitigation |
|---|---|---|
| Formula mistakes create confident wrong recommendations | High trust damage | Unit tests for formula groups and golden workbook verification |
| TDD is skipped under schedule pressure | Hidden logic defects | Story definition of done requires test-first evidence or an explicit exception note |
| UI work starts before persisted outputs stabilize | Rework | Implement backend calculation spine first |
| Excel schema ambiguity causes import churn | Upload failures | Strict validation and `Component_Line_No` generation |
| Machine_Type taxonomy hides real capability differences | Misleading load | Highlight classification warning and validate master data with planner |
| Overrides are misunderstood as recalculated plans | Planner confusion | UX copy and backend behavior explicitly say no automatic recalculation |
| Export scope slows first build | Delivery delay | Ship first five exports first; Weekly/A3 later in V1 |

## 18. Recommended Immediate Next Steps

1. Create `TEST_PLAN.md` before writing planning formulas.
2. Create `API_SPEC.md` before frontend dashboard implementation.
3. Scaffold backend, frontend, migrations, and health checks with smoke tests first.
4. Write data model and import validation tests before implementing schema/import behavior.
5. Build calculation engine by writing fixture-based formula tests first.
