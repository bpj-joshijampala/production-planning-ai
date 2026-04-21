# Data Model Requirements: Machine Shop Planning Software V1

## 1. Document Control

| Field | Value |
|---|---|
| Product | Machine Shop Planning Software |
| Document | Data Model Requirements |
| Version | V1 baseline |
| Date | 2026-04-19 |
| Status | Draft for database and Excel schema baseline |
| Companion documents | PRD.md, TECHNICAL_REQUIREMENTS.md, BUSINESS_LOGIC_FORMULAS.md, USER_EXPERIENCE.md |

## 2. Purpose

This document defines the V1 data model for:

- the SQLite application database
- Excel input workbook schemas
- Excel output workbook schemas
- relationships between planning entities
- import staging and validation data
- persisted calculation outputs
- planner decisions and audit history

The database is the V1 system of record. Excel files are import/export interfaces only.

This document refines and extends the table list in `TECHNICAL_REQUIREMENTS.md`. Where schema-level details differ, this document is the more specific source for implementation.

## 3. Data Model Principles

V1 data must follow these principles:

- Every planning calculation belongs to one `planning_run`.
- Every imported row must be traceable to an `upload_batch`.
- Raw uploaded Excel files must be retained as artifacts.
- Canonical input records must be stored separately from staging rows.
- Calculated outputs must be persisted, not recalculated in the frontend.
- Planner overrides must be append-only.
- Re-uploading Excel creates a new planning run path; it must not overwrite old planning history.
- Excel exports must be generated from database records, not from live Excel formulas.
- SQLite foreign key enforcement must be enabled.

## 4. Naming and Storage Conventions

### 4.1 Naming

Use:

- `snake_case` for database tables and columns
- singular business names for source fields in Excel
- plural names for database tables
- explicit suffixes for units, such as `_days`, `_hrs`, `_cr`, `_percent`

Examples:

```text
internal_wait_days
std_total_hrs
value_cr
efficiency_percent
```

### 4.2 Primary Keys

All primary keys must be application-generated UUID strings.

SQLite type:

```text
TEXT PRIMARY KEY
```

### 4.3 Foreign Keys

Foreign keys must be declared in migrations and enforced with:

```text
PRAGMA foreign_keys = ON;
```

Recommended delete behavior:

- Delete of a `planning_run` may cascade to run-owned canonical and output tables.
- Delete of an `upload_batch` should be restricted if any planning run depends on it.
- Delete of a `user` should be restricted if audit rows depend on it.

### 4.4 Dates and Timestamps

Store dates as ISO date strings:

```text
YYYY-MM-DD
```

Store timestamps as ISO 8601 UTC strings:

```text
YYYY-MM-DDTHH:MM:SSZ
```

SQLite type:

```text
TEXT
```

### 4.5 Booleans

Store booleans as integers:

```text
0 = false
1 = true
```

SQLite type:

```text
INTEGER NOT NULL CHECK (field_name IN (0, 1))
```

### 4.6 Numeric Values

Use:

- `REAL` for hours, days, percentages, and value in Cr
- `INTEGER` for counts, sequence numbers, and row numbers

Stored decimal values may retain precision. Display values should be rounded to 2 decimals.

### 4.7 JSON

Use `TEXT` for JSON payloads.

Where practical, add:

```text
CHECK (json_valid(column_name))
```

JSON fields are allowed for staging payloads, snapshots, reason code arrays, and export metadata. Core planning fields must be modeled as typed columns, not hidden inside JSON.

## 5. Relationship Overview

Core relationship chain:

```text
users
  -> upload_batches
      -> raw_upload_artifacts
      -> import_staging_rows
      -> import_validation_issues
      -> planning_runs
          -> planning_snapshots
          -> master_data_versions
          -> valves
          -> component_statuses
          -> routing_operations
          -> machines
          -> vendors
          -> incoming_load_items
          -> valve_readiness_summaries
          -> planned_operations
          -> machine_load_summaries
          -> vendor_load_summaries
          -> throughput_summaries
          -> recommendations
          -> flow_blockers
          -> planner_overrides
          -> report_exports
```

Most planning-owned tables must include:

```text
planning_run_id TEXT NOT NULL REFERENCES planning_runs(id)
```

## 6. Table Groups

The database is organized into these groups:

| Group | Tables |
|---|---|
| Security and users | users |
| Import and validation | upload_batches, raw_upload_artifacts, import_staging_rows, import_validation_issues |
| Planning run control | planning_runs, planning_snapshots, master_data_versions |
| Canonical input data | valves, component_statuses, routing_operations, machines, vendors |
| Persisted planning outputs | incoming_load_items, valve_readiness_summaries, planned_operations, machine_load_summaries, vendor_load_summaries, throughput_summaries |
| Decisions and blockers | recommendations, flow_blockers, planner_overrides |
| Exports | report_exports |

## 7. Security and User Tables

### 7.1 users

Purpose: authentication, authorization, and audit ownership.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| username | TEXT | Yes | Unique, case-insensitive in app logic |
| display_name | TEXT | Yes | User-facing name |
| role | TEXT | Yes | PLANNER, HOD, MANAGEMENT, ADMIN |
| password_hash | TEXT | No | Required for local auth |
| active | INTEGER | Yes | Boolean |
| created_at | TEXT | Yes | UTC timestamp |
| updated_at | TEXT | No | UTC timestamp |

Indexes:

```text
unique(username)
index(role)
index(active)
```

## 8. Import and Validation Tables

### 8.1 upload_batches

Purpose: one uploaded Excel workbook event.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| original_filename | TEXT | Yes | User file name |
| stored_filename | TEXT | Yes | Server-side file name |
| file_hash | TEXT | Yes | Hash of file content |
| file_size_bytes | INTEGER | Yes | Must be > 0 |
| uploaded_by_user_id | TEXT | Yes | FK to users.id |
| uploaded_at | TEXT | Yes | UTC timestamp |
| status | TEXT | Yes | UPLOADED, VALIDATION_FAILED, VALIDATED, PROMOTED, CALCULATED |
| validation_error_count | INTEGER | Yes | Default 0 |
| validation_warning_count | INTEGER | Yes | Default 0 |

Relationships:

```text
uploaded_by_user_id -> users.id
```

Indexes:

```text
index(uploaded_at)
index(uploaded_by_user_id)
index(status)
index(file_hash)
```

### 8.2 raw_upload_artifacts

Purpose: file storage metadata for uploaded Excel files.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| upload_batch_id | TEXT | Yes | FK to upload_batches.id |
| storage_path | TEXT | Yes | Local or mounted file path |
| mime_type | TEXT | No | Detected MIME type |
| created_at | TEXT | Yes | UTC timestamp |

Relationships:

```text
upload_batch_id -> upload_batches.id
```

### 8.3 import_staging_rows

Purpose: row-level parsed data before canonical promotion.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| upload_batch_id | TEXT | Yes | FK to upload_batches.id |
| sheet_name | TEXT | Yes | Source sheet |
| row_number | INTEGER | Yes | Excel row number |
| normalized_payload_json | TEXT | Yes | JSON object, normalized column names |
| row_hash | TEXT | No | Optional row hash |
| created_at | TEXT | Yes | UTC timestamp |

Relationships:

```text
upload_batch_id -> upload_batches.id
```

Indexes:

```text
index(upload_batch_id, sheet_name)
index(upload_batch_id, sheet_name, row_number)
```

### 8.4 import_validation_issues

Purpose: blocking errors and warnings found during import.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| upload_batch_id | TEXT | Yes | FK to upload_batches.id |
| staging_row_id | TEXT | No | FK to import_staging_rows.id |
| sheet_name | TEXT | No | Source sheet |
| row_number | INTEGER | No | Source row |
| severity | TEXT | Yes | BLOCKING, WARNING |
| issue_code | TEXT | Yes | Machine-readable |
| message | TEXT | Yes | User-facing |
| field_name | TEXT | No | Canonical field |
| created_at | TEXT | Yes | UTC timestamp |

Relationships:

```text
upload_batch_id -> upload_batches.id
staging_row_id -> import_staging_rows.id
```

Indexes:

```text
index(upload_batch_id, severity)
index(upload_batch_id, sheet_name, row_number)
index(issue_code)
```

## 9. Planning Run Control Tables

### 9.1 planning_runs

Purpose: one planning calculation context.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| upload_batch_id | TEXT | Yes | FK to upload_batches.id |
| planning_start_date | TEXT | Yes | ISO date |
| planning_horizon_days | INTEGER | Yes | 7 or 14 |
| status | TEXT | Yes | CREATED, CALCULATING, CALCULATED, FAILED |
| created_by_user_id | TEXT | Yes | FK to users.id |
| created_at | TEXT | Yes | UTC timestamp |
| calculated_at | TEXT | No | UTC timestamp |
| error_message | TEXT | No | Failure message |

Relationships:

```text
upload_batch_id -> upload_batches.id
created_by_user_id -> users.id
```

Constraints:

```text
planning_horizon_days IN (7, 14)
```

Indexes:

```text
index(upload_batch_id)
index(created_at)
index(status)
index(planning_start_date)
```

### 9.2 planning_snapshots

Purpose: immutable snapshot for reproducible calculations.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK to planning_runs.id |
| snapshot_json | TEXT | Yes | JSON payload |
| created_at | TEXT | Yes | UTC timestamp |

Relationships:

```text
planning_run_id -> planning_runs.id
```

### 9.3 master_data_versions

Purpose: identify hashes of master data used for a run.

| Column | SQLite type | Required | Constraints / Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK to planning_runs.id |
| routing_version_hash | TEXT | Yes | Hash |
| machine_version_hash | TEXT | Yes | Hash |
| vendor_version_hash | TEXT | Yes | Hash |
| created_at | TEXT | Yes | UTC timestamp |

Relationships:

```text
planning_run_id -> planning_runs.id
```

## 10. Canonical Input Tables

### 10.1 valves

Purpose: canonical valve plan for one PlanningRun.

| Column | SQLite type | Required | Source field | Constraints / Notes |
|---|---|---:|---|---|
| id | TEXT | Yes | generated | Primary key |
| planning_run_id | TEXT | Yes | generated | FK |
| valve_id | TEXT | Yes | Valve_ID | Source business key |
| order_id | TEXT | Yes | Order_ID | Work order |
| customer | TEXT | Yes | Customer |  |
| valve_type | TEXT | No | Valve_Type |  |
| dispatch_date | TEXT | Yes | Dispatch_Date | ISO date |
| assembly_date | TEXT | Yes | Assembly_Date | ISO date |
| value_cr | REAL | Yes | Value_Cr | >= 0 |
| priority | TEXT | No | Priority | A, B, C, or blank |
| status | TEXT | No | Status | Source status |
| remarks | TEXT | No | Remarks |  |

Relationships:

```text
planning_run_id -> planning_runs.id
```

Unique constraints:

```text
unique(planning_run_id, valve_id)
```

Indexes:

```text
index(planning_run_id, assembly_date)
index(planning_run_id, dispatch_date)
index(planning_run_id, customer)
index(planning_run_id, priority)
```

### 10.2 component_statuses

Purpose: canonical component readiness for one PlanningRun.

| Column | SQLite type | Required | Source field | Constraints / Notes |
|---|---|---:|---|---|
| id | TEXT | Yes | generated | Primary key |
| planning_run_id | TEXT | Yes | generated | FK |
| valve_id | TEXT | Yes | Valve_ID | References valves.valve_id within run |
| component_line_no | INTEGER | Yes | Component_Line_No or generated | Stable line number within Valve_ID |
| component | TEXT | Yes | Component |  |
| qty | REAL | Yes | Qty | > 0 |
| fabrication_required | INTEGER | Yes | Fabrication_Required | Boolean |
| fabrication_complete | INTEGER | Yes | Fabrication_Complete | Boolean |
| expected_ready_date | TEXT | Yes | Expected_Ready_Date | ISO date |
| critical | INTEGER | Yes | Critical | Boolean |
| expected_from_fabrication | TEXT | No | Expected_From_Fabrication | ISO date |
| priority_eligible | INTEGER | No | Priority_Eligible | Imported optional boolean |
| ready_date_type | TEXT | Yes | Ready_Date_Type | CONFIRMED, EXPECTED, TENTATIVE |
| current_location | TEXT | No | Current_Location |  |
| comments | TEXT | No | Comments |  |

Relationships:

```text
planning_run_id -> planning_runs.id
(planning_run_id, valve_id) -> valves(planning_run_id, valve_id)
```

Unique constraint:

```text
unique(planning_run_id, valve_id, component_line_no)
```

If `Component_Line_No` is blank in Excel, the importer must generate it from source row order within each `Valve_ID`. Repeated component names are allowed when line numbers differ.

### 10.3 routing_operations

Purpose: canonical routing master for one PlanningRun.

| Column | SQLite type | Required | Source field | Constraints / Notes |
|---|---|---:|---|---|
| id | TEXT | Yes | generated | Primary key |
| planning_run_id | TEXT | Yes | generated | FK |
| component | TEXT | Yes | Component |  |
| operation_no | INTEGER | Yes | Operation_No | Sequence |
| operation_name | TEXT | Yes | Operation_Name |  |
| machine_type | TEXT | Yes | Machine_Type |  |
| alt_machine | TEXT | No | Alt_Machine |  |
| std_setup_hrs | REAL | No | Std_Setup_Hrs | >= 0 |
| std_run_hrs | REAL | No | Std_Run_Hrs | >= 0 |
| std_total_hrs | REAL | Yes | Std_Total_Hrs | > 0 |
| subcontract_allowed | INTEGER | Yes | Subcontract_Allowed | Boolean |
| vendor_process | TEXT | No | Vendor_Process |  |
| notes | TEXT | No | Notes |  |

Relationships:

```text
planning_run_id -> planning_runs.id
```

Unique constraints:

```text
unique(planning_run_id, component, operation_no)
```

Indexes:

```text
index(planning_run_id, component)
index(planning_run_id, machine_type)
index(planning_run_id, vendor_process)
```

### 10.4 machines

Purpose: canonical machine master for one PlanningRun.

| Column | SQLite type | Required | Source field | Constraints / Notes |
|---|---|---:|---|---|
| id | TEXT | Yes | generated | Primary key |
| planning_run_id | TEXT | Yes | generated | FK |
| machine_id | TEXT | Yes | Machine_ID | Source machine key |
| machine_type | TEXT | Yes | Machine_Type | Capacity pool |
| description | TEXT | No | Description |  |
| hours_per_day | REAL | Yes | Hours_per_Day | > 0 |
| efficiency_percent | REAL | Yes | Efficiency_Percent | > 0 and <= 100 |
| effective_hours_day | REAL | Yes | Effective_Hours_Day | Backend-calculated when needed |
| shift_pattern | TEXT | No | Shift_Pattern |  |
| buffer_days | REAL | Yes | Buffer_Days | > 0 |
| capability_notes | TEXT | No | Capability_Notes |  |
| active | INTEGER | Yes | Active | Boolean |

Relationships:

```text
planning_run_id -> planning_runs.id
```

Unique constraints:

```text
unique(planning_run_id, machine_id)
```

Indexes:

```text
index(planning_run_id, machine_type)
index(planning_run_id, active)
```

### 10.5 vendors

Purpose: canonical vendor master for one PlanningRun.

| Column | SQLite type | Required | Source field | Constraints / Notes |
|---|---|---:|---|---|
| id | TEXT | Yes | generated | Primary key |
| planning_run_id | TEXT | Yes | generated | FK |
| vendor_id | TEXT | Yes | Vendor_ID | Source vendor key |
| vendor_name | TEXT | Yes | Vendor_Name |  |
| primary_process | TEXT | Yes | Primary_Process | Maps to vendor process |
| turnaround_days | REAL | Yes | Turnaround_Days | >= 0 |
| transport_days_total | REAL | Yes | Transport_Days_Total | >= 0 |
| effective_lead_days | REAL | Yes | Effective_Lead_Days | Backend-calculated when needed |
| capacity_rating | TEXT | No | Capacity_Rating | Low, Medium, High |
| reliability | TEXT | No | Reliability | A, B, C |
| approved | INTEGER | Yes | Approved | Boolean |
| comments | TEXT | No | Comments |  |

Relationships:

```text
planning_run_id -> planning_runs.id
```

Unique constraints:

```text
unique(planning_run_id, vendor_id)
```

Indexes:

```text
index(planning_run_id, primary_process)
index(planning_run_id, approved)
```

## 11. Persisted Planning Output Tables

### 11.1 incoming_load_items

Purpose: persisted look-ahead rows for Incoming Load screen and export.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| valve_id | TEXT | Yes | Source Valve_ID |
| component_line_no | INTEGER | Yes | Component line within valve |
| component | TEXT | Yes | Component |
| qty | REAL | Yes | Quantity |
| availability_date | TEXT | Yes | ISO date |
| date_confidence | TEXT | Yes | CONFIRMED, EXPECTED, TENTATIVE |
| current_ready_flag | INTEGER | Yes | Boolean |
| machine_types_json | TEXT | No | JSON array of required machine types |
| priority_score | REAL | Yes | Calculated |
| same_day_arrival_load_days | REAL | No | For machine/date if applicable |
| batch_risk_flag | INTEGER | Yes | Boolean |

Indexes:

```text
index(planning_run_id, availability_date)
index(planning_run_id, valve_id)
index(planning_run_id, date_confidence)
```

### 11.2 valve_readiness_summaries

Purpose: persisted valve readiness and assembly-risk output.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| valve_id | TEXT | Yes | Source Valve_ID |
| customer | TEXT | Yes | Copied from valves |
| assembly_date | TEXT | Yes | ISO date |
| dispatch_date | TEXT | Yes | ISO date |
| value_cr | REAL | Yes | Copied from valves |
| total_components | INTEGER | Yes | Count |
| ready_components | INTEGER | Yes | Count |
| required_components | INTEGER | Yes | Count of assembly_required_components |
| ready_required_count | INTEGER | Yes | Count |
| pending_required_count | INTEGER | Yes | Count |
| full_kit_flag | INTEGER | Yes | Boolean |
| near_ready_flag | INTEGER | Yes | Boolean |
| valve_expected_completion_offset_days | REAL | No | Null if incomplete |
| valve_expected_completion_date | TEXT | No | ISO date |
| otd_delay_days | REAL | Yes | >= 0 |
| otd_risk_flag | INTEGER | Yes | Boolean |
| readiness_status | TEXT | Yes | READY, NEAR_READY, NOT_READY, AT_RISK, DATA_INCOMPLETE |
| risk_reason | TEXT | No | Primary cause |
| valve_flow_gap_days | REAL | No | Flow imbalance measure |
| valve_flow_imbalance_flag | INTEGER | Yes | Boolean |

Unique constraints:

```text
unique(planning_run_id, valve_id)
```

Indexes:

```text
index(planning_run_id, readiness_status)
index(planning_run_id, otd_risk_flag)
index(planning_run_id, assembly_date)
```

### 11.3 planned_operations

Purpose: expanded operation-level plan and queue simulation output.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| valve_id | TEXT | Yes | Source Valve_ID |
| component_line_no | INTEGER | Yes | Component line within valve |
| component | TEXT | Yes | Component |
| operation_no | INTEGER | Yes | Routing sequence |
| operation_name | TEXT | Yes | Operation |
| machine_type | TEXT | Yes | Primary machine type |
| alt_machine | TEXT | No | Alternate machine |
| qty | REAL | Yes | Quantity |
| operation_hours | REAL | Yes | qty x std_total_hrs |
| availability_date | TEXT | Yes | ISO date |
| date_confidence | TEXT | Yes | CONFIRMED, EXPECTED, TENTATIVE |
| priority_score | REAL | Yes | Calculated |
| sort_sequence | INTEGER | Yes | Final queue order |
| availability_offset_days | REAL | Yes | From planning_start_date |
| operation_arrival_offset_days | REAL | Yes | Queue input |
| operation_arrival_date | TEXT | Yes | ISO date |
| scheduled_start_offset_days | REAL | Yes | Calculated |
| internal_wait_days | REAL | Yes | Calculated |
| processing_time_days | REAL | Yes | Calculated |
| internal_completion_days | REAL | Yes | Calculated |
| internal_completion_offset_days | REAL | Yes | Calculated |
| internal_completion_date | TEXT | Yes | ISO date |
| extreme_delay_flag | INTEGER | Yes | Boolean |
| recommendation_status | TEXT | No | Optional display shortcut |

Indexes:

```text
index(planning_run_id, machine_type)
index(planning_run_id, valve_id)
index(planning_run_id, internal_completion_date)
index(planning_run_id, sort_sequence)
index(planning_run_id, extreme_delay_flag)
```

### 11.4 machine_load_summaries

Purpose: machine-type load and capacity summary.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| machine_type | TEXT | Yes | Machine type |
| total_operation_hours | REAL | Yes | Sum operation hours |
| capacity_hours_per_day | REAL | Yes | Sum effective hours/day |
| load_days | REAL | Yes | Calculated |
| buffer_days | REAL | Yes | Buffer |
| overload_flag | INTEGER | Yes | Boolean |
| overload_days | REAL | Yes | Calculated |
| spare_capacity_days | REAL | Yes | Calculated |
| underutilized_flag | INTEGER | Yes | Boolean |
| batch_risk_flag | INTEGER | Yes | Boolean |
| status | TEXT | Yes | OK, OVERLOADED, UNDERUTILIZED, DATA_INCOMPLETE |

Unique constraints:

```text
unique(planning_run_id, machine_type)
```

### 11.5 vendor_load_summaries

Purpose: vendor recommendation load summary.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| vendor_id | TEXT | Yes | Source Vendor_ID |
| vendor_name | TEXT | Yes | Vendor name |
| primary_process | TEXT | Yes | Process |
| vendor_recommended_jobs | INTEGER | Yes | Count |
| max_recommended_jobs_per_horizon | INTEGER | Yes | From capacity rating |
| selected_vendor_overloaded_flag | INTEGER | Yes | Boolean |
| status | TEXT | Yes | OK, VENDOR_OVERLOADED |

Unique constraints:

```text
unique(planning_run_id, vendor_id, primary_process)
```

### 11.6 throughput_summaries

Purpose: selected-horizon throughput check.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| target_throughput_value_cr | REAL | Yes | 2.5 for 7 days, 5.0 for 14 days by default |
| planned_throughput_value_cr | REAL | Yes | Calculated |
| throughput_gap_cr | REAL | Yes | Calculated |
| throughput_risk_flag | INTEGER | Yes | Boolean |

Unique constraints:

```text
unique(planning_run_id)
```

## 12. Decisions, Recommendations, and Blockers

### 12.1 recommendations

Purpose: recommendation records and explanations.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| planned_operation_id | TEXT | No | FK to planned_operations.id |
| recommendation_type | TEXT | Yes | Enum |
| valve_id | TEXT | No | Source Valve_ID |
| component_line_no | INTEGER | No | Component line within valve |
| component | TEXT | No | Component |
| operation_name | TEXT | No | Operation |
| machine_type | TEXT | No | Primary machine |
| suggested_machine_type | TEXT | No | Alternate machine |
| suggested_vendor_id | TEXT | No | Vendor |
| suggested_vendor_name | TEXT | No | Vendor name |
| internal_wait_days | REAL | No | Explanation field |
| processing_time_days | REAL | No | Explanation field |
| internal_completion_days | REAL | No | Explanation field |
| vendor_total_days | REAL | No | Explanation field |
| vendor_gain_days | REAL | No | Explanation field |
| subcontract_batch_candidate_count | INTEGER | No | Batch opportunity |
| batch_subcontract_opportunity_flag | INTEGER | Yes | Boolean |
| reason_codes_json | TEXT | Yes | JSON array |
| explanation | TEXT | Yes | Human-readable |
| status | TEXT | Yes | PENDING, ACCEPTED, REJECTED, OVERRIDDEN |
| created_at | TEXT | Yes | UTC timestamp |

Indexes:

```text
index(planning_run_id, recommendation_type)
index(planning_run_id, status)
index(planning_run_id, suggested_vendor_id)
index(planned_operation_id)
```

### 12.2 flow_blockers

Purpose: planning blockers requiring action.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| planned_operation_id | TEXT | No | FK to planned_operations.id |
| valve_id | TEXT | No | Source Valve_ID |
| component_line_no | INTEGER | No | Component line within valve |
| component | TEXT | No | Component |
| operation_name | TEXT | No | Operation |
| blocker_type | TEXT | Yes | Enum |
| cause | TEXT | Yes | Explanation |
| recommended_action | TEXT | Yes | User action |
| severity | TEXT | Yes | INFO, WARNING, CRITICAL |
| created_at | TEXT | Yes | UTC timestamp |

Indexes:

```text
index(planning_run_id, blocker_type)
index(planning_run_id, severity)
index(planning_run_id, valve_id)
```

### 12.3 planner_overrides

Purpose: append-only manual decision audit.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| recommendation_id | TEXT | No | FK to recommendations.id |
| entity_type | TEXT | Yes | RECOMMENDATION, OPERATION, VALVE, MACHINE, VENDOR |
| entity_id | TEXT | Yes | Entity identifier |
| original_recommendation | TEXT | No | Original recommendation |
| override_decision | TEXT | Yes | Planner decision |
| reason | TEXT | Yes | Required |
| remarks | TEXT | No | Optional |
| stale_flag | INTEGER | Yes | Boolean, default 0 |
| user_id | TEXT | Yes | FK to users.id |
| created_at | TEXT | Yes | UTC timestamp |

Indexes:

```text
index(planning_run_id)
index(recommendation_id)
index(user_id)
index(stale_flag)
```

## 13. Export Tables

### 13.1 report_exports

Purpose: generated report/export metadata.

| Column | SQLite type | Required | Notes |
|---|---|---:|---|
| id | TEXT | Yes | Primary key |
| planning_run_id | TEXT | Yes | FK |
| report_type | TEXT | Yes | Enum |
| file_path | TEXT | Yes | Stored export file |
| file_format | TEXT | Yes | XLSX, PDF, HTML |
| generated_by_user_id | TEXT | Yes | FK to users.id |
| generated_at | TEXT | Yes | UTC timestamp |
| metadata_json | TEXT | No | JSON |

Indexes:

```text
index(planning_run_id, report_type)
index(generated_at)
```

## 14. Enums and Allowed Values

Enums may be implemented as string fields with CHECK constraints or app-level validation. App-level validation is required either way.

### 14.1 user.role

```text
PLANNER
HOD
MANAGEMENT
ADMIN
```

### 14.2 upload_batches.status

```text
UPLOADED
VALIDATION_FAILED
VALIDATED
PROMOTED
CALCULATED
```

### 14.3 planning_runs.status

```text
CREATED
CALCULATING
CALCULATED
FAILED
```

### 14.4 import_validation_issues.severity

```text
BLOCKING
WARNING
```

### 14.5 date_confidence / ready_date_type

```text
CONFIRMED
EXPECTED
TENTATIVE
```

### 14.6 valve_readiness_summaries.readiness_status

```text
READY
NEAR_READY
NOT_READY
AT_RISK
DATA_INCOMPLETE
```

### 14.7 recommendations.recommendation_type

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

### 14.8 recommendations.status

```text
PENDING
ACCEPTED
REJECTED
OVERRIDDEN
```

### 14.9 flow_blockers.blocker_type

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

### 14.10 flow_blockers.severity

```text
INFO
WARNING
CRITICAL
```

### 14.11 machine_load_summaries.status

```text
OK
OVERLOADED
UNDERUTILIZED
DATA_INCOMPLETE
```

### 14.12 report_exports.report_type

```text
MACHINE_LOAD
SUBCONTRACT_PLAN
VALVE_READINESS
FLOW_BLOCKER
WEEKLY_PLANNING
DAILY_EXECUTION
A3_PLANNING
```

## 15. Excel Input Workbook Schema

The V1 input workbook must contain these sheets:

```text
Valve_Plan
Component_Status
Routing_Master
Machine_Master
Vendor_Master
```

Additional sheets are allowed and ignored unless supported later.

### 15.1 Sheet: Valve_Plan

| Excel column | Required | Canonical DB field | Type | Notes |
|---|---:|---|---|---|
| Valve_ID | Yes | valves.valve_id | Text | Unique per planning run |
| Order_ID | Yes | valves.order_id | Text |  |
| Customer | Yes | valves.customer | Text |  |
| Valve_Type | No | valves.valve_type | Text |  |
| Dispatch_Date | Yes | valves.dispatch_date | Date |  |
| Assembly_Date | Yes | valves.assembly_date | Date |  |
| Value_Cr | Yes | valves.value_cr | Number | Aliases allowed |
| Priority | No | valves.priority | Text | A, B, C, or blank |
| Status | No | valves.status | Text |  |
| Remarks | No | valves.remarks | Text |  |

### 15.2 Sheet: Component_Status

| Excel column | Required | Canonical DB field | Type | Notes |
|---|---:|---|---|---|
| Valve_ID | Yes | component_statuses.valve_id | Text | Must exist in Valve_Plan |
| Component_Line_No | No | component_statuses.component_line_no | Integer | Generated by importer if blank |
| Component | Yes | component_statuses.component | Text |  |
| Qty | Yes | component_statuses.qty | Number | > 0 |
| Fabrication_Required | Yes | component_statuses.fabrication_required | Boolean | Y/N |
| Fabrication_Complete | Yes | component_statuses.fabrication_complete | Boolean | Y/N |
| Expected_Ready_Date | Yes | component_statuses.expected_ready_date | Date | Required for planning |
| Critical | Yes | component_statuses.critical | Boolean | Y/N |
| Expected_From_Fabrication | No | component_statuses.expected_from_fabrication | Date |  |
| Priority_Eligible | No | component_statuses.priority_eligible | Boolean | Imported only |
| Ready_Date_Type | No | component_statuses.ready_date_type | Enum | Inferred if blank |
| Current_Location | No | component_statuses.current_location | Text |  |
| Comments | No | component_statuses.comments | Text |  |

### 15.3 Sheet: Routing_Master

| Excel column | Required | Canonical DB field | Type | Notes |
|---|---:|---|---|---|
| Component | Yes | routing_operations.component | Text |  |
| Operation_No | Yes | routing_operations.operation_no | Integer |  |
| Operation_Name | Yes | routing_operations.operation_name | Text |  |
| Machine_Type | Yes | routing_operations.machine_type | Text | Must exist in Machine_Master |
| Alt_Machine | No | routing_operations.alt_machine | Text | Must exist when supplied |
| Std_Setup_Hrs | No | routing_operations.std_setup_hrs | Number | >= 0 |
| Std_Run_Hrs | No | routing_operations.std_run_hrs | Number | >= 0 |
| Std_Total_Hrs | Yes | routing_operations.std_total_hrs | Number | Can be computed from setup + run |
| Subcontract_Allowed | Yes | routing_operations.subcontract_allowed | Boolean | Y/N |
| Vendor_Process | No | routing_operations.vendor_process | Text | Vendor process mapping |
| Notes | No | routing_operations.notes | Text |  |

### 15.4 Sheet: Machine_Master

| Excel column | Required | Canonical DB field | Type | Notes |
|---|---:|---|---|---|
| Machine_ID | Yes | machines.machine_id | Text | Unique per run |
| Machine_Type | Yes | machines.machine_type | Text | Capacity pool |
| Description | No | machines.description | Text |  |
| Hours_per_Day | Yes | machines.hours_per_day | Number | > 0 |
| Efficiency_Percent | Yes | machines.efficiency_percent | Number | > 0 and <= 100 |
| Effective_Hours_Day | No | machines.effective_hours_day | Number | Backend recalculates |
| Shift_Pattern | No | machines.shift_pattern | Text |  |
| Buffer_Days | Yes | machines.buffer_days | Number | > 0 |
| Capability_Notes | No | machines.capability_notes | Text |  |
| Active | Yes | machines.active | Boolean | Y/N |

### 15.5 Sheet: Vendor_Master

| Excel column | Required | Canonical DB field | Type | Notes |
|---|---:|---|---|---|
| Vendor_ID | Yes | vendors.vendor_id | Text | Unique per run |
| Vendor_Name | Yes | vendors.vendor_name | Text |  |
| Primary_Process | Yes | vendors.primary_process | Text |  |
| Turnaround_Days | Yes | vendors.turnaround_days | Number | >= 0 |
| Transport_Days_Total | Yes | vendors.transport_days_total | Number | >= 0 |
| Effective_Lead_Days | No | vendors.effective_lead_days | Number | Backend recalculates |
| Capacity_Rating | No | vendors.capacity_rating | Text | Low, Medium, High |
| Reliability | No | vendors.reliability | Text | A, B, C |
| Approved | Yes | vendors.approved | Boolean | Y/N |
| Comments | No | vendors.comments | Text |  |

## 16. Excel Output Workbook Schemas

Exports must be generated from database records.

Every output workbook must include an `Export_Info` sheet.

First usable build must support these export schemas:

1. Machine Load Report.
2. Subcontract Plan.
3. Valve Readiness Report.
4. Flow Blocker Report.
5. Daily Execution Plan.

Weekly Planning Report and A3 Planning Output may be implemented after the core workflow is stable.

### 16.1 Sheet: Export_Info

| Column | Value |
|---|---|
| Report_Type | report_exports.report_type |
| PlanningRun_ID | planning_runs.id |
| Upload_File | upload_batches.original_filename |
| Planning_Start_Date | planning_runs.planning_start_date |
| Planning_Horizon_Days | planning_runs.planning_horizon_days |
| Generated_At | report_exports.generated_at |
| Generated_By | users.display_name |

### 16.2 Machine Load Report

Sheet name:

```text
Machine_Load
```

Columns:

| Excel column | Source |
|---|---|
| Machine_Type | machine_load_summaries.machine_type |
| Total_Operation_Hours | machine_load_summaries.total_operation_hours |
| Capacity_Hours_Per_Day | machine_load_summaries.capacity_hours_per_day |
| Load_Days | machine_load_summaries.load_days |
| Buffer_Days | machine_load_summaries.buffer_days |
| Overload_Flag | machine_load_summaries.overload_flag |
| Overload_Days | machine_load_summaries.overload_days |
| Spare_Capacity_Days | machine_load_summaries.spare_capacity_days |
| Underutilized_Flag | machine_load_summaries.underutilized_flag |
| Batch_Risk_Flag | machine_load_summaries.batch_risk_flag |
| Status | machine_load_summaries.status |

### 16.3 Machine Queue Detail

Sheet name:

```text
Machine_Queue
```

Columns:

| Excel column | Source |
|---|---|
| Sort_Sequence | planned_operations.sort_sequence |
| Machine_Type | planned_operations.machine_type |
| Valve_ID | planned_operations.valve_id |
| Component_Line_No | planned_operations.component_line_no |
| Component | planned_operations.component |
| Operation_No | planned_operations.operation_no |
| Operation_Name | planned_operations.operation_name |
| Availability_Date | planned_operations.availability_date |
| Date_Confidence | planned_operations.date_confidence |
| Priority_Score | planned_operations.priority_score |
| Operation_Hours | planned_operations.operation_hours |
| Internal_Wait_Days | planned_operations.internal_wait_days |
| Processing_Time_Days | planned_operations.processing_time_days |
| Internal_Completion_Date | planned_operations.internal_completion_date |
| Extreme_Delay_Flag | planned_operations.extreme_delay_flag |
| Recommendation_Status | planned_operations.recommendation_status |

### 16.4 Subcontract Plan

Sheet name:

```text
Subcontract_Plan
```

Rows:

```text
recommendations where recommendation_type = SUBCONTRACT
or recommendation_type = BATCH_SUBCONTRACT_OPPORTUNITY
```

Columns:

| Excel column | Source |
|---|---|
| Recommendation_Type | recommendations.recommendation_type |
| Valve_ID | recommendations.valve_id |
| Component_Line_No | recommendations.component_line_no |
| Component | recommendations.component |
| Operation_Name | recommendations.operation_name |
| Machine_Type | recommendations.machine_type |
| Suggested_Vendor_ID | recommendations.suggested_vendor_id |
| Suggested_Vendor_Name | recommendations.suggested_vendor_name |
| Internal_Wait_Days | recommendations.internal_wait_days |
| Internal_Completion_Days | recommendations.internal_completion_days |
| Vendor_Total_Days | recommendations.vendor_total_days |
| Vendor_Gain_Days | recommendations.vendor_gain_days |
| Batch_Candidate_Count | recommendations.subcontract_batch_candidate_count |
| Batch_Opportunity | recommendations.batch_subcontract_opportunity_flag |
| Status | recommendations.status |
| Explanation | recommendations.explanation |

### 16.5 Valve Readiness Report

Sheet name:

```text
Valve_Readiness
```

Columns:

| Excel column | Source |
|---|---|
| Valve_ID | valve_readiness_summaries.valve_id |
| Customer | valve_readiness_summaries.customer |
| Assembly_Date | valve_readiness_summaries.assembly_date |
| Dispatch_Date | valve_readiness_summaries.dispatch_date |
| Value_Cr | valve_readiness_summaries.value_cr |
| Total_Components | valve_readiness_summaries.total_components |
| Ready_Components | valve_readiness_summaries.ready_components |
| Required_Components | valve_readiness_summaries.required_components |
| Ready_Required_Count | valve_readiness_summaries.ready_required_count |
| Pending_Required_Count | valve_readiness_summaries.pending_required_count |
| Full_Kit | valve_readiness_summaries.full_kit_flag |
| Near_Ready | valve_readiness_summaries.near_ready_flag |
| Expected_Completion_Date | valve_readiness_summaries.valve_expected_completion_date |
| Assembly_Delay_Days | valve_readiness_summaries.otd_delay_days |
| Status | valve_readiness_summaries.readiness_status |
| Risk_Reason | valve_readiness_summaries.risk_reason |
| Valve_Flow_Gap_Days | valve_readiness_summaries.valve_flow_gap_days |
| Valve_Flow_Imbalance | valve_readiness_summaries.valve_flow_imbalance_flag |

### 16.6 Flow Blocker Report

Sheet name:

```text
Flow_Blockers
```

Columns:

| Excel column | Source |
|---|---|
| Severity | flow_blockers.severity |
| Blocker_Type | flow_blockers.blocker_type |
| Valve_ID | flow_blockers.valve_id |
| Component_Line_No | flow_blockers.component_line_no |
| Component | flow_blockers.component |
| Operation_Name | flow_blockers.operation_name |
| Cause | flow_blockers.cause |
| Recommended_Action | flow_blockers.recommended_action |

### 16.7 Daily Execution Plan

Sheet name:

```text
Daily_Execution
```

Rows:

```text
planned_operations sorted by:
1. internal_completion_date ascending
2. sort_sequence ascending
```

Columns:

| Excel column | Source |
|---|---|
| Date | planned_operations.operation_arrival_date |
| Machine_Type | planned_operations.machine_type |
| Queue_Sequence | planned_operations.sort_sequence |
| Valve_ID | planned_operations.valve_id |
| Component_Line_No | planned_operations.component_line_no |
| Component | planned_operations.component |
| Operation_Name | planned_operations.operation_name |
| Planned_Action | recommendations.recommendation_type when available, else OK_INTERNAL |
| Internal_Wait_Days | planned_operations.internal_wait_days |
| Internal_Completion_Date | planned_operations.internal_completion_date |
| Extreme_Delay_Flag | planned_operations.extreme_delay_flag |

### 16.8 Weekly Planning Report

Sheet names:

```text
Weekly_Summary
Machine_Load
Valve_Readiness
Flow_Blockers
Subcontract_Plan
```

`Weekly_Summary` columns:

| Excel column | Source |
|---|---|
| Target_Throughput_Value_Cr | throughput_summaries.target_throughput_value_cr |
| Planned_Throughput_Value_Cr | throughput_summaries.planned_throughput_value_cr |
| Throughput_Gap_Cr | throughput_summaries.throughput_gap_cr |
| Throughput_Risk_Flag | throughput_summaries.throughput_risk_flag |
| Overloaded_Machine_Count | count(machine_load_summaries.overload_flag = 1) |
| Underutilized_Machine_Count | count(machine_load_summaries.underutilized_flag = 1) |
| Assembly_Risk_Valve_Count | count(valve_readiness_summaries.otd_risk_flag = 1) |
| Flow_Blocker_Count | count(flow_blockers) |
| Subcontract_Recommendation_Count | count(recommendations.recommendation_type = SUBCONTRACT) |

### 16.9 A3 Planning Output

Sheet name:

```text
A3_Planning
```

The A3 sheet must contain these sections:

1. Export info.
2. Throughput check.
3. Overloaded machines.
4. Underutilized machines.
5. Top flow blockers.
6. Subcontract actions.
7. Assembly risk valves.
8. Planner overrides.

The A3 output may be implemented as a formatted Excel sheet in V1.

## 17. Required Index Summary

At minimum, migrations must create indexes for:

```text
planning_run_id on all planning-owned tables
upload_batch_id on import tables
valve_id on valve/component/planned operation/output tables
machine_type on routing_operations, planned_operations, machine_load_summaries
vendor_id on vendors, vendor_load_summaries, recommendations
recommendation_type on recommendations
blocker_type on flow_blockers
readiness_status on valve_readiness_summaries
status columns used by dashboards
created_at / uploaded_at / generated_at timestamp columns used for sorting
```

## 18. Recalculation and Data Lifecycle

When a PlanningRun is recalculated:

1. Keep canonical input tables unchanged.
2. Delete or mark superseded calculated output rows for that PlanningRun.
3. Recreate calculated outputs in one calculation transaction where practical.
4. Preserve planner_overrides.
5. Mark overrides stale when their target recommendation or operation no longer exists.

Calculated output tables:

- incoming_load_items
- valve_readiness_summaries
- planned_operations
- machine_load_summaries
- vendor_load_summaries
- throughput_summaries
- recommendations
- flow_blockers

## 19. Data Quality Rules

The data model must support these validation outcomes:

- blocking errors stop planning
- warnings allow planning
- missing routing creates MISSING_ROUTING blocker
- missing machine creates MISSING_MACHINE blocker
- missing approved vendor creates VENDOR_UNAVAILABLE or NO_FEASIBLE_OPTION
- invalid dates create validation issues
- invalid numeric values create validation issues
- duplicate `component_line_no` values within the same `Valve_ID` create blocking validation issues
- blank `Component_Line_No` values are generated by importer before uniqueness validation

Validation issues must remain visible after import and must not be lost when planning runs are created.

## 20. Migration Requirements

The initial Alembic migration must create:

- all tables in this document
- primary keys
- foreign keys
- unique constraints
- required indexes
- enum CHECK constraints where practical
- boolean CHECK constraints

Schema changes after V1 baseline must be made through migrations, not manual database edits.

## 21. Open Data Model Questions

These should be resolved before implementation reaches release candidate:

1. Should Excel export files include internal database IDs, or only business keys like Valve_ID and Machine_Type?
2. Should planner overrides reference stable planned_operation IDs only, or also store duplicated business fields for long-term readability?
3. Should raw import staging rows be retained forever, or pruned after a retention period?
