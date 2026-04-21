# Test Plan: Machine Shop Planning Software V1

## 1. Document Control

| Field | Value |
|---|---|
| Product | Machine Shop Planning Software |
| Document | Test Plan |
| Version | V1 baseline |
| Date | 2026-04-20 |
| Status | Draft for implementation |
| Requirements baseline | `docs/requirements` |
| Implementation plan | `docs/implementation/IMPLEMENTATION_PLAN.md` |

## 2. Purpose

This document defines the V1 testing strategy for Machine Shop Planning Software.

The product is rule-based and deterministic. The test plan must therefore prove that:

- Excel import is strict and traceable.
- SQLite persistence follows the data model.
- Business formulas produce reproducible results.
- PlanningRun outputs are persisted and explainable.
- Recommendations follow the documented rule order.
- Planner overrides are auditable and do not trigger automatic recalculation.
- Dashboards and exports use database records, not frontend formulas or Excel formulas.

## 3. Source Documents

Testing must trace to:

- `docs/requirements/PRD.md`
- `docs/requirements/TECHNICAL_REQUIREMENTS.md`
- `docs/requirements/DATA_MODEL_REQUIREMENTS.md`
- `docs/requirements/BUSINESS_LOGIC_FORMULAS.md`
- `docs/requirements/USER_EXPERIENCE.md`
- `docs/implementation/IMPLEMENTATION_PLAN.md`

## 4. Test Principles

V1 tests must follow these principles:

- Use test-driven development for deterministic behavior.
- Write the failing test before implementing import rules, formulas, persistence behavior, API contracts, recommendations, overrides, and exports.
- Test backend formulas as pure functions wherever practical.
- Test persisted output tables, not only API responses.
- Use deterministic fixtures with expected numeric outputs.
- Use the golden workbook as an end-to-end regression fixture.
- Avoid testing calculations in the frontend because the frontend must not own calculations.
- Include negative tests for missing data, invalid files, and broken references.
- Treat formula changes as high-risk changes requiring regression test updates.
- Keep test data small enough to debug by hand and large enough to reveal queue behavior.

### 4.1 TDD Workflow

The default implementation loop is red-green-refactor:

```text
Red: write a failing test for the next required behavior.
Green: write the smallest implementation that passes the test.
Refactor: improve design while keeping the test green.
Regression: run the affected test set before moving on.
```

TDD applies most strictly to:

- formula calculations
- import validation
- data model constraints
- PlanningRun calculation persistence
- recommendations
- overrides
- API contracts
- exports

For UI work, write tests first for behavior and state transitions where practical. Pure visual styling may be checked with build, smoke, or manual UX tests.

If test-first implementation is not practical for a story, the implementation note or pull request must say why and identify the compensating test added before the story is considered done.

### 4.2 TDD Story Checklist

Before production code:

- Identify the requirement or formula being implemented.
- Choose the test ID or create one in this plan.
- Create or update the smallest fixture needed.
- Write the failing test.
- Confirm the failure message proves the intended behavior is missing.

Before story closure:

- Confirm the new test passes.
- Run the relevant regression set from Section 21.
- Confirm no frontend calculation was introduced for backend-owned logic.
- Update expected fixtures only when the requirement changed.

## 5. Test Levels

| Level | Purpose | Primary Owner | Automation Priority |
|---|---|---|---|
| Static checks | Formatting, typing, import sanity | Engineering | P1 |
| Unit tests | Pure formulas, validation helpers, parsers | Engineering | P0 |
| Data model tests | Constraints, migrations, relationships | Engineering | P0 |
| Integration tests | Upload through persisted planning outputs | Engineering | P0 |
| API tests | Request/response behavior and errors | Engineering | P0 |
| Frontend tests | Screen rendering, actions, states | Engineering | P1 |
| Export tests | XLSX sheets, columns, metadata, values | Engineering | P0 |
| Performance tests | V1 workbook-size timing targets | Engineering | P1 |
| Manual acceptance tests | Planner workflow and release signoff | Product and Engineering | P1 |
| Pilot validation | Real-world planner review | Product, Planner, HOD | P1 |

Priority definitions:

| Priority | Meaning |
|---|---|
| P0 | Must pass before first usable build |
| P1 | Must pass before V1 pilot |
| P2 | Useful after V1 pilot or for hardening |

## 6. Test Environments

### 6.1 Local Development

Purpose:

- Fast feedback while building modules.
- Unit tests and small integration tests.
- Local SQLite database and temporary upload/export directories.

Required characteristics:

- Uses isolated test database files.
- Uses isolated upload/export temp directories.
- Can run without network access.
- Can reset test data safely.

### 6.2 CI or Shared Verification

Purpose:

- Repeatable validation before merging changes.
- Runs unit, data model, integration, API, and export tests.

Required characteristics:

- Creates fresh SQLite database per run.
- Uses committed fixtures only.
- Does not depend on developer machine paths.
- Stores generated test exports only as temporary artifacts.

### 6.3 Pilot Verification

Purpose:

- Validate real planner workflow using sample or plant-approved workbook.
- Compare machine load, recommendations, and exports with manual expectations.

Required characteristics:

- Uses a controlled database copy.
- Preserves upload and PlanningRun history.
- Captures user feedback and discrepancies.

## 7. Test Data Strategy

### 7.1 Golden Workbook

The golden workbook is:

```text
machine_shop_sample_input.xlsx
```

Golden workbook tests must verify:

- required sheets parse successfully
- staging rows are created
- validation result is expected
- canonical records are created
- PlanningRun and PlanningSnapshot are created
- calculation completes
- incoming load rows are produced
- valve readiness rows are produced
- planned operations are produced
- machine load summaries are produced
- flow blockers are produced where rules trigger them
- recommendations are produced where rules trigger them
- first usable build exports can be generated

Golden workbook expectations must be stored as explicit assertions, not vague smoke tests.

### 7.2 Formula Fixtures

Formula fixtures should be small, hand-checkable datasets.

Recommended fixture groups:

| Fixture | Purpose |
|---|---|
| balanced_load | No overload, no subcontract recommendation |
| hbm_overload | HBM exceeds buffer |
| alternate_available | Primary overloaded, alternate feasible |
| vendor_faster | Vendor completion earlier than internal completion |
| no_vendor | Subcontract allowed but no approved vendor |
| full_kit | All required components ready |
| near_ready | One or two required components pending |
| assembly_risk | Expected completion after Assembly_Date |
| batch_risk | Same-day arrivals exceed one machine-type day |
| flow_gap | Consecutive operation gap exceeds 2 days |
| valve_flow_imbalance | Critical component completion spread exceeds 2 days |
| extreme_delay | Internal wait exceeds 2 x buffer days |
| repeated_component | Same component name appears more than once with different component_line_no |

### 7.3 Negative Workbooks

Negative workbook fixtures must cover:

- unsupported file type
- missing required sheet
- missing required column
- invalid date
- invalid numeric value
- missing Valve_ID reference
- missing routing
- missing machine type
- invalid alternate machine
- subcontract allowed but no approved vendor
- duplicate component_line_no within same Valve_ID
- formula-only cell without cached value where backend cannot recalculate

### 7.4 Performance Fixture

Performance fixture should represent typical V1 volume:

```text
50 to 100 valves
multiple components per valve
multiple routing operations per component
several machine types
multiple vendors
```

The fixture should include at least one overloaded machine, one underutilized machine, one assembly-risk valve, one subcontract recommendation, and one flow blocker.

## 8. Test Naming and Traceability

Test IDs should follow this pattern:

```text
<AREA>-<TYPE>-<NUMBER>
```

Examples:

```text
IMPORT-UNIT-001
FORMULA-UNIT-006
PLAN-INT-003
API-CONTRACT-004
EXPORT-INT-002
UX-MANUAL-005
```

Each automated test should trace to at least one source:

- requirement section
- formula section
- data model table
- implementation story
- API endpoint

## 9. Coverage Matrix

| Area | Unit | Data Model | Integration | API | Frontend | Export | Performance | Manual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Settings and health | Yes | No | Yes | Yes | Yes | No | No | No |
| Excel upload | Yes | Yes | Yes | Yes | Yes | No | Yes | Yes |
| Workbook validation | Yes | Yes | Yes | Yes | Yes | No | Yes | Yes |
| Canonical promotion | Yes | Yes | Yes | Yes | No | No | No | No |
| PlanningRun and snapshot | Yes | Yes | Yes | Yes | Yes | No | No | Yes |
| Readiness and assembly risk | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes |
| Priority score | Yes | No | Yes | Yes | Yes | Yes | No | Yes |
| Routing expansion | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes |
| Queue simulation | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Machine load | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Flow blockers | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes |
| Recommendations | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes |
| Planner overrides | Yes | Yes | Yes | Yes | Yes | No | No | Yes |
| Vendor load | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes |
| Throughput summary | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes |
| Exports | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Security and audit | Yes | Yes | Yes | Yes | Yes | No | No | Yes |

## 10. Unit Test Plan

### 10.1 Import and Normalization Unit Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| IMPORT-UNIT-001 | Normalize column casing | `Valve_ID`, `valve id`, and `valve_id` map to the same canonical field |
| IMPORT-UNIT-002 | Trim spaces and collapse repeated spaces | Canonical field matching succeeds |
| IMPORT-UNIT-003 | Normalize boolean values | Y/N and supported equivalents become true/false |
| IMPORT-UNIT-004 | Reject blank required boolean | Blocking validation issue |
| IMPORT-UNIT-005 | Parse valid dates | ISO date value is produced |
| IMPORT-UNIT-006 | Reject invalid date | Blocking validation issue |
| IMPORT-UNIT-007 | Parse valid numeric values | Numeric value is produced |
| IMPORT-UNIT-008 | Reject invalid numeric value | Blocking validation issue |
| IMPORT-UNIT-009 | Generate component_line_no | Blank Component_Line_No gets source-order sequence within Valve_ID |
| IMPORT-UNIT-010 | Detect duplicate component_line_no | Duplicate within Valve_ID creates blocking issue |

### 10.2 Formula Unit Tests

| Test ID | Formula Area | Required Assertions |
|---|---|---|
| FORMULA-UNIT-001 | Date confidence | Blank Ready_Date_Type is inferred correctly |
| FORMULA-UNIT-002 | Availability date | Ready vs not-ready behavior follows formula |
| FORMULA-UNIT-003 | Current ready flag | Fabrication rules produce expected current_ready_flag |
| FORMULA-UNIT-004 | Full kit | pending_required_count = 0 produces full_kit_flag |
| FORMULA-UNIT-005 | Near ready | pending_required_count 1 or 2 produces near_ready_flag |
| FORMULA-UNIT-006 | Assembly risk | Expected completion after Assembly_Date produces AT_RISK |
| FORMULA-UNIT-007 | Priority score | All score components are included with correct weights |
| FORMULA-UNIT-008 | Starvation | waiting_age_days >= 10 adds starvation uplift |
| FORMULA-UNIT-009 | Operation hours | Qty x Std_Total_Hrs is used |
| FORMULA-UNIT-010 | Setup/run fallback | Std_Total_Hrs is calculated from setup + run when allowed |
| FORMULA-UNIT-011 | Machine capacity | Active machines aggregate by Machine_Type |
| FORMULA-UNIT-012 | Processing time | operation_hours / machine_type_capacity_hours_per_day |
| FORMULA-UNIT-013 | Queue wait | Scheduled start respects arrival and machine availability |
| FORMULA-UNIT-014 | Operation completion | internal_completion_date uses ceil offset rule |
| FORMULA-UNIT-015 | Overload | load_days > buffer_days sets overload_flag |
| FORMULA-UNIT-016 | Underutilization | load_days < 0.5 x buffer_days sets underutilized_flag |
| FORMULA-UNIT-017 | Extreme delay | internal_wait_days > 2 x buffer_days creates EXTREME_DELAY |
| FORMULA-UNIT-018 | Alternate machine | Alternate load after assignment within buffer creates USE_ALTERNATE |
| FORMULA-UNIT-019 | Vendor comparison | vendor_completion_offset_days < internal_completion_offset_days creates vendor gain |
| FORMULA-UNIT-020 | Vendor selection | Vendor sorting follows lead time, reliability, capacity, name |
| FORMULA-UNIT-021 | Batch subcontract | Candidate count >= 2 creates batch opportunity |
| FORMULA-UNIT-022 | Same-day batch risk | same_day_arrival_load_days > 1.0 creates BATCH_RISK |
| FORMULA-UNIT-023 | Flow gap | flow_gap_days > 2 creates FLOW_GAP |
| FORMULA-UNIT-024 | Valve flow imbalance | valve_flow_gap_days > 2 creates VALVE_FLOW_IMBALANCE |
| FORMULA-UNIT-025 | Vendor overload | recommended jobs >= capacity limit sets selected_vendor_overloaded_flag |
| FORMULA-UNIT-026 | Throughput target | 7-day target is 2.5 Cr and 14-day target is 5.0 Cr |
| FORMULA-UNIT-027 | Throughput gap | planned value below target creates throughput_gap_cr |
| FORMULA-UNIT-028 | Recommendation order | Type assignment follows documented priority order |
| FORMULA-UNIT-029 | Flow blocker severity | Blocker severity matches default mapping |
| FORMULA-UNIT-030 | Override save behavior | Override save does not mutate planned operations, machine load, throughput, or recommendations except affected status |

### 10.3 Export Unit Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| EXPORT-UNIT-001 | Export_Info metadata | Workbook includes PlanningRun ID, upload filename, start date, horizon, generated timestamp, user |
| EXPORT-UNIT-002 | Sheet naming | Sheet names match data model requirements |
| EXPORT-UNIT-003 | Column naming | Required columns are present in correct order |
| EXPORT-UNIT-004 | No Excel formulas for core calculations | Exported calculation values are stored values, not workbook formulas |

## 11. Data Model Test Plan

### 11.1 Migration Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| DB-MIG-001 | Apply migrations to empty SQLite database | All tables are created |
| DB-MIG-002 | Re-run migration command | Database remains valid under migration tool |
| DB-MIG-003 | Foreign key enforcement | Invalid FK insert fails with foreign keys enabled |
| DB-MIG-004 | Enum CHECK constraints where implemented | Invalid enum value is rejected |
| DB-MIG-005 | Boolean constraints where implemented | Invalid boolean value is rejected |

### 11.2 Relationship and Constraint Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| DB-CON-001 | Duplicate Valve_ID in same PlanningRun | Unique constraint or validation failure |
| DB-CON-002 | Same Valve_ID in different PlanningRun | Allowed |
| DB-CON-003 | Duplicate component_line_no in same valve/run | Blocking validation or constraint failure |
| DB-CON-004 | Same component name with different component_line_no | Allowed |
| DB-CON-005 | Planned operation references PlanningRun | FK relationship valid |
| DB-CON-006 | Recommendation references planned operation where available | FK relationship valid |
| DB-CON-007 | Planner override references user | FK relationship valid |
| DB-CON-008 | Report export references PlanningRun and user | FK relationship valid |

## 12. Integration Test Plan

### 12.1 Upload to Canonical Import

| Test ID | Scenario | Expected Result |
|---|---|---|
| IMPORT-INT-001 | Upload valid workbook | UploadBatch and RawUploadArtifact records created |
| IMPORT-INT-002 | Parse valid workbook | Staging rows created for all required sheets |
| IMPORT-INT-003 | Validate valid workbook | No blocking validation issues |
| IMPORT-INT-004 | Promote valid workbook | Canonical tables populated |
| IMPORT-INT-005 | Upload workbook with missing sheet | Blocking validation issue and no promotion |
| IMPORT-INT-006 | Upload workbook with warning-only vendor issue | Promotion allowed, warning remains visible |

### 12.2 PlanningRun Calculation

| Test ID | Scenario | Expected Result |
|---|---|---|
| PLAN-INT-001 | Create PlanningRun from promoted data | PlanningRun and PlanningSnapshot persisted |
| PLAN-INT-002 | Calculate PlanningRun | Calculated output tables are populated |
| PLAN-INT-003 | Recalculate same PlanningRun | Results are deterministic for same inputs |
| PLAN-INT-004 | Calculation failure | PlanningRun status becomes FAILED and error is visible |
| PLAN-INT-005 | Missing machine in calculation path | MISSING_MACHINE blocker is produced and affected load is handled per rules |

### 12.3 Recommendation and Override Flow

| Test ID | Scenario | Expected Result |
|---|---|---|
| REC-INT-001 | Primary overloaded and alternate feasible | USE_ALTERNATE is generated before subcontract |
| REC-INT-002 | Vendor faster and approved | SUBCONTRACT recommendation is generated |
| REC-INT-003 | No approved vendor | VENDOR_UNAVAILABLE or NO_FEASIBLE_OPTION path is used |
| REC-INT-004 | Batch subcontract opportunity | BATCH_SUBCONTRACT_OPPORTUNITY is generated |
| OVERRIDE-INT-001 | Create override with reason | PlannerOverride created and recommendation status updated |
| OVERRIDE-INT-002 | Create override without reason | API rejects request |
| OVERRIDE-INT-003 | Override does not recalculate | PlannedOperation, MachineLoadSummary, and ThroughputSummary values remain unchanged |

### 12.4 Export Integration

| Test ID | Scenario | Expected Result |
|---|---|---|
| EXPORT-INT-001 | Generate Machine Load Report | XLSX created with Export_Info and Machine_Load sheet |
| EXPORT-INT-002 | Generate Subcontract Plan | XLSX created with subcontract recommendation rows |
| EXPORT-INT-003 | Generate Valve Readiness Report | XLSX created with readiness and assembly-risk fields |
| EXPORT-INT-004 | Generate Flow Blocker Report | XLSX created with blocker severity, cause, and action |
| EXPORT-INT-005 | Generate Daily Execution Plan | XLSX created with queue and action fields |
| EXPORT-INT-006 | Export unavailable PlanningRun | API returns structured error |

## 13. API Test Plan

API tests must validate status codes, response schemas, error schemas, pagination, sorting, filtering, and database side effects.

### 13.1 Core API Contract Tests

| Test ID | Endpoint Area | Required Assertions |
|---|---|---|
| API-CONTRACT-001 | Health | Returns success and basic app status |
| API-CONTRACT-002 | Upload | Accepts `.xlsx`, rejects unsupported formats |
| API-CONTRACT-003 | Validation issues | Returns issues grouped by severity, sheet, row |
| API-CONTRACT-004 | PlanningRun create | Requires valid upload and valid horizon |
| API-CONTRACT-005 | PlanningRun calculate | Updates status and persists outputs |
| API-CONTRACT-006 | Home dashboard | Returns summary counts from persisted outputs |
| API-CONTRACT-007 | Incoming load | Supports pagination and filters |
| API-CONTRACT-008 | Machine load | Returns load, buffer, overload, underutilization |
| API-CONTRACT-009 | Machine queue | Returns operation rows for selected Machine_Type |
| API-CONTRACT-010 | Valve readiness | Returns readiness and assembly-risk fields |
| API-CONTRACT-011 | Assembly risk | Uses `/assembly-risk` route and assembly-risk language |
| API-CONTRACT-012 | Recommendations | Returns explanations, reason codes, numeric fields |
| API-CONTRACT-013 | Flow blockers | Returns severity, cause, and recommended action |
| API-CONTRACT-014 | Vendor load | Returns current-run vendor load and limitation-ready fields |
| API-CONTRACT-015 | Throughput | Returns horizon-scaled target, planned value, gap, risk |
| API-CONTRACT-016 | Planner overrides | Requires reason and stores append-only record |
| API-CONTRACT-017 | Exports | Creates report_export record and downloadable file |

### 13.2 Error Response Tests

| Test ID | Error Category | Expected Result |
|---|---|---|
| API-ERROR-001 | INVALID_FILE_TYPE | Structured error with clear message |
| API-ERROR-002 | WORKBOOK_PARSE_FAILED | Structured error with parse context where possible |
| API-ERROR-003 | VALIDATION_FAILED | Structured error when blocking validation prevents planning |
| API-ERROR-004 | PLANNING_RUN_NOT_FOUND | Structured not-found response |
| API-ERROR-005 | CALCULATION_FAILED | PlanningRun status and error message persisted |
| API-ERROR-006 | EXPORT_FAILED | Report export failure is visible and logged |
| API-ERROR-007 | OVERRIDE_REQUIRES_REASON | Override without reason is rejected |

## 14. Frontend and UX Test Plan

Frontend tests should verify behavior and rendering, not business formulas.

### 14.1 Automated Frontend Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| UX-AUTO-001 | App loads with backend available | Main shell and navigation render |
| UX-AUTO-002 | Backend unavailable | Friendly connection error renders |
| UX-AUTO-003 | Upload screen | File input, validation summary, and run action states render |
| UX-AUTO-004 | Home dashboard | Summary tiles render from API fixture |
| UX-AUTO-005 | Machine load table | OVERLOADED and UNDERUTILIZED states are visually distinct |
| UX-AUTO-006 | Queue detail | Aggregated Machine_Type warning is visible |
| UX-AUTO-007 | Recommendation explanation | Numeric explanation fields render |
| UX-AUTO-008 | Override dialog | Reason is mandatory |
| UX-AUTO-009 | Vendor dashboard | Vendor limitation warning is visible |
| UX-AUTO-010 | Assembly Risk view | UI uses Assembly Risk label |

### 14.2 Manual UX Acceptance Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| UX-MANUAL-001 | Planner uploads valid workbook | Planner reaches dashboard without developer help |
| UX-MANUAL-002 | Planner sees blocking validation issues | Planner understands what must be fixed in Excel |
| UX-MANUAL-003 | Planner investigates overloaded machine | Planner can drill from machine summary to queue detail |
| UX-MANUAL-004 | Planner reviews subcontract recommendation | Planner can see why vendor is recommended |
| UX-MANUAL-005 | Planner records override | Planner can record decision with reason |
| UX-MANUAL-006 | Management reviews assembly risk | Management can identify valves likely to miss assembly date |
| UX-MANUAL-007 | HOD reviews machine-type limitation | HOD sees that queue is aggregated by Machine_Type |
| UX-MANUAL-008 | Planner exports daily plan | Planner can open exported workbook and understand it |

## 15. Performance Test Plan

Performance tests must use a V1-volume workbook or generated equivalent.

| Test ID | Scenario | Target |
|---|---|---|
| PERF-001 | Upload validation for V1 workbook size | Completes under 10 seconds |
| PERF-002 | Planning calculations for 50 to 100 valves | Completes under 3 seconds after upload/promotion |
| PERF-003 | Dashboard API response for typical table | Returns under 1 second |
| PERF-004 | Export generation for first usable build report | Completes under 10 seconds |
| PERF-005 | Paginated table endpoint | Response time remains stable with pagination |

Performance test results should record:

- dataset name
- valve count
- component count
- planned operation count
- machine type count
- vendor count
- elapsed time
- pass/fail

## 16. Security, Audit, and Data Protection Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| SEC-001 | Unsupported upload file | Rejected before parsing |
| SEC-002 | Path traversal filename | Stored safely under configured upload directory |
| SEC-003 | Logs on upload/calculation/export | Logs do not include workbook contents or sensitive values |
| AUDIT-001 | Upload audit | UploadBatch includes user and timestamp |
| AUDIT-002 | PlanningRun audit | PlanningRun includes creator and timestamps |
| AUDIT-003 | Override audit | Override includes user, timestamp, original recommendation, decision, reason |
| AUDIT-004 | Export audit | ReportExport includes user, timestamp, type, file path |
| AUDIT-005 | Raw artifact traceability | Upload can be traced to raw artifact and generated planning run |

## 17. Release Acceptance Tests

These tests map to PRD release criteria.

| Test ID | Release Criterion | Evidence Required |
|---|---|---|
| REL-001 | Excel import works end to end | Golden workbook test passes |
| REL-002 | Validation issues are persisted and visible | Negative workbook tests and UI validation screen |
| REL-003 | PlanningRun and PlanningSnapshot are persisted | Integration test and database assertions |
| REL-004 | Formulas are implemented and tested | Formula unit test suite passes |
| REL-005 | Database schema is implemented through migrations | Migration tests pass |
| REL-006 | User flows are usable end to end | Manual UX acceptance tests pass |
| REL-007 | Dashboards load from persisted records | API and frontend dashboard tests pass |
| REL-008 | Planner overrides are append-only and auditable | Override integration and audit tests pass |
| REL-009 | Excel exports are generated from database records | Export tests pass |
| REL-010 | Golden workbook test passes | CI or local release run evidence |

## 18. Milestone Test Gates

| Milestone | Required Test Gate |
|---|---|
| M0 | Health, settings, migration smoke, frontend build/smoke |
| M1 | Import unit tests, validation tests, data model tests, upload-to-canonical integration |
| M2 | Formula unit tests, PlanningRun calculation integration, deterministic recalculation test |
| M3 | Recommendation tests, flow blocker tests, override tests |
| M4 | API contract tests, frontend smoke tests, core UX manual tests |
| M5 | Golden workbook, first export tests, performance tests, release acceptance dry run |
| M6 | Later V1 export tests, pilot validation, full release acceptance |

## 19. Defect Severity

| Severity | Meaning | Examples |
|---|---|---|
| S1 Critical | Blocks planning or creates materially wrong recommendations | Wrong queue wait, wrong subcontract decision, data loss, failed import of valid workbook |
| S2 High | Major workflow broken or important output missing | Dashboard unavailable, export missing required columns, override not auditable |
| S3 Medium | Workaround exists but behavior is incorrect or confusing | Warning text missing, sort order wrong, filter issue |
| S4 Low | Cosmetic or minor usability issue | Label spacing, minor copy issue |

S1 and S2 defects must be resolved before pilot unless explicitly accepted by product owner.

## 20. Test Reporting

Each test run should record:

- date and time
- code version or commit when available
- database migration version
- test dataset
- test command or manual scenario
- pass/fail count
- failed test IDs
- generated artifacts, such as export files or screenshots
- known exceptions

## 21. Regression Policy

Run the relevant regression set whenever these areas change:

| Changed Area | Required Regression |
|---|---|
| Excel parsing or validation | Import unit tests, negative workbook tests, golden workbook |
| Database schema | Migration tests, relationship tests, integration tests |
| Business formulas | Full formula unit suite, planning integration, golden workbook |
| Queue simulation | Queue tests, machine load tests, recommendation tests, performance test |
| Recommendation logic | Recommendation tests, override tests, export tests |
| API schemas | API contract tests and frontend integration fixtures |
| Export code | Export unit/integration tests and workbook openability check |
| UI dashboard code | Frontend tests and manual UX smoke tests |

## 22. Out of Scope for V1 Testing

V1 testing does not need to cover:

- live ERP integration
- live machine connectivity
- barcode workflows
- purchase order generation
- advanced optimizer comparison
- exact Machine_ID-level finite scheduling
- high-concurrency enterprise load testing
- native mobile application testing

## 23. Immediate Test Implementation Order

Recommended order:

1. Create test harness and smoke tests before scaffold behavior grows.
2. Write data model and migration tests before implementing migrations.
3. Write import normalization and validation unit tests before importer behavior.
4. Write golden workbook upload and staging test before broad import implementation.
5. Write formula unit tests using small fixtures before each formula module.
6. Write PlanningRun calculation integration tests before output persistence logic.
7. Write recommendation and override tests before recommendation services.
8. Write API contract tests before frontend depends on endpoint shapes.
9. Write export tests before export service behavior.
10. Add frontend smoke and manual UX tests before UI polish.
11. Add performance tests before first usable build signoff.
12. Run release acceptance test suite before pilot.
