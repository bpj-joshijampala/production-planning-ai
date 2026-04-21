# User Experience Document: Machine Shop Planning Software V1

## 1. Document Control

| Field | Value |
|---|---|
| Product | Machine Shop Planning Software |
| Document | User Experience Document |
| Version | V1 baseline |
| Date | 2026-04-19 |
| Status | Draft for product/design baseline |
| Companion documents | PRD.md, TECHNICAL_REQUIREMENTS.md, DATA_MODEL_REQUIREMENTS.md, BUSINESS_LOGIC_FORMULAS.md |

## 2. UX Purpose

This document describes the step-by-step user experience for Machine Shop Planning Software V1.

The PRD defines what the system must do. The TRD defines how the system is built. This UX document defines how planners, HODs, and management should experience the product in daily use.

The product must feel like a practical planning cockpit, not a data-entry system. The user should always understand:

- what changed
- what is overloaded
- what is at risk
- what the system recommends
- why the system recommends it
- what action the planner can take
- what will be recorded for traceability

## 3. UX North Star

The main user experience goal:

```text
Within 5 minutes of uploading the latest Excel plan, the planner should know what requires action today.
```

The product should help the planner answer these questions in order:

1. Is the uploaded data usable?
2. Are we on track for the selected horizon?
3. Which machines are overloaded or underutilized?
4. Which valves are at risk?
5. What is blocking flow?
6. What should be shifted to an alternate machine?
7. What should be subcontracted?
8. What decisions need planner approval?
9. What can be shared as the daily or weekly plan?

## 4. Experience Principles

### 4.1 Show Decisions, Not Just Data

The user should not have to hunt through raw tables to infer the issue. Each screen should surface the decision implied by the data:

- keep internal
- move to alternate machine
- send to vendor
- hold for priority flow
- investigate data issue
- review manually

### 4.2 Explain Every Recommendation

Every recommendation must include a plain-language explanation backed by numbers.

Example:

```text
HBM load is 6.2 days against a 4.0 day buffer.
Internal completion is 7.1 days from arrival.
Vendor completion is 4.0 days from arrival.
Recommended action: send to vendor on receipt.
```

### 4.3 Preserve Planner Authority

The system recommends. The planner decides.

The UX must make it easy to:

- accept
- reject
- override
- add reason
- export plan

The user must never feel the software is silently taking control of production.

### 4.4 Keep Confidence Visible

Expected and tentative dates must be visually distinct from confirmed dates.

Date confidence affects trust. A TENTATIVE component should not look the same as a CONFIRMED component.

### 4.5 Make Flow Blockers Obvious

The most important UX object is the Flow Blocker.

A blocker is any issue that can stop valve completion, create machine congestion, or require planner action. The dashboard must surface blockers early, not bury them in detail screens.

### 4.6 Use Excel as a Bridge

Users may continue to think in Excel. The product should respect that by supporting Excel import/export, but the live planning experience must happen in the app.

## 5. Primary User Roles

### 5.1 Production Planner

Primary user.

Needs to:

- upload latest Excel plan
- validate data
- run planning calculation
- review dashboard
- investigate overloads
- review subcontract recommendations
- make overrides
- generate daily plan
- generate weekly plan

### 5.2 Machine Shop HOD

Review and decision support user.

Needs to:

- see machine load
- see bottlenecks
- review overloaded and underutilized machines
- review queue details
- discuss alternate routing and subcontracting with planner

### 5.3 Management

Summary visibility user.

Needs to:

- see throughput status
- see assembly risk
- see overloaded machines
- see subcontract exposure
- see flow blockers
- export or view weekly plan

## 6. Primary End-to-End Journey

### Step 1: User Opens the App

The user lands on the latest Planning Dashboard if a calculated PlanningRun exists.

If no PlanningRun exists, the user lands on Data Upload.

The first screen must make the current state clear:

| State | User sees |
|---|---|
| No upload exists | Upload latest Excel plan |
| Upload exists but validation failed | Validation failed, fix listed rows |
| Upload validated but not calculated | Run planning |
| Planning calculation failed | Calculation failed, review error |
| Planning calculated | Dashboard with action summary |

### Step 2: User Uploads Excel File

User action:

1. Opens Data Upload.
2. Selects `.xlsx` workbook.
3. Clicks Upload.

System response:

1. Shows upload progress.
2. Stores raw file.
3. Parses sheets.
4. Validates rows.
5. Shows validation result.

Successful upload message:

```text
Upload validated. Ready to create planning run.
```

Failed upload message:

```text
Upload has blocking errors. Fix the highlighted rows and upload again.
```

### Step 3: User Reviews Validation

The validation screen must separate:

- Blocking errors
- Warnings

Blocking errors prevent planning.

Warnings allow planning but remain visible.

Validation table columns:

| Column | Purpose |
|---|---|
| Severity | BLOCKING or WARNING |
| Sheet | Source sheet |
| Row | Source row |
| Field | Field with issue |
| Issue | Human-readable problem |
| Action | What the user should fix |

User decision:

- If blocking errors exist, user returns to Excel and fixes the input.
- If only warnings exist, user may continue.

### Step 4: User Creates Planning Run

User action:

1. Confirms planning_start_date.
2. Selects horizon: 7 days or 14 days.
3. Clicks Run Planning.

Default:

```text
planning_start_date = upload date
planning_horizon_days = 7
```

The user may override planning_start_date.

System response:

1. Creates PlanningRun.
2. Creates PlanningSnapshot.
3. Runs calculations.
4. Opens Home Dashboard.

### Step 5: User Reads the Home Dashboard

The Home Dashboard is the planner's morning control panel.

It must answer:

```text
What needs attention first?
```

Top summary tiles:

| Tile | Purpose |
|---|---|
| Active valves | Scope of current plan |
| Active value | Value in the system |
| Planned throughput | Expected value completion in selected horizon |
| Throughput gap | Gap against horizon-scaled target: INR 2.5 Cr for 7 days, INR 5.0 Cr for 14 days |
| Overloaded machines | Capacity pressure |
| Underutilized machines | Load-balancing opportunity |
| Flow blockers | Items needing action |
| Assembly risk valves | Valves likely to miss assembly date |
| Subcontract recommendations | Outsourcing decisions |
| Batch risks | Same-day arrival spikes |

Dashboard priority order:

1. Blocking data issues
2. Assembly risk
3. Machine overload
4. Extreme delay
5. Flow blockers
6. Subcontract recommendations
7. Underutilized machines
8. Throughput gap

The dashboard should not be a wall of charts. It should be a triage surface.

### Step 6: User Investigates Flow Blockers

If blockers exist, user opens Flow Blockers.

The Flow Blocker screen must group by blocker_type:

- MISSING_COMPONENT
- MISSING_ROUTING
- MISSING_MACHINE
- MACHINE_OVERLOAD
- BATCH_RISK
- FLOW_GAP
- VALVE_FLOW_IMBALANCE
- EXTREME_DELAY
- VENDOR_UNAVAILABLE
- VENDOR_OVERLOADED

Each row must show:

| Column | Purpose |
|---|---|
| Blocker type | What kind of problem |
| Valve | Affected valve |
| Component | Affected component |
| Operation | Affected operation |
| Cause | Why blocker exists |
| Recommended action | What planner should do next |
| Severity | INFO, WARNING, CRITICAL |

Example recommended actions:

```text
Add missing routing for Body.
Review HBM queue; load exceeds buffer by 2.1 days.
Review vendor capacity before accepting subcontract recommendation.
Delay non-full-kit work to protect full-kit valve flow.
```

### Step 7: User Reviews Machine Load

User opens Machine Load Dashboard.

Primary question:

```text
Which machine types are overloaded, underutilized, or at batch risk?
```

Machine Load table columns:

| Column | Purpose |
|---|---|
| Machine Type | HBM, VTL, Lathe, etc. |
| Total Hours | Workload in hours |
| Capacity Hours/Day | Effective daily capacity |
| Load Days | Workload converted to days |
| Buffer Days | Controlled WIP threshold |
| Overload Days | Days beyond buffer |
| Spare Capacity Days | Days before buffer is consumed |
| Status | OK, OVERLOADED, UNDERUTILIZED |
| Batch Risk | Same-day spike indicator |

Row interaction:

- Click a machine row to open Machine Queue Detail.

Visual priority:

- OVERLOADED rows appear first.
- EXTREME_DELAY operations are called out.
- UNDERUTILIZED rows are visible but less urgent than overloads.

### Step 8: User Opens Machine Queue Detail

The Machine Queue Detail explains the machine load.

Primary question:

```text
What is consuming this machine's capacity?
```

Table columns:

| Column | Purpose |
|---|---|
| Sequence | Queue order |
| Priority score | Why job appears here |
| Valve | Parent valve |
| Component | Component |
| Operation | Routing operation |
| Availability date | When job becomes available |
| Date confidence | CONFIRMED, EXPECTED, TENTATIVE |
| Operation hours | Standard load |
| Internal wait days | Queue wait |
| Processing days | Machine time |
| Completion date | Expected internal completion |
| Recommendation | Keep, alternate, vendor, hold |

The queue screen must make the approximation clear:

```text
Queue is priority-based and aggregated by machine type. Review before execution.
```

User actions:

- Filter to full-kit valves.
- Filter to extreme delay.
- Open subcontract recommendation.
- Change machine assignment.
- Add planner override.

### Step 9: User Reviews Subcontract Recommendations

Primary question:

```text
What should go outside before it reaches the internal queue?
```

Each recommendation must show:

| Field | Purpose |
|---|---|
| Valve | Business context |
| Component | Part to send |
| Operation | Process to subcontract |
| Machine Type | Internal bottleneck |
| Internal wait days | Why internal is slow |
| Internal completion days | Internal completion offset |
| Vendor total days | Vendor lead time |
| Vendor gain days | Time saved |
| Suggested vendor | Recommended vendor |
| Batch opportunity | Whether similar jobs can be grouped |
| Explanation | Plain-language reason |

Recommendation actions:

- Accept
- Reject
- Force in-house
- Force vendor
- Add reason

If the planner accepts:

```text
Decision saved. Include in subcontract plan.
```

If the planner rejects:

```text
Reason required.
```

Subcontract batching behavior:

- V1 flags batch opportunities.
- V1 does not automatically group vendor dispatches.
- Planner decides whether to group.

### Step 10: User Reviews Valve Readiness

Primary question:

```text
Which valves can realistically move toward assembly?
```

Valve Readiness columns:

| Column | Purpose |
|---|---|
| Valve | Valve identifier |
| Customer | Customer |
| Assembly date | Target assembly date |
| Dispatch date | Target dispatch |
| Total components | Scope |
| Ready components | Readiness progress |
| Critical ready | Full-kit basis |
| Status | READY, NEAR_READY, NOT_READY, AT_RISK |
| Expected completion | Calculated completion |
| Assembly delay days | Delay against assembly |
| Risk reason | Main blocker |

Row interaction:

- Click valve to open Component Status View.

### Step 11: User Opens Component Status View

Primary question:

```text
What exactly is stopping this valve?
```

Component Status columns:

| Column | Purpose |
|---|---|
| Component | Component name |
| Current location | Fabrication, stores, vendor, ready |
| Fabrication complete | Y/N |
| Critical | Y/N |
| Availability date | Date used in plan |
| Date confidence | CONFIRMED, EXPECTED, TENTATIVE |
| Next operation | Next machine/process |
| Internal wait days | Queue wait if routed |
| Status | Ready, pending, blocked |

The screen should make missing or tentative information visible.

### Step 12: User Reviews Assembly Risk

Primary question:

```text
Which valves may miss assembly date, and why?
```

V1 uses assembly-date risk as the OTD risk signal. The UI label should be `Assembly Risk` wherever space allows.

Assembly Risk columns:

| Column | Purpose |
|---|---|
| Valve | Valve identifier |
| Customer | Customer |
| Assembly date | Target date |
| Expected completion date | Calculated completion |
| Assembly delay days | Delay amount |
| Reason | Missing component, overload, vendor issue, data issue |
| Suggested action | Planner action |

Rows must be sorted by:

1. otd_delay_days descending
2. Assembly_Date ascending
3. Value_Cr descending

### Step 13: User Takes Planner Actions

Planner Actions are used when human judgement overrides the system.

Supported actions:

- Override priority
- Force in-house
- Force vendor
- Change machine assignment
- Accept subcontract recommendation
- Reject subcontract recommendation
- Add remarks

Every action requires:

- decision
- reason
- user
- timestamp

The action form should be short. Required reason examples:

```text
Customer escalation
Technical constraint
Vendor quality concern
Machine setup already planned
Material not physically available
Management instruction
```

After submission:

```text
Decision recorded.
```

### Step 14: User Opens Vendor Dashboard

Primary question:

```text
Are we overloading any vendor in this plan?
```

Vendor Dashboard columns:

| Column | Purpose |
|---|---|
| Vendor | Vendor name |
| Process | HBM, VTL, Lathe, etc. |
| Recommended jobs | Current-run recommendation count |
| Capacity limit | V1 limit by capacity rating |
| Status | OK or VENDOR_OVERLOADED |
| Notes | Reliability, remarks |

The screen must show this limitation:

```text
Vendor timing and external pending load are only partially modeled in V1. Confirm before dispatch.
```

### Step 15: User Reviews A3 Planning Output

The A3 Planning Output is the daily/weekly planning conversation view.

Primary question:

```text
What plan should we discuss and execute?
```

A3 view sections:

1. Throughput check
2. Machine-wise weekly plan
3. Daily execution plan
4. Flow blockers
5. Subcontract actions
6. Assembly risk valves
7. Planner overrides

The A3 view should be printable/exportable.

It should not require users to open every dashboard during a meeting.

### Step 16: User Exports Reports

User opens Reports.

Available exports:

First usable build:

- Machine Load Report
- Subcontract Plan
- Valve Readiness Report
- Flow Blocker Report
- Daily Execution Plan

Later V1 export increment:

- Weekly Planning Report
- A3 Planning Output

Each export must include:

- PlanningRun ID
- upload filename
- planning_start_date
- horizon
- generated timestamp
- generated by

Export success message:

```text
Export ready.
```

## 7. Main User Flows

### 7.1 Daily Planner Flow

```text
Open app
  -> Upload latest Excel
  -> Review validation
  -> Run planning
  -> Read dashboard
  -> Review blockers
  -> Review overloaded machines
  -> Review subcontract recommendations
  -> Apply overrides
  -> Export daily execution plan
```

### 7.2 HOD Review Flow

```text
Open latest calculated PlanningRun
  -> Review dashboard
  -> Open machine load
  -> Drill into overloaded machines
  -> Review queue detail
  -> Review alternate/vendor recommendations
  -> Review A3 planning output
```

### 7.3 Management Review Flow

```text
Open latest calculated PlanningRun
  -> Review throughput check
  -> Review assembly risk
  -> Review overloaded machines
  -> Review subcontract count
  -> Export weekly planning report
```

### 7.4 Data Correction Flow

```text
Upload Excel
  -> Validation fails
  -> User reviews blocking rows
  -> User fixes Excel source
  -> User re-uploads
  -> New UploadBatch is created
  -> Planning continues
```

## 8. Screen-by-Screen UX Requirements

### 8.1 Login

V1 login should be simple.

Fields:

- username
- password

Success:

- route to latest dashboard or upload screen

Failure:

```text
Username or password is incorrect.
```

### 8.2 Home Dashboard

Default route after login when a calculated PlanningRun exists.

Primary layout:

1. PlanningRun selector
2. Summary tiles
3. Critical alerts
4. Machine load snapshot
5. Assembly risk snapshot
6. Subcontract recommendation snapshot
7. Flow blocker snapshot

Empty state:

```text
No planning run yet. Upload the latest Excel plan to begin.
```

### 8.3 Data Upload

Must include:

- upload control
- selected file name
- upload status
- validation summary
- issue table
- create planning run action

Upload statuses:

- UPLOADED
- VALIDATION_FAILED
- VALIDATED
- PROMOTED
- CALCULATED

### 8.4 Incoming Load

Filters:

- horizon
- date
- customer
- valve type
- machine type
- date confidence

Default sort:

1. availability_date ascending
2. priority_score descending
3. Machine_Type ascending

### 8.5 Machine Load

Default sort:

1. OVERLOADED
2. EXTREME_DELAY present
3. BATCH_RISK present
4. load_days descending
5. UNDERUTILIZED

Primary chart:

- load_days vs buffer_days by Machine_Type

The chart should not replace the table; the table is the decision surface.

### 8.6 Machine Queue Detail

Entered from Machine Load.

Must show selected Machine_Type clearly.

Key controls:

- filter by status
- filter by date confidence
- filter by full-kit/near-ready
- filter by recommendation

### 8.7 Subcontract Recommendations

Default grouping:

1. Machine_Type
2. Vendor_Process
3. Suggested vendor

Default sort:

1. vendor_gain_days descending
2. internal_wait_days descending
3. Assembly_Date ascending
4. priority_score descending

### 8.8 Valve Readiness

Default grouping:

- AT_RISK
- NEAR_READY
- READY
- NOT_READY
- DATA_INCOMPLETE

Default sort:

1. status priority
2. Assembly_Date ascending
3. Value_Cr descending

### 8.9 Component Status

Entered from Valve Readiness.

Must show one valve at a time.

The user should not need to filter the whole component table manually to understand one valve.

### 8.10 Planner Action Log

Must be append-only in V1.

Default sort:

1. created_at descending

Must show stale/orphaned overrides if recalculation invalidates their target.

### 8.11 Reports

Reports screen must show:

- available report types
- latest generated report
- generated by
- generated time
- download action

## 9. Interaction Patterns

### 9.1 Drilldown Pattern

Use this pattern throughout:

```text
Summary tile -> filtered list -> row detail -> action
```

Examples:

```text
Overloaded machines -> Machine Load -> HBM queue -> subcontract action
Assembly risk -> Valve Readiness -> Component Status -> blocker action
Flow blockers -> blocker row -> related queue or valve detail
```

### 9.2 Explanation Pattern

Every recommendation detail must use this structure:

```text
Recommendation
Reason
Numbers used
Assumptions
Planner action
```

Example:

```text
Recommendation: Send Body / HBM Boring to vendor.
Reason: HBM exceeds buffer and vendor completion is earlier.
Numbers: internal wait 5.5 days, vendor total 4.0 days, gain 1.5 days.
Assumption: Vendor load timing is not modeled in V1.
Action: Accept, reject, or override.
```

### 9.3 Override Pattern

When user overrides:

1. User selects action.
2. System opens compact reason dialog.
3. User enters reason.
4. User confirms.
5. System records decision.
6. Affected recommendation status updates.

Reason is mandatory.

Saving an override does not recalculate the plan in V1. Machine load, queue order, throughput, and recommendations remain based on the current PlanningRun until a future replanning workflow is introduced.

## 10. States and Feedback

### 10.1 Loading States

Use specific loading text:

```text
Uploading file...
Validating workbook...
Creating planning run...
Calculating machine load...
Generating export...
```

Avoid generic:

```text
Loading...
```

### 10.2 Empty States

Empty states must tell the user what to do next.

Examples:

```text
No subcontract recommendations. Internal plan is within current subcontract rules.
No flow blockers found for this planning run.
No planning run yet. Upload the latest Excel plan to begin.
```

### 10.3 Error States

Errors must include:

- what failed
- why it failed if known
- what the user can do next

Example:

```text
Planning calculation failed.
Machine type HBM is missing from Machine_Master.
Fix the workbook and upload a new file.
```

### 10.4 Warning States

Warnings should allow continuation but remain visible.

Examples:

```text
Some dates are TENTATIVE. Review before confirming vendor actions.
Vendor timing and external pending load are only partially modeled in V1. Confirm before dispatch.
Queue is aggregated by machine type. Review before execution.
```

## 11. Visual Language

### 11.1 Status Colors

Use consistent status treatment:

| Status | Meaning |
|---|---|
| Green | OK, READY, CONFIRMED |
| Yellow | NEAR_READY, EXPECTED, warning |
| Red | OVERLOADED, AT_RISK, EXTREME_DELAY, blocking |
| Gray | NOT_READY, DATA_INCOMPLETE, inactive |

TENTATIVE should be visually distinct from EXPECTED. Use a warning treatment and clear label.

### 11.2 Numeric Emphasis

Important numeric fields should be easy to scan:

- load_days
- buffer_days
- overload_days
- internal_wait_days
- vendor_gain_days
- otd_delay_days
- throughput_gap_cr

### 11.3 Tables Before Decoration

This product is table-led. Charts support decisions but should not hide details.

Primary decision screens should use strong tables with:

- sticky headers
- sorting
- filtering
- clear status badges
- row click behavior
- export action where relevant

## 12. UX Copy Guidelines

Copy should be direct, operational, and calm.

Use:

```text
HBM is overloaded by 2.1 days.
Vendor completion is 1.5 days earlier.
Reason required before override.
Upload validated.
Export ready.
```

Avoid:

```text
Great news!
Oops!
Our intelligent engine has optimized your plan.
Click here to unlock insights.
```

The product should sound like a capable planning assistant, not a marketing page.

## 13. What V1 Must Not Feel Like

V1 must not feel like:

- a full ERP
- a black-box optimizer
- a spreadsheet clone
- a passive reporting dashboard
- a shop-floor execution system
- a tool that silently makes production decisions

V1 should feel like:

- a planning cockpit
- a bottleneck detector
- a flow blocker board
- a subcontract decision assistant
- a daily planning room

## 14. First-Use Experience

For the first usable build, the ideal experience is:

1. User opens app.
2. User sees upload prompt.
3. User uploads `machine_shop_sample_input.xlsx`.
4. App validates workbook.
5. User creates planning run.
6. App opens dashboard.
7. User clicks overloaded machine.
8. User sees queue detail.
9. User opens subcontract recommendation.
10. User accepts/rejects with reason.
11. User exports daily execution plan.

This first-use path should be tested end to end before adding secondary polish.

## 15. UX Acceptance Criteria

V1 UX is acceptable when:

- A new planner can upload a valid workbook and reach the dashboard without developer help.
- Validation errors tell the user exactly what to fix.
- Dashboard shows the most urgent planning problems first.
- Every recommendation has an explanation.
- Every override requires and records a reason.
- Machine load can be drilled into from summary to operation-level queue.
- Assembly risk can be drilled into from valve to component cause.
- Flow blockers are visible from the dashboard.
- A3 output can support a planning meeting without opening every screen.
- Excel import/export feels natural while the app remains the planning system of record.
