# Product Requirements Document: Machine Shop Planning Software V1

## 1. Document Control

| Field | Value |
|---|---|
| Product | Machine Shop Planning Software |
| Version | V1 baseline |
| Date | 2026-04-19 |
| Status | Product baseline |
| Primary users | Production planner, machine shop HOD, management |
| Source inputs | docs/archive/requirements_legacy.md, machine_shop_sample_input.xlsx, machine shop scheduling rule book.xlsx, Scheduler logic sheet.xlsx, Screen wise requirement sheet for scheduling software.xlsx |

## 2. Document Set and Ownership

This PRD is the product-level source of truth. It defines the product problem, goals, scope, users, success criteria, and product decisions.

Detailed implementation rules live in companion documents to avoid duplicate logic and document drift.

| Document | Owns |
|---|---|
| README.md | Canonical requirements index and baseline usage guidance |
| PRD.md | Product intent, V1 scope, product decisions, success criteria, release criteria |
| USER_EXPERIENCE.md | User journeys, screen behavior, interaction patterns, UX copy, visual states |
| TECHNICAL_REQUIREMENTS.md | Architecture, technology stack, modules, APIs, runtime, testing categories |
| DATA_MODEL_REQUIREMENTS.md | SQLite schema, table relationships, indexes, Excel input schemas, Excel output schemas |
| BUSINESS_LOGIC_FORMULAS.md | Business formulas, planning rules, calculation sequencing, recommendation logic |

When a detail belongs to a companion document, that companion document is authoritative. The PRD must not duplicate detailed formulas, table schemas, or screen-by-screen behavior.

## 3. Executive Summary

Machine Shop Planning Software V1 is a rule-based planning and decision-support tool for a high-mix valve manufacturing machine shop.

The product helps planners look ahead 7 to 14 days, understand incoming component load from fabrication, calculate machine-wise capacity pressure, detect overload before it becomes a dispatch problem, and recommend alternate machine or subcontracting decisions.

V1 is not an ERP, MES, or advanced optimizer. It is a practical planning cockpit built on an open custom stack that turns validated planning data into clear alerts, reports, and explainable recommendations.

## 4. Problem Statement

The machine shop receives valve components from fabrication at different times. Planners need to know what is coming, whether internal machines can absorb the work, and whether some work should be routed to alternate machines or sent directly to vendors before queues build up.

Today, these decisions are difficult because:

- component readiness, routing, machine capacity, and vendor capability are spread across planning sheets
- machine overload is often visible only after work has already arrived
- subcontracting decisions may happen late
- valve completion depends on critical components being ready together
- management needs a simple view of load, assembly risk, blockers, and throughput pipeline

## 5. Product Goals

V1 must:

- support the operating throughput target for the machine shop
- predict machine load for the next 7 days by default, with an optional 14-day view
- identify machine overload before components physically arrive
- identify underutilized machine capacity
- identify flow blockers that need planner action
- show valve readiness, full-kit status, assembly risk, and throughput gap
- recommend alternate machine assignment when feasible
- recommend subcontracting when rule-based comparison shows it is beneficial
- flag subcontract batching opportunities for planner review
- allow planners to override recommendations with a recorded reason
- provide Excel import and Excel export while keeping the application database as the system of record

Throughput target comparison is horizon-scaled: INR 2.5 Cr for a 7-day horizon and INR 5.0 Cr for a 14-day horizon.

Detailed formulas for these goals are defined in BUSINESS_LOGIC_FORMULAS.md.

## 6. Non-Goals

V1 will not:

- replace ERP, order booking, inventory, or accounting systems
- replace MES or detailed shop-floor execution
- perform minute-by-minute finite-capacity scheduling
- auto-release jobs to production without planner approval
- optimize globally across all factory constraints
- perform AI-based prediction or optimization
- integrate live with machines, ERP, MES, vendor portals, or barcode systems
- generate subcontract purchase orders
- use Microsoft Power Platform, Dataverse, SharePoint Lists, or live shared Excel workbooks as the application backend
- treat Excel files as the live planning database

## 7. Users and Personas

### 7.1 Production Planner

Primary user. Uploads Excel input data, validates the plan, runs planning, reviews machine load and flow blockers, accepts or rejects recommendations, records overrides, and exports daily or weekly plans.

### 7.2 Machine Shop HOD

Reviews machine load, queue pressure, bottlenecks, alternate machine usage, subcontract recommendations, and flow continuity.

### 7.3 Management

Reviews throughput pipeline, active value, assembly risk, overload count, subcontract exposure, and major flow blockers.

Detailed user journeys and screen behavior are defined in USER_EXPERIENCE.md.

## 8. Product Principles

V1 must be:

- rule-based
- explainable
- planner-driven
- audit-friendly
- Excel-compatible for import/export
- database-backed for system-of-record behavior
- simple enough for a V1 pilot
- structured enough to support later scaling

The system recommends. The planner decides.

Correct machine-type classification is essential for valid planning results. Machines with materially different capability, size, accuracy, tooling, or process constraints must not be pooled under the same `Machine_Type`.

## 9. Data Ownership Strategy

Excel files are interfaces, not the system of record.

The V1 system of record is the application database.

Required product behavior:

- users import the agreed Excel workbook template
- uploaded Excel files are stored as raw artifacts
- validated rows are promoted into canonical database tables
- each successful import creates a PlanningRun and PlanningSnapshot
- planning calculations, recommendations, overrides, dashboards, and exports are generated from database records
- planner overrides are stored in the application database
- re-uploading a workbook creates a new planning history path and must not silently overwrite prior planning runs

The technical implementation of this strategy is defined in TECHNICAL_REQUIREMENTS.md and DATA_MODEL_REQUIREMENTS.md.

## 10. V1 Scope

### 10.1 In Scope

V1 includes:

- Excel upload and validation
- raw upload storage
- canonical database persistence after validation
- planning run and planning snapshot creation
- valve, component, routing, machine, and vendor import
- incoming load look-ahead
- valve readiness and assembly risk
- priority scoring
- routing expansion
- machine load calculation
- aggregate machine-type queue simulation
- overload, underutilization, batch risk, extreme delay, and flow blocker detection
- alternate machine recommendation
- subcontract recommendation
- subcontract batch opportunity flagging
- vendor load summary
- throughput check
- planner override logging
- dashboard views
- Excel exports and A3 planning output

V1 OTD risk is assembly-risk first. Dispatch-risk calculation is not a separate derived field in V1.

Detailed formulas are defined in BUSINESS_LOGIC_FORMULAS.md. Detailed data structures are defined in DATA_MODEL_REQUIREMENTS.md.

### 10.2 Out of Scope

V1 excludes:

- exact Machine_ID-level scheduling
- shift calendars beyond imported capacity assumptions
- live shop-floor status updates
- detailed operator planning
- material reservation
- purchase order generation
- automated vendor booking
- native mobile application
- high-concurrency enterprise deployment
- multi-site synchronization

## 11. Product Capabilities

V1 must provide the following capabilities at product level.

### 11.1 Excel Import and Validation

Users can upload the agreed Excel workbook. The system validates the workbook and clearly separates blocking errors from warnings.

Authoritative details:

- Excel schema: DATA_MODEL_REQUIREMENTS.md
- import and validation pipeline: TECHNICAL_REQUIREMENTS.md
- upload UX: USER_EXPERIENCE.md

### 11.2 Planning Run Creation

Users can create a PlanningRun from a validated upload, choose planning_start_date, select 7-day or 14-day horizon, and run calculations.

Authoritative details:

- planning run lifecycle: TECHNICAL_REQUIREMENTS.md
- database schema: DATA_MODEL_REQUIREMENTS.md
- formulas: BUSINESS_LOGIC_FORMULAS.md

### 11.3 Dashboard Triage

Users can see the most urgent planning issues first, including throughput gap, assembly risk, overloaded machines, flow blockers, subcontract recommendations, and batch risks.

Authoritative details:

- dashboard experience: USER_EXPERIENCE.md
- API and module requirements: TECHNICAL_REQUIREMENTS.md
- output tables: DATA_MODEL_REQUIREMENTS.md

### 11.4 Incoming Load View

Users can see components expected within the selected horizon, including readiness confidence and machine demand.

Authoritative details:

- UX behavior: USER_EXPERIENCE.md
- formulas and inclusion rules: BUSINESS_LOGIC_FORMULAS.md
- persisted output schema: DATA_MODEL_REQUIREMENTS.md

### 11.5 Machine Load and Queue Review

Users can review machine-type load, overload, underutilization, batch risk, and operation-level queue details.

Authoritative details:

- queue formulas: BUSINESS_LOGIC_FORMULAS.md
- UX behavior: USER_EXPERIENCE.md
- data model: DATA_MODEL_REQUIREMENTS.md

### 11.6 Valve Readiness and Assembly Risk

Users can see each valve's readiness status, expected completion, assembly-risk status, delay, and primary risk reason.

For V1, fields named OTD risk or OTD delay must be interpreted as assembly-date risk:

```text
assembly risk = expected completion date is later than Assembly_Date
```

Dispatch risk may be added later as a separate derived field.

Authoritative details:

- readiness and assembly-risk formulas: BUSINESS_LOGIC_FORMULAS.md
- UX behavior: USER_EXPERIENCE.md
- output schema: DATA_MODEL_REQUIREMENTS.md

### 11.7 Flow Blocker Review

Users can review blockers that require action, such as missing routing, missing machine, overload, batch risk, flow gap, valve flow imbalance, extreme delay, or vendor issues.

Authoritative details:

- blocker rules: BUSINESS_LOGIC_FORMULAS.md
- blocker UX: USER_EXPERIENCE.md
- blocker schema: DATA_MODEL_REQUIREMENTS.md

### 11.8 Recommendation Review

Users can review and act on alternate machine, subcontract, hold-for-flow, and no-feasible-option recommendations.

Authoritative details:

- recommendation logic: BUSINESS_LOGIC_FORMULAS.md
- recommendation UX: USER_EXPERIENCE.md
- recommendation schema: DATA_MODEL_REQUIREMENTS.md

### 11.9 Planner Overrides

Users can override recommendations with a required reason. Overrides are recorded for audit.

In V1, saving an override does not automatically recalculate queue state, machine load, throughput, or recommendations. The override records the planner decision and updates recommendation status only. Replanning with overrides is a later workflow.

Authoritative details:

- override UX: USER_EXPERIENCE.md
- override schema: DATA_MODEL_REQUIREMENTS.md
- API and audit requirements: TECHNICAL_REQUIREMENTS.md

### 11.10 Reports and Exports

Users can export planning outputs to Excel, including machine load, subcontract plan, valve readiness, flow blockers, daily execution plan, weekly planning report, and A3 planning output.

First usable build export priority:

1. Machine Load Report.
2. Subcontract Plan.
3. Valve Readiness Report.
4. Flow Blocker Report.
5. Daily Execution Plan.

Weekly Planning Report and A3 Planning Output remain in V1 scope, but may be implemented after the core workflow is stable.

Authoritative details:

- export schemas: DATA_MODEL_REQUIREMENTS.md
- export services: TECHNICAL_REQUIREMENTS.md
- report UX: USER_EXPERIENCE.md

## 12. Success Metrics

V1 is successful when:

- a planner can upload a valid workbook and reach the dashboard without developer help
- upload validation identifies blocking errors and warnings clearly
- planning calculations complete for the V1 workbook size within the agreed performance target
- machine load, valve readiness, flow blockers, recommendations, and throughput check are visible in the app
- each recommendation is explainable
- planner overrides are captured with user, timestamp, decision, and reason
- Excel exports can support daily and weekly planning conversations
- the sample workbook can be used as a golden import and planning test

Detailed performance targets and test responsibilities are defined in TECHNICAL_REQUIREMENTS.md.

## 13. Release Criteria

V1 can be considered ready for pilot when:

- Excel import works end to end
- validation issues are persisted and visible
- PlanningRun and PlanningSnapshot are persisted
- formulas in BUSINESS_LOGIC_FORMULAS.md are implemented and tested
- database schema in DATA_MODEL_REQUIREMENTS.md is implemented through migrations
- user flows in USER_EXPERIENCE.md are usable end to end
- dashboards load from persisted database records
- planner overrides are append-only and auditable
- Excel exports are generated from database records
- golden workbook test passes using machine_shop_sample_input.xlsx

## 14. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Excel template changes frequently | Import failures or wrong mappings | Version the template and validate columns strictly |
| Routing standards are inaccurate | Load calculation becomes misleading | Surface missing/zero hours and allow master corrections through new imports |
| Vendor lead times are unreliable | Bad subcontract recommendations | Keep recommendations explainable and require planner review |
| Planner expects exact scheduling | V1 may be misused | Clearly label V1 as planning support, not exact finite scheduling |
| SQLite deployment is used beyond intended scale | Concurrency or operational issues | Define V1 as small-team deployment; consider PostgreSQL later if needed |
| Duplicate logic across docs | Drift and implementation errors | Keep formulas, schemas, UX behavior, and technical details in their companion documents |

## 15. Open Product Questions

These product questions remain open and should be resolved before V1 release:

1. Should accepted subcontract recommendations appear in generated Excel exports by default?
2. What user roles are required in the first release: planner only, or planner plus HOD and management views?
3. For the later A3 export increment, is formatted Excel sufficient or is PDF/HTML print view also required?

## 16. Requirements Governance

To prevent drift:

- do not add detailed formulas to PRD.md; update BUSINESS_LOGIC_FORMULAS.md
- do not add detailed database schema to PRD.md; update DATA_MODEL_REQUIREMENTS.md
- do not add screen-by-screen UX behavior to PRD.md; update USER_EXPERIENCE.md
- do not add endpoint, module, runtime, or testing details to PRD.md; update TECHNICAL_REQUIREMENTS.md
- update this PRD only when product scope, product decisions, success criteria, risks, or release criteria change
