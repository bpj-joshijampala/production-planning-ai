1. IMPLEMENTATION_PLAN.md - created at `docs/implementation/IMPLEMENTATION_PLAN.md`

This is the most important next document.

It should break the build into phases and tasks:

Phase 0: project setup
Phase 1: backend scaffold
Phase 2: SQLite schema and migrations
Phase 3: Excel import and validation
Phase 4: planning engine
Phase 5: APIs
Phase 6: React UI
Phase 7: exports
Phase 8: test hardening
Phase 9: pilot readiness
This helps avoid jumping randomly between UI, formulas, and database work.

2. TEST_PLAN.md - created at `docs/implementation/TEST_PLAN.md`; includes the TDD workflow and test-first gates

Because the planning logic is deterministic, we should define tests before implementation.

It should cover:

golden workbook test using machine_shop_sample_input.xlsx
formula unit tests
import validation tests
data model constraint tests
planning run integration tests
dashboard API tests
export tests
acceptance scenario tests from the PRD
This is especially important because small formula mistakes can create very confident but wrong recommendations.

3. API_SPEC.md

The technical requirements list the endpoints, but an API spec should define request/response payloads.

It should include:

upload API
validation issue response
create planning run request
dashboard response
machine load response
machine queue response
valve readiness response
subcontract recommendation response
flow blocker response
planner override request
export request/response
This will let backend and frontend work cleanly without guessing payload shapes.

Optional but useful later:

4. OPERATIONS_RUNBOOK.md

For deployment and maintenance:

how to start backend/frontend
where SQLite database lives
backup/restore steps
how to reset local dev data
where uploads/exports are stored
troubleshooting common failures
5. PILOT_FEEDBACK_PLAN.md

For factory pilot:

what planners should test
what screenshots/data to collect
what decisions to compare manually
what metrics to track
how to tune buffers and priority weights
