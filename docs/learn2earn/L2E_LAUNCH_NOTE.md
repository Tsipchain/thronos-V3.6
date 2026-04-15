# Learn2Earn Launch / Rollout Note

## Launch Position
Learn2Earn launches as a **core Thronos Chain service** with completed Phases 1–8 foundation controls.

## What Is Complete
- Tenant-aware course operations with wallet-native learner interactions
- Stateful academic progression and certificate lifecycle governance
- RBAC/tenant policy enforcement for certificate, history, reporting, and observability actions
- Compliance reporting, delivery tracking, and observability dashboards
- Policy-evaluation provider compatibility (`internal`, `opa`, `cedar`) with stable internal enforcement semantics

## Intentionally Future Refinement
- deeper external policy execution beyond compatibility wrappers
- richer analytics/SLO depth
- broader delivery transport channel hardening and advanced retries
- additional UX/operator tooling polish

## Explicitly Unchanged at Launch
- THR-first pricing model remains unchanged
- controlled reward issuance remains unchanged and non-automatic
- approval/issuance boundaries remain explicit and role-governed

## What Must Be Confirmed Before Public Rollout
1. Final launch checklist completion (`L2E_PRODUCTION_SMOKE_CHECKLIST.md`).
2. Final screenshot/demo checklist completion (`L2E_PRODUCTION_SMOKE_CHECKLIST.md`).
3. No tenant/RBAC/audit/policy boundary regressions.
4. No automatic reward/certificate behavior regressions.

## Go / No-Go Criteria
### Go
- all required checklist items pass
- no high-severity boundary or governance regressions
- launch artifacts are captured and archived for handoff

### No-Go
- any failed boundary/security/governance check
- unresolved lifecycle/audit/reporting integrity issue
- incomplete launch or demo evidence for required flows
