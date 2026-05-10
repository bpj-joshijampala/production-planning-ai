# Pilot Validation

This document is the M6-E5 pilot validation artifact. It records the sample workflow, manual HOD machine-load comparison, and management metrics expected from the committed golden workbook.

## Scope

Pilot validation uses:

```text
backend/tests/fixtures/machine_shop_sample_input.xlsx
```

Default pilot run settings:

| Field | Value |
|---|---|
| Planning start date | `2026-04-21` |
| Planning horizon | `7` days |
| Horizon end used for manual checks | `2026-04-28` |

Automated evidence:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_m6_pilot_validation.py
```

The automated pilot test proves upload, validation, planning, dashboard review, HOD machine-load comparison, recommendation action, action log, and V1 export generation/download.

## Planner Pilot Workflow

| Step | Expected result |
|---|---|
| Upload golden workbook | Upload status is `VALIDATED`; blocking and warning counts are `0` |
| Create PlanningRun | PlanningRun is created from the uploaded workbook |
| Calculate PlanningRun | PlanningRun status becomes `CALCULATED` |
| Review dashboard | Throughput, overload, subcontract, assembly risk, and blocker metrics match the table below |
| Review recommendations | Recommendation list includes explainable batch subcontract recommendations |
| Record planner action | Accepting a recommendation creates an append-only planner override with reason and user |
| Review action log | Action log shows the accepted decision as current, not stale |
| Generate exports | All V1 `.xlsx` exports can be generated and downloaded |

V1 exports checked during pilot validation:

| Report type | Expected workbook sheets |
|---|---|
| `MACHINE_LOAD` | `Export_Info`, `Machine_Load` |
| `SUBCONTRACT_PLAN` | `Export_Info`, `Subcontract_Plan` |
| `VALVE_READINESS` | `Export_Info`, `Valve_Readiness` |
| `FLOW_BLOCKER` | `Export_Info`, `Flow_Blockers` |
| `DAILY_EXECUTION` | `Export_Info`, `Daily_Execution` |
| `WEEKLY_PLANNING` | `Export_Info`, `Weekly_Summary`, `Machine_Load`, `Valve_Readiness`, `Flow_Blockers`, `Subcontract_Plan` |
| `A3_PLANNING` | `Export_Info`, `A3_Planning` |

## HOD Machine-Load Comparison

The HOD manual comparison is calculated directly from the workbook, not from app output.

Ready components within the 7-day horizon:

| Valve | Component | Ready date | Included? | Reason |
|---|---|---:|---|---|
| `V-100` | `Body` | `2026-04-21` | Yes | Fabrication complete and ready within horizon |
| `V-100` | `Seat` | `2026-04-21` | Yes | Fabrication complete and ready within horizon |
| `V-200` | `Bonnet` | `2026-04-21` | Yes | Fabrication complete and ready within horizon |
| `V-300` | `Disc` | `2026-04-30` | No | Fabrication incomplete and ready after `2026-04-28` |

Manual machine-load math:

| Machine type | Included operations | Total hours | Capacity hours/day | Load days | Buffer days | Expected status |
|---|---|---:|---:|---:|---:|---|
| `HBM` | Body roughing `8`, Seat prep `8`, Bonnet finish `8` | `24.0` | `8.0` | `3.0` | `1.0` | `OVERLOADED` |
| `VTL` | Body finish `4` | `4.0` | `8.0` | `0.5` | `3.0` | `UNDERUTILIZED` |

Expected comparison:

| Machine type | Overload days | Spare capacity days |
|---|---:|---:|
| `HBM` | `2.0` | `0.0` |
| `VTL` | `0.0` | `2.5` |

## Management Pilot Metrics

These are the management metrics captured from the dashboard for the golden workbook pilot run.

| Metric | Expected value |
|---|---:|
| Throughput gap | `0.75 Cr` |
| Overloaded machines | `1` |
| Subcontract recommendations | `3` |
| Assembly-risk valves | `1` |
| Flow blockers | `4` |

Additional dashboard context:

| Metric | Expected value |
|---|---:|
| Active valves | `3` |
| Planned throughput | `1.75 Cr` |
| Batch risks | `1` |

## Manual Signoff Notes

Use this table during an actual plant pilot run.

| Area | Reviewer | Pass/Fail | Notes |
|---|---|---|---|
| Upload and validation | Planner |  |  |
| Dashboard metrics | Management |  |  |
| Machine-load comparison | HOD |  |  |
| Recommendation explanation | Planner/HOD |  |  |
| Planner action and action log | Planner |  |  |
| Excel exports | Planner/Management |  |  |
| Backup before pilot reset or data refresh | Support |  |  |

Open discrepancies should be captured with:

- workbook name
- PlanningRun ID
- screenshot or exported workbook name
- expected value
- actual value
- reviewer decision
