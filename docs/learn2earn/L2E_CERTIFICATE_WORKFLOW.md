# Learn2Earn Certificate Workflow (Phase 2)

## Scope
Phase 2 introduces a **non-automatic certificate workflow skeleton** on top of the stabilized Learn2Earn foundation.

## Explicit Lifecycle States
`certificate_lifecycle_state` values in this phase:
- `not_enabled`
- `eligible`
- `pending_approval`
- `issuable`
- `issued`
- `rejected`

## Design Rules
- Certificate issuance is **not automatic**.
- Completion, pass/fail, certificate status, and reward states are separate.
- Approval modes (`manual`, `teacher_approval`, `admin_approval`) are modeled for workflow readiness.

## Course-Level Configuration
- `certificate_enabled`
- `certificate_threshold_score`
- `certificate_approval_mode`
- `certificate_template_name`
- `certificate_issuer_identity`
