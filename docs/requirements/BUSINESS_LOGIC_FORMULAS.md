# Business Logic and Formula Reference: Machine Shop Planning Software V1

## 1. Document Control

| Field | Value |
|---|---|
| Product | Machine Shop Planning Software |
| Document | Business Logic and Formula Reference |
| Version | V1 baseline |
| Date | 2026-04-19 |
| Status | Draft for implementation |
| Companion documents | PRD.md, TECHNICAL_REQUIREMENTS.md, DATA_MODEL_REQUIREMENTS.md, USER_EXPERIENCE.md |

## 2. Purpose

This document is the implementation reference for V1 business logic formulas.

It is the authoritative home for deterministic planning rules so backend implementation, tests, and future maintenance can use the same formula definitions.

The backend must own these calculations. The frontend must display stored outputs and must not reimplement these formulas.

## 3. Calculation Scope

The V1 calculation engine must calculate:

- planning horizon inclusion
- component readiness
- valve readiness
- assembly risk
- priority score
- routing expansion
- operation hours
- machine capacity
- queue wait and completion
- machine load
- overload and underutilization
- alternate machine feasibility
- subcontract feasibility
- subcontract batch opportunity
- same-day batch risk
- flow gap
- valve flow imbalance
- vendor load
- flow blockers
- throughput check
- final recommendations

## 4. Global Constants and Defaults

### 4.1 Planning Defaults

```text
default_planning_horizon_days = 7
allowed_planning_horizon_days = [7, 14]
default_planning_start_date = upload_date
```

User may override:

```text
planning_start_date
planning_horizon_days
```

### 4.2 Throughput Target

```text
default_target_throughput_per_7_days_cr = 2.5
```

V1 may store this as:

```text
target_throughput_per_7_days_cr
```

The comparison target scales with selected planning horizon:

```text
7-day horizon target = 2.5 Cr
14-day horizon target = 5.0 Cr
```

### 4.3 Flow Gap Limit

```text
flow_gap_limit_days = 2
```

### 4.4 Batch Risk Threshold

```text
same_day_batch_risk_threshold_days = 1.0
```

### 4.5 Extreme Delay Multiplier

```text
extreme_delay_multiplier = 2
```

### 4.6 Underutilization Multiplier

```text
underutilization_multiplier = 0.5
```

### 4.7 Priority Starvation Threshold

```text
starvation_waiting_age_days = 10
starvation_uplift_points = 500
```

### 4.8 Default Machine Buffer Days

These are defaults. Use `Machine_Master.Buffer_Days` from the imported workbook when available.

| Machine Type | Default Buffer Days |
|---|---:|
| HBM | 4 |
| VTL | 3 |
| Lathe | 2 |
| Drill | 2 |
| Milling | 2 |
| EDM | 2 |
| Finishing | 2 |

## 5. Unit and Date Rules

### 5.1 Units

```text
date unit = calendar day
duration unit = decimal day
hours unit = decimal hour
value unit = INR Cr
```

### 5.2 Hour-to-Day Conversion

```text
1 machine-type day = machine_type_capacity_hours_per_day
```

### 5.3 Date Offset Rule

All offset-day calculations are relative to:

```text
planning_start_date
```

### 5.4 Completion Date Rounding

All completion dates must use `ceil()`:

```text
completion_date = planning_start_date + ceil(completion_offset_days)
```

Do not use floor or normal rounding. `ceil()` prevents optimistic completion dates when a job consumes a partial day.

### 5.5 Display Rounding

Stored decimal values may retain precision.

Display decimal day values as:

```text
round(value, 2)
```

## 6. Input Normalization Rules

### 6.1 Boolean Normalization

Treat these as true:

```text
Y
YES
TRUE
1
```

Treat these as false:

```text
N
NO
FALSE
0
blank only when field is optional
```

Required boolean fields must not be blank.

### 6.2 Date Confidence

Allowed values:

```text
CONFIRMED
EXPECTED
TENTATIVE
```

Formula:

```text
if Ready_Date_Type is supplied:
  date_confidence = Ready_Date_Type
else if Fabrication_Complete = Y or Fabrication_Required = N:
  date_confidence = CONFIRMED
else:
  date_confidence = EXPECTED
```

### 6.3 Component Identity

Every component status row must have a stable line identity inside its valve.

```text
component_line_no =
  imported Component_Line_No if supplied
  else sequential number assigned by source row order within Valve_ID
```

The importer must preserve `component_line_no` through incoming load, planned operations, recommendations, blockers, and exports.

Repeated component names are allowed when their `component_line_no` values differ.

## 7. Planning Horizon Formulas

### 7.1 Horizon End Date

```text
planning_end_date = planning_start_date + planning_horizon_days
```

### 7.2 Component Availability Date

```text
if Fabrication_Required = N:
  availability_date = max(
    planning_start_date,
    Expected_Ready_Date if present else planning_start_date
  )

if Fabrication_Required = Y and Fabrication_Complete = Y:
  availability_date = max(
    planning_start_date,
    Expected_Ready_Date if present else planning_start_date
  )

if Fabrication_Required = Y and Fabrication_Complete = N:
  availability_date = Expected_Ready_Date
```

### 7.3 Horizon Inclusion

```text
in_horizon_flag =
  availability_date >= planning_start_date
  and availability_date <= planning_start_date + planning_horizon_days
```

## 8. Component Readiness Formulas

### 8.1 Current Ready Flag

```text
current_ready_flag =
  Fabrication_Required = N
  or (Fabrication_Required = Y and Fabrication_Complete = Y)
```

### 8.2 Planned Component Inclusion

A component is included in planning when:

```text
planned_component_flag =
  current_ready_flag = true
  or in_horizon_flag = true
```

If `Expected_Ready_Date` is missing for a not-ready component, exclude the component and create a validation issue.

## 9. Valve Readiness Formulas

### 9.1 Assembly Required Components

```text
critical_components =
  components where Critical = Y

if count(critical_components) > 0:
  assembly_required_components = critical_components
else:
  assembly_required_components = all components for the valve
```

### 9.2 Component Counts

```text
total_components =
  count(all Component_Status rows for Valve_ID)

required_components =
  count(assembly_required_components)

ready_components =
  count(all components where current_ready_flag = true)

ready_required_count =
  count(assembly_required_components where current_ready_flag = true)

pending_required_count =
  count(assembly_required_components where current_ready_flag = false)
```

### 9.3 Full Kit and Near Ready

```text
full_kit_flag =
  pending_required_count = 0

near_ready_flag =
  pending_required_count >= 1
  and pending_required_count <= 2
```

## 10. Valve Expected Completion and Assembly Risk

### 10.1 Component Expected Completion

For a component with routing:

```text
component_expected_completion_offset_days =
  internal_completion_offset_days of the component's last operation by Operation_No
```

For a component without routing:

```text
component_expected_completion_offset_days =
  availability_offset_days
```

### 10.2 Valve Expected Completion

```text
valve_expected_completion_offset_days =
  max(component_expected_completion_offset_days for assembly_required_components)

valve_expected_completion_date =
  planning_start_date + ceil(valve_expected_completion_offset_days)
```

If any required component cannot produce a completion offset:

```text
valve_expected_completion_date = null
readiness_status = DATA_INCOMPLETE
```

### 10.3 Assembly Delay

```text
otd_delay_days =
  max(0, valve_expected_completion_date - Assembly_Date)
```

### 10.4 Assembly Risk

```text
otd_risk_flag =
  valve_expected_completion_date > Assembly_Date
```

For V1, `otd_risk_flag` and `otd_delay_days` mean assembly-date risk. Dispatch risk is not calculated as a separate field in V1.

### 10.5 Valve Readiness Status

Assign exactly one status:

```text
if valve_expected_completion_date cannot be calculated:
  readiness_status = DATA_INCOMPLETE
else if otd_risk_flag = true:
  readiness_status = AT_RISK
else if full_kit_flag = true:
  readiness_status = READY
else if near_ready_flag = true:
  readiness_status = NEAR_READY
else:
  readiness_status = NOT_READY
```

## 11. Priority Score Formula

### 11.1 Assembly Urgency

```text
days_until_assembly =
  max(0, Assembly_Date - planning_start_date)

assembly_urgency_score =
  max(0, 30 - days_until_assembly) * 10
```

### 11.2 Kit Status Bonus

```text
full_kit_bonus =
  1000 if full_kit_flag = true else 0

near_ready_bonus =
  600 if near_ready_flag = true else 0
```

### 11.3 Critical Component Bonus

```text
critical_component_bonus =
  100 if Critical = Y else 0
```

### 11.4 Planner Priority Score

```text
planner_priority_score =
  300 if Priority = A
  150 if Priority = B
  50 if Priority = C
  0 if Priority is blank or any other value
```

Priority comparison must be case-insensitive.

### 11.5 Waiting Age

```text
waiting_age_days =
  max(0, planning_start_date - availability_date)

waiting_age_score =
  min(waiting_age_days, 10) * 5
```

### 11.6 Starvation Protection

```text
starvation_uplift =
  500 if waiting_age_days >= 10 else 0
```

### 11.7 Value Score

```text
value_score =
  min(Value_Cr * 100, 100)
```

### 11.8 Date Confidence Penalty

```text
date_confidence_penalty =
  0 if date_confidence = CONFIRMED
  25 if date_confidence = EXPECTED
  75 if date_confidence = TENTATIVE
```

### 11.9 Final Priority Score

```text
priority_score =
  full_kit_bonus
  + near_ready_bonus
  + assembly_urgency_score
  + critical_component_bonus
  + planner_priority_score
  + waiting_age_score
  + starvation_uplift
  + value_score
  - date_confidence_penalty
```

## 12. Sorting Rules

### 12.1 Default Operation Sort

All operation queue simulation must use this stable sort:

```text
sort operations by:
1. priority_score descending
2. Assembly_Date ascending
3. Dispatch_Date ascending
4. Value_Cr descending
5. Valve_ID ascending
6. Component ascending
7. Operation_No ascending
```

The result must be stored as:

```text
sort_sequence
```

### 12.2 Assembly Risk Sort

```text
sort assembly risk rows by:
1. otd_delay_days descending
2. Assembly_Date ascending
3. Value_Cr descending
```

### 12.3 Subcontract Recommendation Sort

```text
sort subcontract recommendations by:
1. vendor_gain_days descending
2. internal_wait_days descending
3. Assembly_Date ascending
4. priority_score descending
```

## 13. Routing Expansion Formulas

For every planned component:

```text
routing_rows =
  Routing_Master rows where Routing_Master.Component = Component_Status.Component
  sorted by Operation_No ascending
```

For each routing row:

```text
operation_hours =
  Qty * Std_Total_Hrs
```

Each generated planned operation must carry:

```text
Valve_ID
component_line_no
Component
Operation_No
```

If `Std_Total_Hrs` is missing but setup and run are present:

```text
Std_Total_Hrs =
  Std_Setup_Hrs + Std_Run_Hrs
```

If no routing exists for a component requiring machining:

```text
create FLOW_BLOCKER with blocker_type = MISSING_ROUTING
exclude component from operation load
```

## 14. Machine Capacity Formulas

### 14.1 Machine Effective Hours

```text
effective_hours_per_day(machine_id) =
  Hours_per_Day * Efficiency_Percent / 100
```

### 14.2 Machine Type Capacity

```text
machine_type_capacity_hours_per_day(machine_type) =
  sum(effective_hours_per_day for active machines with that Machine_Type)
```

If capacity is zero or missing:

```text
create FLOW_BLOCKER with blocker_type = MISSING_MACHINE
exclude affected operation from load
```

### 14.3 Processing Time

```text
processing_time_days =
  operation_hours / machine_type_capacity_hours_per_day(Machine_Type)
```

## 15. Queue Simulation Formulas

### 15.1 Initial State

For each Machine_Type:

```text
machine_available_offset_days[Machine_Type] = 0
```

### 15.2 Availability Offset

```text
availability_offset_days =
  max(0, availability_date - planning_start_date)
```

### 15.3 Previous Operation Completion

For the first operation of a component:

```text
previous_operation_completion_offset_days =
  availability_offset_days
```

For later operations:

```text
previous_operation_completion_offset_days =
  internal_completion_offset_days of the prior Operation_No
```

### 15.4 Operation Arrival

```text
operation_arrival_offset_days =
  max(availability_offset_days, previous_operation_completion_offset_days)

operation_arrival_date =
  planning_start_date + ceil(operation_arrival_offset_days)
```

### 15.5 Scheduled Start

```text
scheduled_start_offset_days =
  max(operation_arrival_offset_days, machine_available_offset_days[Machine_Type])
```

### 15.6 Internal Wait

```text
internal_wait_days =
  max(0, scheduled_start_offset_days - operation_arrival_offset_days)
```

### 15.7 Internal Completion

```text
internal_completion_days =
  internal_wait_days + processing_time_days

internal_completion_offset_days =
  operation_arrival_offset_days + internal_completion_days

internal_completion_date =
  planning_start_date + ceil(internal_completion_offset_days)
```

### 15.8 Machine Availability Update

After each operation:

```text
machine_available_offset_days[Machine_Type] =
  internal_completion_offset_days
```

### 15.9 Queue Simulation Limitation

The queue is an aggregate Machine_Type queue, not exact Machine_ID scheduling.

Sequential allocation is based on priority sorting. Large jobs sorted early may push later jobs. Planner must review queue outputs before execution.

## 16. Machine Load, Buffer, and Status

### 16.1 Total Operation Hours

```text
total_operation_hours_for_machine_type =
  sum(operation_hours for operations assigned to Machine_Type)
```

### 16.2 Load Days

```text
load_days =
  total_operation_hours_for_machine_type
  / machine_type_capacity_hours_per_day(Machine_Type)
```

### 16.3 Overload

```text
overload_flag =
  load_days > buffer_days

overload_days =
  max(0, load_days - buffer_days)
```

### 16.4 Spare Capacity

```text
spare_capacity_days =
  max(0, buffer_days - load_days)
```

### 16.5 Underutilization

```text
underutilized_flag =
  load_days < (0.5 * buffer_days)
```

### 16.6 Machine Status

```text
if capacity is missing or invalid:
  machine_status = DATA_INCOMPLETE
else if overload_flag = true:
  machine_status = OVERLOADED
else if underutilized_flag = true:
  machine_status = UNDERUTILIZED
else:
  machine_status = OK
```

### 16.7 Extreme Delay

```text
extreme_delay_flag =
  internal_wait_days > (2 * buffer_days for Machine_Type)
```

If true:

```text
recommendation_type = EXTREME_DELAY
create FLOW_BLOCKER with blocker_type = EXTREME_DELAY
```

## 17. Alternate Machine Feasibility

Evaluate alternate machine only when:

```text
primary overload_flag = true
```

### 17.1 Alternate Load After Assignment

```text
alternate_load_days_after_assignment =
  (current_total_operation_hours_for_Alt_Machine + operation_hours)
  / machine_type_capacity_hours_per_day(Alt_Machine)
```

### 17.2 Alternate Feasible

```text
alternate_feasible =
  Alt_Machine is not blank
  and Alt_Machine exists in Machine_Master
  and Alt_Machine has at least one active machine
  and alternate_load_days_after_assignment <= alternate_buffer_days
```

Where:

```text
alternate_buffer_days =
  Buffer_Days for Alt_Machine
```

If true:

```text
recommendation_type = USE_ALTERNATE
```

Alternate machine must be preferred before subcontracting.

## 18. Subcontract Evaluation Formulas

Evaluate subcontracting only when:

```text
primary overload_flag = true
and alternate_feasible = false
```

### 18.1 Vendor Process Required

```text
vendor_process_required =
  Vendor_Process if Vendor_Process is not blank
  else Machine_Type
```

### 18.2 Candidate Vendors

```text
candidate_vendors =
  vendors where
    Approved = Y
    and Primary_Process = vendor_process_required
```

### 18.3 Vendor Total Days

```text
vendor_total_days =
  Effective_Lead_Days if present and > 0
  else Turnaround_Days + Transport_Days_Total
```

### 18.4 Vendor Completion

```text
vendor_completion_offset_days =
  operation_arrival_offset_days + vendor_total_days

vendor_completion_date =
  planning_start_date + ceil(vendor_completion_offset_days)
```

### 18.5 Vendor Gain

```text
vendor_gain_days =
  internal_completion_offset_days - vendor_completion_offset_days
```

### 18.6 Vendor Sort

Choose suggested vendor by:

```text
sort candidate_vendors by:
1. vendor_total_days ascending
2. Reliability ascending, where A is best, then B, then C, blank last
3. Capacity_Rating descending, where High > Medium > Low > blank
4. Vendor_ID ascending
```

### 18.7 Subcontract Recommendation

```text
subcontract_recommended =
  Subcontract_Allowed = Y
  and count(candidate_vendors) > 0
  and selected_vendor_overloaded_flag = false
  and vendor_completion_offset_days < internal_completion_offset_days
```

If true:

```text
recommendation_type = SUBCONTRACT
recommended_action = Send component directly to vendor on receipt
```

If no approved vendor exists:

```text
recommendation_type = NO_FEASIBLE_OPTION
create FLOW_BLOCKER with blocker_type = VENDOR_UNAVAILABLE
```

## 19. Subcontract Batch Opportunity

### 19.1 Batch Key

```text
subcontract_batch_key =
  Machine_Type + vendor_process_required + selected Vendor_ID
```

### 19.2 Batch Candidate Count

```text
subcontract_batch_candidate_count =
  count(subcontract-eligible operations in the planning horizon
        with the same subcontract_batch_key)
```

### 19.3 Batch Opportunity Flag

```text
batch_subcontract_opportunity_flag =
  subcontract_batch_candidate_count >= 2
```

If true:

```text
recommendation_type = BATCH_SUBCONTRACT_OPPORTUNITY
```

V1 only flags the opportunity. It does not automatically group dispatches.

## 20. Same-Day Batch Risk

### 20.1 Same-Day Arrival Hours

```text
same_day_arrival_hours[date, Machine_Type] =
  sum(operation_hours for operations where
    operation_arrival_date = date
    and operation Machine_Type = Machine_Type)
```

### 20.2 Same-Day Arrival Load Days

```text
same_day_arrival_load_days =
  same_day_arrival_hours / machine_type_capacity_hours_per_day(Machine_Type)
```

### 20.3 Batch Risk

```text
batch_risk_flag =
  same_day_arrival_load_days > 1.0
```

If true:

```text
recommendation_type = BATCH_RISK
create FLOW_BLOCKER with blocker_type = BATCH_RISK
```

## 21. Flow Continuity Formulas

### 21.1 Operation Flow Gap

```text
flow_gap_days =
  next_operation_scheduled_start_offset_days
  - current_operation_internal_completion_offset_days
```

### 21.2 Flow Gap Blocker

```text
flow_blocker_flag =
  flow_gap_days > flow_gap_limit_days
```

Where:

```text
flow_gap_limit_days = 2
```

If true:

```text
create FLOW_BLOCKER with blocker_type = FLOW_GAP
```

## 22. Non-Full-Kit Throughput Conflict

### 22.1 Priority Load Days

```text
priority_load_days_for_machine_type =
  sum(operation_hours for Full Kit and Near Ready work on Machine_Type)
  / machine_type_capacity_hours_per_day(Machine_Type)
```

### 22.2 Non-Full-Kit Allowed

```text
non_full_kit_allowed =
  priority_load_days_for_machine_type <= buffer_days
  and spare_capacity_days >= processing_time_days of the non-full-kit operation
```

If false:

```text
recommendation_type = HOLD_FOR_PRIORITY_FLOW
```

## 23. Valve Flow Imbalance

### 23.1 Valve Flow Gap Days

```text
valve_flow_gap_days =
  max(component_expected_completion_offset_days for assembly_required_components)
  - min(component_expected_completion_offset_days for assembly_required_components)
```

### 23.2 Valve Flow Imbalance

```text
valve_flow_imbalance_flag =
  valve_flow_gap_days > 2
```

If true:

```text
create FLOW_BLOCKER with blocker_type = VALVE_FLOW_IMBALANCE
```

## 24. Vendor Load Formulas

V1 vendor load is based only on recommendations generated in the current planning run.

### 24.1 Vendor Capacity Limit

```text
max_recommended_jobs_per_horizon =
  1 if Capacity_Rating = Low
  3 if Capacity_Rating = Medium
  5 if Capacity_Rating = High
  1 if Capacity_Rating is blank or unknown
```

Capacity_Rating comparison is case-insensitive.

### 24.2 Vendor Recommended Jobs

```text
vendor_recommended_jobs =
  count(SUBCONTRACT recommendations assigned to Vendor_ID)
```

### 24.3 Vendor Overload

```text
selected_vendor_overloaded_flag =
  vendor_recommended_jobs >= max_recommended_jobs_per_horizon
```

If true:

```text
create FLOW_BLOCKER with blocker_type = VENDOR_OVERLOADED
```

### 24.4 Vendor Timing Limitation

V1 vendor load does not model arrival timing inside the horizon or external pending vendor load outside the current planning run. Planner must validate timing feasibility before dispatch.

## 25. Flow Blocker Rules

Create flow blockers for these conditions:

| Blocker Type | Trigger |
|---|---|
| MISSING_COMPONENT | Required component is not current-ready and availability_date is outside horizon |
| MISSING_ROUTING | Component requires machining but Routing_Master has no matching row |
| MISSING_MACHINE | Operation Machine_Type has no active machine capacity |
| MACHINE_OVERLOAD | load_days > buffer_days |
| BATCH_RISK | same_day_arrival_load_days > 1.0 |
| FLOW_GAP | flow_gap_days > 2 |
| VALVE_FLOW_IMBALANCE | valve_flow_gap_days > 2 |
| EXTREME_DELAY | internal_wait_days > 2 x buffer_days |
| VENDOR_UNAVAILABLE | subcontract allowed but no approved vendor exists |
| VENDOR_OVERLOADED | selected vendor has reached V1 capacity limit |

### 25.1 Flow Blocker Severity

Default severity mapping:

| Blocker Type | Severity |
|---|---|
| MISSING_COMPONENT | CRITICAL if related valve has assembly risk, else WARNING |
| MISSING_ROUTING | CRITICAL |
| MISSING_MACHINE | CRITICAL |
| MACHINE_OVERLOAD | WARNING |
| BATCH_RISK | INFO |
| FLOW_GAP | WARNING |
| VALVE_FLOW_IMBALANCE | WARNING |
| EXTREME_DELAY | CRITICAL |
| VENDOR_UNAVAILABLE | CRITICAL if no feasible option and related valve has assembly risk, else WARNING |
| VENDOR_OVERLOADED | WARNING |

## 26. Throughput Check

### 26.1 Target Throughput

```text
target_throughput_value_cr =
  target_throughput_per_7_days_cr * (planning_horizon_days / 7)
```

### 26.2 Planned Throughput

```text
planned_throughput_value_cr =
  sum(Value_Cr of valves where
    valve_expected_completion_date >= planning_start_date
    and valve_expected_completion_date <= planning_start_date + planning_horizon_days)
```

### 26.3 Throughput Gap

```text
throughput_gap_cr =
  max(0, target_throughput_value_cr - planned_throughput_value_cr)
```

### 26.4 Throughput Risk

```text
throughput_risk_flag =
  throughput_gap_cr > 0
```

## 27. Recommendation Type Assignment

The engine may create multiple recommendation or blocker records for one operation when multiple rules trigger. However, each planned operation should have one display `recommendation_status`.

Recommended display precedence:

```text
1. DATA_ERROR
2. EXTREME_DELAY
3. HOLD_FOR_PRIORITY_FLOW
4. SUBCONTRACT
5. USE_ALTERNATE
6. MACHINE_OVERLOAD
7. BATCH_SUBCONTRACT_OPPORTUNITY
8. BATCH_RISK
9. OK_INTERNAL
```

### 27.1 OK Internal

```text
OK_INTERNAL when:
  no blocking data error
  and no hold rule
  and no alternate recommendation
  and no subcontract recommendation
```

### 27.2 Machine Overload

```text
MACHINE_OVERLOAD when:
  load_days > buffer_days
```

### 27.3 No Feasible Option

```text
NO_FEASIBLE_OPTION when:
  primary overload_flag = true
  and alternate_feasible = false
  and subcontract_recommended = false
```

## 28. Validation Rule Outcomes

### 28.1 Missing Routing

```text
if component requires machining and no routing rows exist:
  validation severity = warning
  runtime flow blocker = MISSING_ROUTING
  exclude component from operation load
```

### 28.2 Missing Machine

```text
if Machine_Type does not exist in Machine_Master:
  validation severity = blocking for affected operation

if Machine_Type exists in Machine_Master
and machine_type_capacity_hours_per_day(Machine_Type) <= 0:
  import validation does not block PlanningRun creation
  runtime flow blocker = MISSING_MACHINE
  exclude affected operation from queue and load
```

### 28.3 Missing Vendor

```text
if Subcontract_Allowed = Y and no approved vendor exists:
  validation severity = warning
  subcontract recommendation = not created
  flow blocker = VENDOR_UNAVAILABLE when overload requires vendor
```

### 28.4 Missing Expected Ready Date

```text
if not-ready component has no Expected_Ready_Date:
  validation severity = blocking
  component excluded from planning

if ready component has no Expected_Ready_Date:
  validation severity = warning
  availability_date = planning_start_date
```

## 29. Recalculation Rules

Saving a planner override does not trigger recalculation in V1.

```text
override_saved:
  create planner_override record
  update affected recommendation status where applicable
  do not modify planned_operations
  do not modify machine_load_summaries
  do not modify throughput_summaries
  do not generate new recommendations
```

When recalculating a PlanningRun:

```text
1. Keep canonical input records unchanged.
2. Remove or supersede prior calculated output rows.
3. Recalculate formulas in this document.
4. Insert new calculated output rows.
5. Preserve planner overrides.
6. Mark affected overrides stale if their target operation or recommendation no longer exists.
```

Calculated output tables include:

- incoming_load_items
- valve_readiness_summaries
- planned_operations
- machine_load_summaries
- vendor_load_summaries
- throughput_summaries
- recommendations
- flow_blockers

## 30. Formula Test Cases

The implementation must include tests for these formula groups:

| Test area | Required assertions |
|---|---|
| Date confidence | blank Ready_Date_Type inferred correctly |
| Availability date | ready vs not-ready behavior |
| Full kit | pending_required_count = 0 produces full_kit_flag |
| Near ready | pending_required_count 1 or 2 produces near_ready_flag |
| Assembly risk | expected completion after Assembly_Date creates AT_RISK |
| Priority score | all score components included |
| Starvation | waiting_age_days >= 10 adds 500 |
| Operation hours | Qty x Std_Total_Hrs |
| Machine capacity | active machines aggregated by Machine_Type |
| Queue wait | scheduled start respects machine availability |
| Overload | load_days > buffer_days |
| Underutilization | load_days < 0.5 x buffer_days |
| Extreme delay | internal_wait_days > 2 x buffer_days |
| Alternate machine | alternate load after assignment within buffer |
| Vendor comparison | vendor_completion_offset_days < internal_completion_offset_days |
| Batch subcontract | candidate count >= 2 |
| Same-day batch risk | same_day_arrival_load_days > 1.0 |
| Flow gap | flow_gap_days > 2 |
| Valve flow imbalance | valve_flow_gap_days > 2 |
| Vendor overload | recommended jobs >= capacity limit |
| Throughput gap | planned value below target |

## 31. Implementation Notes

### 31.1 Backend Ownership

All formulas in this document must be implemented in backend services.

The frontend must not recompute these values.

### 31.2 Stable Sorting

All sorts must be stable and must include the specified tie-breakers.

### 31.3 Null Handling

If a required formula input is missing:

```text
do not guess
create DATA_ERROR or relevant flow blocker
exclude affected row from dependent calculation
```

### 31.4 Explainability

Recommendation explanations must include the numeric fields used in the decision.

Example for subcontract:

```text
Machine HBM is overloaded by 2.2 days.
Internal wait is 5.5 days.
Vendor total time is 4.0 days.
Vendor gain is 1.5 days.
Recommended action: send to vendor on receipt.
```
