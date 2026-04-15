# L2E Certificate Workflow (Skeleton Layer)

## Goal
Add non-destructive certificate workflow readiness on top of existing L2E completion and quiz foundations.

## Lifecycle states
- `not_enabled`
- `eligible`
- `pending_approval`
- `issuable`
- `issued`
- `rejected`

## Rules
1. Certificate issuance is never automatic on course completion.
2. Completion and certificate issuance remain separate operations.
3. Eligibility depends on:
   - course `certificate_enabled`
   - score >= `certificate_threshold_score`
4. Approval mode support:
   - `manual` => `issuable` when eligible
   - `teacher_approval` => `pending_approval` until approved
   - `admin_approval` => `pending_approval` until approved

## Current phase
- Approval mode semantics are modeled.
- Final approval queue UI and issuing endpoints are pending future phase.
