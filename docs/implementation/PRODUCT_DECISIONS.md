# Product Decisions

## M6-E1 A3 Export Format

Date: 2026-05-07

Decision: The V1 A3 Planning Output is a formatted `.xlsx` workbook generated from database records.

PDF and HTML print views are not required for V1 pilot readiness. They are deferred to post-V1 unless product review reopens the requirement.

Rationale:

- V1 requirements already require Excel-compatible exports.
- The A3 sheet can support the planning meeting inside the same export pipeline as the other reports.
- Keeping PDF/HTML out of V1 avoids adding a second rendering path before pilot validation.

## M6-E2 Role and Authentication Model

Date: 2026-05-07

Decision: V1 pilot uses the seeded default `dev.planner` account as the acting user. Local username/password login and user-management screens are deferred until after pilot validation.

First-release role behavior:

| Role | V1 access |
|---|---|
| PLANNER | Upload, create/calculate planning runs, view dashboards, record overrides, and export reports |
| HOD | View dashboards/queues/recommendations/action log and export reports |
| MANAGEMENT | View dashboards/queues/recommendations/action log and export reports |
| ADMIN | View operational data only until user/settings management screens are implemented |

Rationale:

- The first plant pilot needs auditable user ownership more than multi-user login.
- The seeded user keeps local deployment and smoke testing simple.
- HOD and management roles are still enforced in backend authorization so read/export behavior can be validated before login is added.
- ADMIN remains non-writer/non-exporter in V1 pilot because the required admin surfaces are not yet in scope.

Post-V1 backlog:

- Add local username/password login with password hashing.
- Add user/session management screens for ADMIN.
- Replace the seeded current-user lookup with login-backed session state once login exists.

## M6-E3 Stale Override and Recalculation Policy

Date: 2026-05-08

Decision: V1 keeps planner overrides as append-only audit decisions. Recalculation does not replay overrides into the planning engine.

Stale/orphaned override behavior:

| Scenario | V1 behavior |
|---|---|
| Override target still exists after recalculation | Override remains current in the action log |
| Override target no longer exists after recalculation | Override is marked stale/orphaned and remains visible in the action log |
| Planner wants the decision reflected in the recalculated plan | Planner reviews the stale action and records a fresh decision against the new recommendation or target |
| Dashboard warnings for affected entities | Deferred; V1 surfaces stale/orphaned decisions in the action log only |

Rationale:

- Replaying old decisions into newly generated recommendations would require stable semantic target matching, conflict handling, and planner confirmation.
- The V1 pilot needs a clear audit trail more than automatic override-driven replanning.
- Action-log surfacing is enough for pilot review while keeping dashboard calculations based on canonical inputs and deterministic formulas.

Post-V1 backlog:

- Evaluate semantic target matching for recommendation and operation overrides.
- Add dashboard-level stale decision warnings if pilot users need them.
- Add an explicit reapply/clone decision workflow after planner confirmation.

## M6-E4 Backup Location and Restore Policy

Date: 2026-05-08

Decision: V1 pilot uses `data/backups/` as the default local backup archive location. Each archive contains the SQLite database, uploaded workbook directory, generated export directory, and a manifest. Pilot operators must copy backup archives to an off-machine location after creation.

Restore policy:

| Scenario | V1 behavior |
|---|---|
| Backup creation | Use the runtime backup utility to create a manifest-bearing `.zip` archive |
| Test restore | Restore into a separate test path and run SQLite integrity smoke checks |
| Local runtime restore | Stop the app, create a pre-restore backup if needed, then restore with `--force` |
| Existing target data | Restore refuses to overwrite existing runtime data unless `--force` is supplied |

Rationale:

- `data/backups/` keeps local operator commands simple and near the runtime paths already documented for V1.
- A single archive avoids mismatches between the database, uploaded workbooks, and generated exports.
- Off-machine copying is required for pilot resilience because a local archive alone does not protect against workstation or disk loss.

Post-V1 backlog:

- Add scheduled backup automation in deployment tooling.
- Add retention policies and off-site backup verification for production deployment.

## M6-E6 Release Scope Decisions

Date: 2026-05-08

Decision: V1 is ready for pilot when the release readiness checklist passes and the pilot validation workflow runs against the committed golden workbook.

Resolved release questions:

| Question | V1 decision |
|---|---|
| Should accepted subcontract recommendations appear in generated Excel exports by default? | Yes. The Subcontract Plan export includes recommendation `Status`, so accepted recommendations are visible by default. A3 Planning also includes planner override rows. |
| Should generated exports include one workbook with multiple sheets or separate files per report? | Each requested report creates its own workbook. Weekly Planning is the multi-sheet planning pack. A3 Planning is a workbook containing the A3 sheet. |
| Should app settings such as `flow_gap_limit_days` be configurable in the UI? | Keep formula settings backend-owned for V1. UI configuration is deferred until after pilot feedback. |

Rationale:

- Pilot users need a stable, deterministic build more than runtime configurability.
- Export history and one-workbook-per-report behavior keep downloads simple while allowing Weekly Planning to serve as the consolidated planning pack.
- Showing accepted status in exports preserves planner intent without introducing override-driven recalculation.

Post-V1 backlog:

- Add configurable planning settings UI if pilot users need plant-specific tuning.
- Add release note generation from the checklist and test output.
- Revisit export packaging if users prefer one consolidated all-report workbook.
