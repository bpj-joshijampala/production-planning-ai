# Technical Requirements Document: Machine Shop Planning Software V1

## 1. Document Control

| Field | Value |
|---|---|
| Product | Machine Shop Planning Software |
| Document | Technical Requirements Document |
| Version | V1 baseline |
| Date | 2026-04-19 |
| Status | Draft for development baseline |
| Companion documents | PRD.md, DATA_MODEL_REQUIREMENTS.md, BUSINESS_LOGIC_FORMULAS.md, USER_EXPERIENCE.md |

## 2. Purpose

This document translates the V1 Product Requirements Document into implementation requirements for engineering.

The PRD defines what the product must do. This TRD defines how the V1 system must be structured so the PRD can be implemented consistently, tested, and maintained.

The PRD remains the source of truth for product intent, scope, and success criteria. `BUSINESS_LOGIC_FORMULAS.md` is the source of truth for business rules and formulas. This TRD is the source of truth for architecture, storage, APIs, module boundaries, technical constraints, and verification requirements.

## 3. Technical Principles

V1 must follow these principles:

- Use an open custom stack.
- Keep Excel as import/export only.
- Use SQLite as the V1 application database and system of record.
- Keep planning logic deterministic and backend-owned.
- Persist every PlanningRun and its calculation outputs.
- Make calculations reproducible from stored inputs and settings.
- Keep frontend calculations limited to display formatting.
- Keep all planner overrides auditable.
- Avoid Microsoft Power Platform, Dataverse, SharePoint Lists, Excel desktop automation, and live Excel workbooks as runtime dependencies.

## 4. Architecture Overview

V1 must use this architecture:

```text
Excel .xlsx input
    |
    v
FastAPI backend
    |
    +-- Upload and validation service
    +-- Import staging service
    +-- Canonical persistence service
    +-- Planning calculation engine
    +-- Recommendation engine
    +-- Export/report service
    |
    v
SQLite database file
    |
    v
React frontend dashboards
```

The backend owns all:

- workbook parsing
- validation
- canonical data persistence
- queue simulation
- priority scoring
- machine load calculations
- subcontract recommendations
- flow blocker generation
- throughput checks
- report/export generation

The frontend owns:

- user interaction
- file upload UI
- dashboard rendering
- filters and table presentation
- planner action forms
- download triggers

## 5. Required Technology Stack

### 5.1 Backend

Required:

- Python 3.11 or newer.
- FastAPI.
- Pydantic for request/response schemas and validation models.
- SQLAlchemy or SQLModel for database models and persistence.
- Alembic for schema migrations.
- openpyxl for .xlsx import.
- A pure Python export library for .xlsx output, preferably openpyxl unless another open library is selected later.

Backend calculations must not rely on Excel formulas, Excel desktop automation, COM automation, Microsoft Graph, or Microsoft 365 APIs.

### 5.2 Frontend

Required:

- React.
- TypeScript.
- A client-side router.
- A table/grid component capable of sorting, filtering, and stable column rendering.
- Charting library suitable for bar charts and simple dashboard visuals.

Frontend must consume backend APIs. It must not parse the uploaded workbook or reproduce planning calculations.

### 5.3 Database

Required:

- SQLite for V1.
- SQLite database file must be treated as the system of record.
- Foreign key enforcement must be enabled for every database connection.
- Migrations must be managed through Alembic.
- Database backup/export must be available from the backend or deployment tooling.

Recommended SQLite pragmas:

```text
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

WAL mode is recommended to improve read/write behavior for a small planning team. V1 is not designed for high-concurrency enterprise usage.

## 6. Runtime and Deployment Assumptions

V1 deployment assumptions:

- Single factory or single planning office.
- Small planning team.
- One SQLite database file per deployment.
- Backend and database run on the same server or workstation.
- Uploaded Excel files and generated exports are stored on local disk or a mounted application data directory.

V1 must not assume:

- multi-site distributed writes
- real-time shop-floor machine connectivity
- ERP integration
- MES integration
- high-concurrency editing
- cloud-only deployment

## 7. Target Repository Structure

The implementation should follow this logical structure unless the selected framework scaffolding requires minor differences.

```text
production-planning-ai/
  backend/
    app/
      api/
      core/
      db/
      models/
      schemas/
      services/
      planning/
      imports/
      exports/
      tests/
    alembic/
    pyproject.toml
  frontend/
    src/
      api/
      components/
      pages/
      routes/
      types/
      utils/
    package.json
  data/
    uploads/
    exports/
    app.sqlite3
  PRD.md
  TECHNICAL_REQUIREMENTS.md
```

The `data/` directory is runtime state and should not be committed except for placeholder files if needed.

## 8. Backend Module Requirements

Implementation should proceed in this order:

1. Write or update the relevant tests for the next behavior.
2. Excel upload, normalization, validation.
3. Canonical import into SQLite.
4. PlanningRun and snapshot creation.
5. Readiness and priority score.
6. Routing expansion.
7. Queue simulation and machine load.
8. Flow blockers, assembly risk, and throughput summary.
9. Recommendations.
10. Core dashboard APIs.
11. Override logging.
12. First usable build exports.
13. UI polish.

For deterministic backend behavior, implementation must follow test-driven development: write the failing test first, implement the smallest passing change, then refactor with the test green.

### 8.1 API Layer

The API layer must:

- expose versioned API routes under `/api/v1`
- validate request payloads with Pydantic schemas
- return structured error responses
- avoid business logic in route handlers
- delegate to service classes/functions

### 8.2 Import Module

The import module must:

- accept `.xlsx` files
- store the raw uploaded file
- compute file size and content hash
- parse required sheets using openpyxl
- normalize column names according to this TRD and `DATA_MODEL_REQUIREMENTS.md`
- create staging records
- validate staged rows
- generate `component_line_no` when `Component_Line_No` is blank
- reject duplicate `component_line_no` values within the same `Valve_ID`
- create ImportValidationIssue records
- keep missing routing as a warning-level import issue so planning can surface `MISSING_ROUTING` in calculated outputs
- keep unknown machine references blocking, but allow zero-active-capacity machine types to surface as runtime `MISSING_MACHINE` blockers
- block promotion when blocking errors exist

### 8.3 Persistence Module

The persistence module must:

- use SQLAlchemy or SQLModel models
- use Alembic migrations
- enforce foreign key relationships
- wrap import promotion in database transactions
- keep raw import records separate from canonical records
- persist PlanningRun and PlanningSnapshot records

### 8.4 Planning Engine

The planning engine must:

- be deterministic
- run only on persisted canonical data
- accept PlanningRun ID and calculation settings as input
- produce persisted calculation outputs
- implement formulas from `BUSINESS_LOGIC_FORMULAS.md`
- avoid hidden state outside the database
- be unit-testable without FastAPI route execution

The planning engine should be organized into pure or mostly pure calculation functions where practical.

Suggested service boundaries:

```text
PlanningInputLoader
ReadinessCalculator
PriorityScorer
RoutingExpander
MachineQueueSimulator
MachineLoadCalculator
AlternateMachineEvaluator
SubcontractEvaluator
FlowBlockerGenerator
ThroughputCalculator
PlanningOutputPersister
```

### 8.5 Recommendation Engine

The recommendation engine must:

- generate recommendation records for each affected operation
- use recommendation types defined in `DATA_MODEL_REQUIREMENTS.md` and assignment rules defined in `BUSINESS_LOGIC_FORMULAS.md`
- include reason codes and human-readable explanation text
- persist enough numeric fields for audit and explanation
- never overwrite planner overrides

### 8.6 Export Module

The export module must:

- generate reports from database records, not Excel formulas
- support .xlsx export for V1
- create export metadata records
- store generated export files in the configured export directory
- support these first usable build exports:
  - machine load report
  - subcontract recommendation report
  - valve readiness report
  - flow blocker report
  - daily execution plan
- support these later V1 exports after the core workflow is stable:
  - machine-wise weekly plan
  - A3 planning output

## 9. Database Requirements

### 9.1 Primary Key Strategy

All tables should use application-generated string UUIDs unless a simpler integer key is intentionally selected and consistently applied.

Recommended:

```text
id TEXT PRIMARY KEY
```

UUIDs make generated records easier to merge, reference, and export later.

### 9.2 Date and Time Storage

Use ISO formats:

```text
date fields: YYYY-MM-DD
datetime fields: ISO 8601 UTC timestamp
```

Planning calculations operate on calendar dates and decimal day offsets. Time-of-day precision is not required for scheduling in V1.

### 9.3 Numeric Storage

Recommended:

- Hours and day offsets: REAL.
- Counts: INTEGER.
- Value in Cr: REAL or NUMERIC-compatible SQLAlchemy type.

All displayed decimal day values must be rounded to 2 decimals. Stored values may retain higher precision.

### 9.4 Required Tables

The schema must include the following logical tables.

The detailed table-level schema, relationships, indexes, and Excel import/export mappings are defined in `DATA_MODEL_REQUIREMENTS.md`. That document refines this section and is the implementation authority for database migrations. Do not implement column definitions from this summary when they differ from the data model document.

#### users

Purpose: basic authentication and audit ownership.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| username | Unique |
| display_name | User-facing name |
| role | PLANNER, HOD, MANAGEMENT, ADMIN |
| password_hash | Required if local auth is implemented |
| active | Boolean |
| created_at | Timestamp |

#### upload_batches

Purpose: upload event metadata.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| original_filename | Uploaded file name |
| stored_filename | Stored server file name |
| file_hash | Content hash |
| file_size_bytes | Integer |
| uploaded_by_user_id | FK to users |
| uploaded_at | Timestamp |
| status | UPLOADED, VALIDATION_FAILED, VALIDATED, PROMOTED, CALCULATED |

#### raw_upload_artifacts

Purpose: track raw uploaded file location.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| upload_batch_id | FK |
| storage_path | Local path |
| mime_type | File type |
| created_at | Timestamp |

#### import_staging_rows

Purpose: store parsed row-level import data before promotion.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| upload_batch_id | FK |
| sheet_name | Source sheet |
| row_number | Source row number |
| normalized_payload_json | Parsed row as JSON |
| row_hash | Optional row hash |
| created_at | Timestamp |

#### import_validation_issues

Purpose: record validation findings.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| upload_batch_id | FK |
| staging_row_id | Optional FK |
| sheet_name | Source sheet |
| row_number | Optional source row |
| severity | BLOCKING, WARNING |
| issue_code | Machine-readable code |
| message | Human-readable message |
| field_name | Optional field |

#### planning_runs

Purpose: one planning calculation context.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| upload_batch_id | FK |
| planning_start_date | Date |
| planning_horizon_days | 7 or 14 |
| status | CREATED, CALCULATING, CALCULATED, FAILED |
| created_by_user_id | FK to users |
| created_at | Timestamp |
| calculated_at | Optional timestamp |
| error_message | Optional |

#### planning_snapshots

Purpose: immutable planning input snapshot for reproducibility.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| snapshot_json | Canonical input and settings snapshot |
| created_at | Timestamp |

#### master_data_versions

Purpose: identify the master data set used by a run.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| routing_version_hash | Hash or text |
| machine_version_hash | Hash or text |
| vendor_version_hash | Hash or text |
| created_at | Timestamp |

#### valves

Purpose: canonical valve plan records.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| valve_id | Source Valve_ID |
| order_id | Source Order_ID |
| customer | Text |
| valve_type | Optional text |
| dispatch_date | Date |
| assembly_date | Date |
| value_cr | Numeric |
| priority | Optional A/B/C/etc. |
| status | Optional text |
| remarks | Optional text |

Unique constraint:

```text
(planning_run_id, valve_id)
```

#### component_statuses

Purpose: canonical component readiness records.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| valve_id | FK or source valve key |
| component_line_no | Stable line number within valve |
| component | Text |
| qty | Numeric |
| fabrication_required | Boolean |
| fabrication_complete | Boolean |
| expected_ready_date | Date |
| critical | Boolean |
| expected_from_fabrication | Optional date |
| ready_date_type | CONFIRMED, EXPECTED, TENTATIVE |
| current_location | Optional text |
| comments | Optional text |

#### routing_operations

Purpose: canonical routing master records.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| component | Text |
| operation_no | Integer |
| operation_name | Text |
| machine_type | Text |
| alt_machine | Optional text |
| std_setup_hrs | Optional numeric |
| std_run_hrs | Optional numeric |
| std_total_hrs | Numeric |
| subcontract_allowed | Boolean |
| vendor_process | Optional text |
| notes | Optional text |

Unique constraint:

```text
(planning_run_id, component, operation_no)
```

#### machines

Purpose: machine master records.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| machine_id | Source Machine_ID |
| machine_type | Text |
| description | Optional text |
| hours_per_day | Numeric |
| efficiency_percent | Numeric |
| effective_hours_day | Numeric |
| shift_pattern | Optional text |
| buffer_days | Numeric |
| capability_notes | Optional text |
| active | Boolean |

#### vendors

Purpose: vendor master records.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| vendor_id | Source Vendor_ID |
| vendor_name | Text |
| primary_process | Text |
| turnaround_days | Numeric |
| transport_days_total | Numeric |
| effective_lead_days | Numeric |
| capacity_rating | Low, Medium, High, or blank |
| reliability | A, B, C, or blank |
| approved | Boolean |
| comments | Optional text |

#### incoming_load_items

Purpose: persisted look-ahead rows for the Incoming Load screen and exports.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| valve_id | Source Valve_ID |
| component_line_no | Stable line number within valve |
| component | Text |
| qty | Numeric |
| availability_date | Date |
| date_confidence | CONFIRMED, EXPECTED, TENTATIVE |
| current_ready_flag | Boolean |
| machine_types_json | JSON array |
| priority_score | Numeric |
| same_day_arrival_load_days | Optional numeric |
| batch_risk_flag | Boolean |

#### valve_readiness_summaries

Purpose: persisted valve readiness and assembly-risk output.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| valve_id | Source Valve_ID |
| customer | Text |
| assembly_date | Date |
| dispatch_date | Date |
| value_cr | Numeric |
| total_components | Integer |
| ready_components | Integer |
| required_components | Integer |
| ready_required_count | Integer |
| pending_required_count | Integer |
| full_kit_flag | Boolean |
| near_ready_flag | Boolean |
| valve_expected_completion_date | Optional date |
| otd_delay_days | Numeric |
| otd_risk_flag | Boolean |
| readiness_status | READY, NEAR_READY, NOT_READY, AT_RISK, DATA_INCOMPLETE |
| risk_reason | Optional text |
| valve_flow_gap_days | Optional numeric |
| valve_flow_imbalance_flag | Boolean |

#### planned_operations

Purpose: expanded operation-level plan and queue simulation output.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| valve_id | Source Valve_ID |
| component_line_no | Stable line number within valve |
| component | Text |
| operation_no | Integer |
| operation_name | Text |
| machine_type | Text |
| alt_machine | Optional text |
| qty | Numeric |
| operation_hours | Numeric |
| availability_date | Date |
| date_confidence | CONFIRMED, EXPECTED, TENTATIVE |
| priority_score | Numeric |
| sort_sequence | Integer |
| operation_arrival_offset_days | Numeric |
| scheduled_start_offset_days | Numeric |
| internal_wait_days | Numeric |
| processing_time_days | Numeric |
| internal_completion_days | Numeric |
| internal_completion_offset_days | Numeric |
| internal_completion_date | Date |
| extreme_delay_flag | Boolean |

#### machine_load_summaries

Purpose: machine-type load and capacity summary.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| machine_type | Text |
| total_operation_hours | Numeric |
| capacity_hours_per_day | Numeric |
| load_days | Numeric |
| buffer_days | Numeric |
| overload_flag | Boolean |
| overload_days | Numeric |
| spare_capacity_days | Numeric |
| underutilized_flag | Boolean |
| batch_risk_flag | Boolean |

#### vendor_load_summaries

Purpose: V1 vendor recommendation load summary.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| vendor_id | Source Vendor_ID |
| vendor_name | Text |
| primary_process | Text |
| vendor_recommended_jobs | Integer |
| max_recommended_jobs_per_horizon | Integer |
| selected_vendor_overloaded_flag | Boolean |

#### throughput_summaries

Purpose: selected-horizon throughput target check.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| target_throughput_value_cr | Numeric, horizon-scaled |
| planned_throughput_value_cr | Numeric |
| throughput_gap_cr | Numeric |
| throughput_risk_flag | Boolean |

#### recommendations

Purpose: recommendation records and explanations.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| planned_operation_id | Optional FK |
| recommendation_type | Enum |
| valve_id | Optional source Valve_ID |
| component_line_no | Optional component line within valve |
| component | Optional text |
| operation_name | Optional text |
| machine_type | Optional text |
| suggested_machine_type | Optional text |
| suggested_vendor_id | Optional text |
| suggested_vendor_name | Optional text |
| internal_wait_days | Optional numeric |
| processing_time_days | Optional numeric |
| internal_completion_days | Optional numeric |
| vendor_total_days | Optional numeric |
| vendor_gain_days | Optional numeric |
| reason_codes_json | JSON array |
| explanation | Text |
| status | PENDING, ACCEPTED, REJECTED, OVERRIDDEN |
| created_at | Timestamp |

#### flow_blockers

Purpose: planning blockers requiring attention.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| planned_operation_id | Optional FK |
| valve_id | Optional source Valve_ID |
| component_line_no | Optional component line within valve |
| component | Optional text |
| operation_name | Optional text |
| blocker_type | Enum |
| cause | Text |
| recommended_action | Text |
| severity | INFO, WARNING, CRITICAL |

#### planner_overrides

Purpose: audit trail of manual decisions.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| recommendation_id | Optional FK |
| entity_type | Text |
| entity_id | Text |
| original_recommendation | Text |
| override_decision | Text |
| reason | Text |
| remarks | Optional text |
| user_id | FK to users |
| created_at | Timestamp |

#### report_exports

Purpose: generated export metadata.

Required fields:

| Field | Notes |
|---|---|
| id | Primary key |
| planning_run_id | FK |
| report_type | Enum |
| file_path | Text |
| file_format | XLSX, PDF, HTML |
| generated_by_user_id | FK to users |
| generated_at | Timestamp |

## 10. Required Enums

The implementation must centralize enum values.

### 10.1 Import Status

```text
UPLOADED
VALIDATION_FAILED
VALIDATED
PROMOTED
CALCULATED
```

### 10.2 Planning Run Status

```text
CREATED
CALCULATING
CALCULATED
FAILED
```

### 10.3 Validation Severity

```text
BLOCKING
WARNING
```

### 10.4 Date Confidence

```text
CONFIRMED
EXPECTED
TENTATIVE
```

### 10.5 Valve Readiness Status

```text
READY
NEAR_READY
NOT_READY
AT_RISK
DATA_INCOMPLETE
```

### 10.6 Recommendation Type

```text
OK_INTERNAL
MACHINE_OVERLOAD
USE_ALTERNATE
SUBCONTRACT
HOLD_FOR_PRIORITY_FLOW
EXTREME_DELAY
BATCH_SUBCONTRACT_OPPORTUNITY
BATCH_RISK
FLOW_BLOCKER
NO_FEASIBLE_OPTION
DATA_ERROR
```

### 10.7 Flow Blocker Type

```text
MISSING_COMPONENT
MISSING_ROUTING
MISSING_MACHINE
MACHINE_OVERLOAD
BATCH_RISK
FLOW_GAP
VALVE_FLOW_IMBALANCE
EXTREME_DELAY
VENDOR_UNAVAILABLE
VENDOR_OVERLOADED
```

### 10.8 Recommendation Status

```text
PENDING
ACCEPTED
REJECTED
OVERRIDDEN
```

### 10.9 Flow Blocker Severity

```text
INFO
WARNING
CRITICAL
```

### 10.10 Machine Status

```text
OK
OVERLOADED
UNDERUTILIZED
DATA_INCOMPLETE
```

### 10.11 Report Type

```text
MACHINE_LOAD
SUBCONTRACT_PLAN
VALVE_READINESS
FLOW_BLOCKER
WEEKLY_PLANNING
DAILY_EXECUTION
A3_PLANNING
```

## 11. Excel Import Requirements

### 11.1 Supported Files

V1 must support:

```text
.xlsx
```

V1 must reject:

```text
.xls
.xlsm
.csv
.tsv
```

unless support is explicitly added later.

### 11.2 Required Sheets

The import parser must support the input workbook sheets defined in `DATA_MODEL_REQUIREMENTS.md`:

- Valve_Plan
- Component_Status
- Routing_Master
- Machine_Master
- Vendor_Master

The workbook may contain additional sheets. Additional sheets must be ignored unless explicitly supported later.

### 11.3 Column Normalization

The import parser must implement these normalization rules:

- trim spaces
- collapse repeated spaces
- treat spaces and underscores as equivalent
- match case-insensitively
- remove currency symbols and punctuation before alias matching
- map aliases to canonical names

### 11.4 Formula Handling

For imported cells:

- If openpyxl returns a calculated value, use the calculated value.
- If a required value is only present as a formula with no cached result, mark the field invalid.
- The backend must not use Excel to recalculate formulas.
- Derived values such as Effective_Hours_Day and Effective_Lead_Days must be recalculated by the backend when source fields are available.

### 11.5 Import Idempotency

Uploading the same file twice must create two UploadBatch records unless duplicate-blocking is explicitly configured later.

Re-uploading must not overwrite an existing PlanningRun.

## 12. Planning Calculation Requirements

### 12.1 Calculation Ownership

All planning calculations must run in the backend.

The frontend must display stored calculation outputs. It must not recalculate:

- priority_score
- load_days
- internal_wait_days
- internal_completion_date
- vendor_gain_days
- otd_delay_days
- throughput_gap_cr

### 12.2 Calculation Input

The calculation engine input must be:

- planning_run_id
- planning_start_date
- planning_horizon_days
- canonical records associated with the PlanningRun

### 12.3 Calculation Output

The calculation engine must persist:

- incoming_load_items
- valve_readiness_summaries
- planned_operations
- machine_load_summaries
- vendor_load_summaries
- throughput_summaries
- recommendations
- flow_blockers
- planning_snapshots

### 12.4 Recalculation Behavior

Creating a planner override must not automatically trigger full recalculation in V1.

On override creation, the backend must:

- create an append-only planner override record
- update the affected recommendation status where applicable
- leave planned operations unchanged
- leave machine load summaries unchanged
- leave throughput summaries unchanged
- avoid generating replacement recommendations

If a PlanningRun is recalculated:

- previous calculated outputs for that PlanningRun must be deleted or marked superseded in one transaction
- new outputs must be inserted in the same transaction where practical
- planner overrides must not be silently deleted
- if recalculation invalidates an override target, the override must be shown as stale or orphaned

### 12.5 Determinism

Given the same PlanningRun inputs and settings, the calculation engine must produce the same outputs.

Sorting must be stable and must include the tie-breakers defined in `BUSINESS_LOGIC_FORMULAS.md`.

## 13. API Requirements

All APIs must be versioned under:

```text
/api/v1
```

### 13.1 Health

```text
GET /api/v1/health
```

Returns service health and database connectivity status.

### 13.2 Uploads

```text
POST /api/v1/uploads
```

Accepts `.xlsx` file upload.

Returns:

- upload_batch_id
- status
- validation summary if validation is run synchronously

```text
GET /api/v1/uploads/{upload_batch_id}
```

Returns upload metadata and status.

```text
GET /api/v1/uploads/{upload_batch_id}/validation-issues
```

Returns validation issues grouped by severity, sheet, and row.

### 13.3 Planning Runs

```text
POST /api/v1/planning-runs
```

Creates a PlanningRun from a validated UploadBatch.

Request fields:

- upload_batch_id
- planning_start_date
- planning_horizon_days

```text
POST /api/v1/planning-runs/{planning_run_id}/calculate
```

Runs or reruns planning calculations.

```text
GET /api/v1/planning-runs
```

Lists planning runs.

```text
GET /api/v1/planning-runs/{planning_run_id}
```

Returns PlanningRun details and calculation status.

### 13.4 Dashboards

```text
GET /api/v1/planning-runs/{planning_run_id}/dashboard
GET /api/v1/planning-runs/{planning_run_id}/incoming-load
GET /api/v1/planning-runs/{planning_run_id}/valve-readiness
GET /api/v1/planning-runs/{planning_run_id}/machine-load
GET /api/v1/planning-runs/{planning_run_id}/machine-load/{machine_type}/queue
GET /api/v1/planning-runs/{planning_run_id}/subcontract-recommendations
GET /api/v1/planning-runs/{planning_run_id}/flow-blockers
GET /api/v1/planning-runs/{planning_run_id}/vendor-load
GET /api/v1/planning-runs/{planning_run_id}/assembly-risk
GET /api/v1/planning-runs/{planning_run_id}/throughput
```

Dashboard endpoints must support pagination where row counts can grow.

Recommended query parameters:

- `page`
- `page_size`
- `sort`
- `direction`
- `machine_type`
- `customer`
- `status`
- `blocker_type`
- `recommendation_type`

### 13.5 Planner Overrides

```text
POST /api/v1/planner-overrides
```

Creates an override. This endpoint must not trigger planning recalculation in V1.

Required fields:

- planning_run_id
- entity_type
- entity_id
- original_recommendation
- override_decision
- reason

```text
GET /api/v1/planning-runs/{planning_run_id}/planner-overrides
```

Lists overrides for a PlanningRun.

### 13.6 Exports

```text
POST /api/v1/planning-runs/{planning_run_id}/exports
```

Generates an export.

Request fields:

- report_type
- file_format

```text
GET /api/v1/exports/{report_export_id}/download
```

Downloads generated file.

## 14. Frontend Requirements

The frontend must provide screens matching the PRD:

- Home Dashboard
- Data Upload
- Incoming Load
- Machine Load Dashboard
- Machine Queue Detail
- Subcontract Recommendation
- Valve Readiness
- Component Status
- Planner Action Log
- Vendor Dashboard
- Assembly Risk Dashboard
- Reports
- A3 Planning Output

### 14.1 Frontend State

Frontend state must treat PlanningRun as the primary context.

The selected PlanningRun ID must drive all dashboard API calls.

### 14.2 Display Rules

The frontend must:

- show all calculated day values to 2 decimals
- show dates as calendar dates
- visually distinguish CONFIRMED, EXPECTED, and TENTATIVE rows
- highlight OVERLOADED, UNDERUTILIZED, AT_RISK, EXTREME_DELAY, and FLOW_BLOCKER statuses
- expose explanation text for recommendations
- require a reason before submitting overrides

### 14.3 No Business Logic Duplication

The frontend must not duplicate backend planning formulas.

Permitted frontend calculations:

- table totals for currently displayed rows
- display formatting
- chart formatting
- filter counts already returned by API

## 15. Error Handling Requirements

API errors must use a consistent structure:

```json
{
  "error_code": "VALIDATION_FAILED",
  "message": "Workbook contains blocking validation errors.",
  "details": []
}
```

Required error categories:

- INVALID_FILE_TYPE
- WORKBOOK_PARSE_FAILED
- VALIDATION_FAILED
- PLANNING_RUN_NOT_FOUND
- CALCULATION_FAILED
- EXPORT_FAILED
- OVERRIDE_REQUIRES_REASON
- DATABASE_ERROR

Blocking import errors must prevent PlanningRun creation.

Calculation errors must set PlanningRun status to FAILED and preserve the error message.

## 16. Security Requirements

V1 must include basic authenticated access.

Minimum user roles:

| Role | Capabilities |
|---|---|
| PLANNER | Upload, calculate, view, override, export |
| HOD | View dashboards, export |
| MANAGEMENT | View dashboards, export |
| ADMIN | Manage users and settings |

Authentication may be local username/password in V1.

Passwords must be stored as hashes, never plaintext.

All write actions must include authenticated user context.

## 17. Audit Requirements

The system must retain:

- upload history
- validation issues
- PlanningRun creation metadata
- calculation status and timestamp
- generated recommendations
- planner overrides
- export history

Planner overrides must be append-only in V1. Editing or deleting overrides is out of scope unless explicitly added later.

## 18. Backup and Data Protection Requirements

The application must provide an operational way to back up:

- SQLite database file
- uploaded Excel files
- generated export files

Minimum V1 backup requirement:

- document the runtime data directory
- provide a manual backup command or script
- ensure backups can be restored in a local environment

The application must not store uploaded files only in temporary directories.

## 19. Performance Requirements

The implementation must satisfy PRD performance targets:

- dashboard calculations for 50 to 100 valves complete in under 3 seconds after upload
- upload validation completes in under 10 seconds for the V1 workbook size

Additional technical targets:

- dashboard API responses should return in under 1 second for typical V1 data volume
- export generation should complete in under 10 seconds for typical V1 data volume
- APIs returning tables must support pagination

## 20. Testing Requirements

V1 implementation must use test-driven development for deterministic behavior.

Required TDD scope:

- import normalization and validation
- database constraints and migrations
- business formulas
- PlanningRun calculation persistence
- recommendation logic
- planner override behavior
- API contracts
- export generation

For these areas, a story is not complete unless the relevant tests were written or updated before the production behavior, or the implementation notes explain why test-first was not practical and identify the compensating tests.

### 20.1 Unit Tests

Unit tests must cover:

- column normalization
- workbook validation rules
- readiness calculation
- priority_score calculation
- routing expansion
- queue simulation
- machine load calculation
- overload and underutilization flags
- extreme delay rule
- same-day batch risk
- flow gap and valve flow imbalance
- subcontract vendor selection
- batch subcontract opportunity
- throughput calculation

### 20.2 Integration Tests

Integration tests must cover:

- upload workbook
- create staging rows
- validation issue generation
- promotion to canonical tables
- PlanningRun creation
- calculation output persistence
- dashboard endpoint responses
- planner override creation
- export generation

### 20.3 Golden Workbook Test

The sample workbook `machine_shop_sample_input.xlsx` must be used as a golden import test.

The golden test must verify:

- required sheets parse successfully
- canonical records are created
- planning calculation completes
- machine load summary is produced
- valve readiness is produced
- recommendations and flow blockers are produced where rules trigger them

### 20.4 Acceptance Scenario Tests

The release criteria in `PRD.md` and formula test cases in `BUSINESS_LOGIC_FORMULAS.md` must be represented as automated tests or documented manual test cases before V1 release.

## 21. Logging Requirements

The backend must log:

- application startup
- database connection status
- upload start and completion
- validation summary
- PlanningRun creation
- calculation start and completion
- calculation failures
- export generation
- override creation

Logs must not include passwords or sensitive file contents.

## 22. Configuration Requirements

The backend must support configuration through environment variables or a local config file.

Required configuration:

```text
APP_ENV
DATABASE_URL
UPLOAD_DIR
EXPORT_DIR
SECRET_KEY
MAX_UPLOAD_SIZE_MB
```

Default local DATABASE_URL:

```text
sqlite:///./data/app.sqlite3
```

## 23. Migration Requirements

Alembic migrations must be used for all schema changes.

The initial migration must create:

- all core tables
- primary keys
- foreign keys
- required indexes
- unique constraints

Required indexes:

- planning_run_id on all planning-owned tables
- valve_id on valve/component/planned operation tables
- machine_type on planned_operations and machine_load_summaries
- recommendation_type on recommendations
- blocker_type on flow_blockers
- status fields used by dashboards

## 24. Report Export Requirements

First usable build must generate `.xlsx` exports for:

- Machine Load Report
- Subcontract Plan
- Valve Readiness Report
- Flow Blocker Report
- Daily Execution Plan

Later V1 export increment:

- Weekly Planning Report
- A3 Planning Output

Exports must:

- include PlanningRun ID
- include planning_start_date
- include planning_horizon_days
- include generated timestamp
- include source upload filename
- use database-calculated values
- avoid workbook formulas for core calculations

## 25. Open Technical Questions

These questions do not block initial scaffolding, but should be resolved before final V1 release:

1. Should local authentication be implemented immediately, or can V1 begin with a single default planner user in development?
2. Should generated exports include one workbook with multiple sheets or separate files per report?
3. Should stale planner overrides after recalculation remain visible only in the action log, or also appear as warnings on affected dashboards?
4. What is the preferred backup location for the SQLite database and upload/export directories?
5. Should app settings such as flow_gap_limit_days be configurable in the UI or kept as backend constants for V1?
