# PR: Learn2Earn Modular Access (Merge-Ready)

## Executive Summary
This PR finalizes Learn2Earn modular access so enrollment, wallet eligibility, rewards, pledge constraints, and live classrooms are clearly separated and production-ready.

## Product Rationale
- Users should be able to pay with THR or card (Stripe) to access learning.
- THR remains the canonical pricing rail and settlement unit.
- Rewards must remain wallet-based and auditable.
- Pledge controls must only gate explicitly pledge-required features.
- Teachers need practical live-session management in the classroom UI.

## Architecture Overview
- **Access layer**: enrollment (`thr` or `stripe`) grants course participation.
- **Reward layer**: reward eligibility is wallet-dependent and state-driven.
- **Policy layer**: live sessions enforce `public | enrolled-only | thr-wallet-only | pledge-only | invite-only`.
- **UI layer**: cards/modals expose policy and lifecycle state with clear disabled reasons.

## Enrollment Model
- Supported methods:
  - `payment_method="thr"` (on-chain transfer + auth)
  - `payment_method="stripe"` (access-only mirror path using THR-price fiat estimate)
- Core fields:
  - `learner_id`
  - `student_thr` (optional for stripe)
  - `reward_eligible`
  - `access_only`
  - `reward_state`

## Reward Lifecycle Model
- States:
  - `not_eligible`
  - `eligible`
  - `claimable`
  - `claimed`
  - `rejected`
  - `completed_without_wallet`
- Claim API only accepts `claimable`.
- Completion alone does **not** auto-issue reward.
- Reward transfer executes only during successful claim.
- `teacher_approval` / `admin_approval` are modeled policy modes; full approval workflow remains pending.

## Live-Session Access Model
- Teacher/admin can create/edit/delete sessions.
- Student join checks are layered by access policy:
  - `public`
  - `enrolled-only`
  - `thr-wallet-only`
  - `pledge-only`
  - `invite-only`
- Seat limits enforced server-side.

## Endpoint Table
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/courses/:course_id/enroll` | THR or Stripe enrollment |
| POST | `/api/v1/courses/:course_id/claim_reward` | Claim reward if `claimable` |
| GET | `/api/v1/courses/:course_id/enrollment/:learner_id` | Enrollment + reward lifecycle |
| GET | `/api/v1/courses/:course_id/live_sessions` | List sessions with attendance/seat hydration |
| POST | `/api/v1/courses/:course_id/live_sessions` | Teacher/admin create session |
| PATCH | `/api/v1/courses/:course_id/live_sessions/:session_id` | Teacher/admin edit session |
| DELETE | `/api/v1/courses/:course_id/live_sessions/:session_id` | Teacher/admin delete session |
| POST | `/api/v1/courses/:course_id/live_sessions/:session_id/join` | Join live session with policy checks |

## Validation / Security Hardening Notes
- Strict payload validation for enrollment, claim, live create/edit/join.
- Duplicate protections:
  - duplicate enrollment => `409`
  - duplicate join => `409`
  - duplicate claim => `409`
- Teacher/admin authorization for live-session management.
- Server-side policy enforcement remains source-of-truth for joins and claims.

## Migration / Data Notes
- Keep `l2e_enrollments.json` and `l2e_live_sessions.json` in persistent data volume.
- Backfill old enrollments with explicit `reward_state`.
- For legacy users without wallet, use `completed_without_wallet` when completed.

## QA Checklist
- [ ] THR enroll path works and writes on-chain payment tx.
- [ ] Stripe enroll path grants access but sets `reward_state=not_eligible`.
- [ ] Reward claim allowed only when `claimable`.
- [ ] Duplicate enroll/join/claim return `409`.
- [ ] Live session create/edit/delete works for teacher/admin only.
- [ ] Access policies block/allow as expected.
- [ ] Seat limits enforced.
- [ ] Replay button appears only when replay URL exists.
- [ ] UI badges and disabled reasons are clear.

## Rollout Plan
1. Deploy backend + frontend together.
2. Run smoke tests for enroll/claim/live session actions.
3. Validate enrollment and live-session JSON persistence.
4. Monitor logs for validation rejects and auth denials.
5. Enable teacher onboarding notes for live classroom workflow.

## Future Improvements
- Replace prompt-based fallbacks with richer dashboard tables.
- Add timezone-aware scheduling picker and locale formatting.
- Add webhook-verified Stripe intent status before enrollment finalize.
- Add invite management UI for `invite-only`.
- Add server-driven capability endpoint for per-user action gating.
- Expand certificate issuance workflows using `L2E_CERTIFICATE_MODEL.md`.
- Add tenant governance boundaries from `L2E_TENANT_UNIVERSITY_MODE.md`.
