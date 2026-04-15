# Learn2Earn Production Smoke Checklist

## A. Core Availability
- [ ] L2E course endpoints respond successfully for authorized users.
- [ ] Enrollment and quiz result flows load without schema errors.
- [ ] Certificate workflow endpoints are reachable and return expected status codes.

## B. Security / Boundary Verification
- [ ] Tenant-scoped actors cannot access other tenant resources.
- [ ] Non-admin/non-delegate roles are blocked from governed admin actions.
- [ ] Policy-evaluation endpoint enforces role-aware decisions.
- [ ] Audit history visibility follows RBAC + tenant boundaries.

## C. Certificate Governance
- [ ] Request approval transitions to pending state.
- [ ] Approve and reject transitions are enforced by authorized roles only.
- [ ] Issue action is explicit and not automatic.
- [ ] Certificate lifecycle transitions are audit logged.

## D. Compliance / Reporting
- [ ] Tenant operational report generation succeeds.
- [ ] Report delivery creation stores queued state.
- [ ] Delivery process updates record attempts and outcomes.
- [ ] Delivery audit trail entries are present for each lifecycle event.

## E. Observability / Dashboard
- [ ] Course observability endpoint returns action and role summaries.
- [ ] Tenant observability includes delivery state counts.
- [ ] Global L2E dashboard returns totals, action counts, delivery-state counts.

## F. Policy Provider Compatibility
- [ ] Policy evaluation succeeds with `internal` provider.
- [ ] Policy evaluation succeeds with `opa` compatibility mode.
- [ ] Policy evaluation succeeds with `cedar` compatibility mode.
- [ ] Unsupported engine value falls back safely to internal semantics.

## G. Screenshot / Demo Capture Checklist
- [ ] Capture course creation page showing tenant/institution inputs.
- [ ] Capture certificate queue/history views under authorized role.
- [ ] Capture policy evaluation payload/response example.
- [ ] Capture tenant observability and global dashboard summaries.
- [ ] Capture report delivery lifecycle progression (`queued` -> `processing` -> terminal).

## Exit Criteria
All sections above must pass before marking a deployment window as launch-ready.
