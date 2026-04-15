# Learn2Earn Production Smoke Checklist

## Final Launch Checklist

### 1) Production Smoke Verification
- [ ] Core L2E routes respond with expected auth behavior and HTTP status codes.
- [ ] No schema/hydration errors appear during normal learner and instructor flows.
- [ ] Error payloads remain structured for UI/operator troubleshooting.

### 2) Payment / Enrollment Verification
- [ ] THR-first enrollment pricing is enforced and unchanged.
- [ ] Enrollment creation/update works for authorized actors.
- [ ] Duplicate enrollment protections and learner identity handling remain intact.

### 3) Live Session Verification
- [ ] Live session creation/listing/join flows are reachable and stable.
- [ ] Role boundaries for live session operations are enforced.
- [ ] Live session fields render correctly in course experiences.

### 4) Quiz / Result-State Verification
- [ ] Quiz submissions compute expected score/pass/fail outcomes.
- [ ] Result-state transitions are persisted and visible in learner history.
- [ ] Result-state logic does not auto-issue rewards/certificates.

### 5) Certificate Approval / Issuance Verification
- [ ] `request_approval` transitions to pending approval state.
- [ ] `approve` and `reject` are role-gated and correctly persisted.
- [ ] `issue` is explicit, role-gated, and non-automatic.
- [ ] Certificate lifecycle transitions are reflected in audit history.

### 6) Tenant / RBAC / Audit Verification
- [ ] Cross-tenant access attempts are denied.
- [ ] Tenant-admin/delegate/global-admin boundaries are enforced.
- [ ] Policy evaluation decisions are role-aware and consistent.
- [ ] Audit history visibility and export boundaries follow tenant/RBAC rules.

### 7) Dashboard / Report / Export Verification
- [ ] Tenant operational reports generate successfully.
- [ ] Report delivery lifecycle (`queued` -> `processing` -> terminal) is tracked.
- [ ] Course/tenant/global observability summaries are accurate.
- [ ] Export payload structures remain compliance-ready.

## Final Screenshot / Demo Checklist

### Student Flow
- [ ] Enrollment, participation, quiz submission, and result-state views.

### Teacher Flow
- [ ] Course configuration, live session management, and learner result review.

### Admin / Tenant Flow
- [ ] Tenant-scoped dashboard/report operations under authorized roles.

### Approval Flow
- [ ] Certificate request and approval/rejection queue transitions.

### Certificate Issuance Flow
- [ ] Explicit issuance action and resulting lifecycle/audit state.

### Dashboard Flow
- [ ] Course observability, tenant observability, and global L2E dashboard snapshots.

### Policy / Report Flow
- [ ] Policy evaluation request/response and report delivery lifecycle evidence.

## Exit Criteria
All launch checklist and screenshot/demo checklist items must be validated before public rollout.
