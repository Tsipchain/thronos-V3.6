# Learn2Earn Access Architecture (Thronos Chain)

## 1) Updated Data Models

### Enrollment (`data/l2e_enrollments.json`)
```json
{
  "<course_id>": {
    "<learner_id_or_wallet>": {
      "learner_id": "guest-1712345678 | THR...",
      "student_thr": "THR... | null",
      "payment_method": "thr | stripe",
      "stripe_payment_intent": "pi_xxx | null",
      "wallet_connected": true,
      "reward_eligible": true,
      "access_only": false,
      "enrolled_at": "2026-04-15 12:00:00 UTC",
      "completed": false,
      "completed_at": null,
      "reward_paid": false,
      "reward_claimed": false,
      "reward_claimed_at": null,
      "reward_state": "not_eligible|eligible|claimable|claimed|rejected|completed_without_wallet"
    }
  }
}
```

### Live Session (`data/l2e_live_sessions.json`)
```json
{
  "<course_id>": [
    {
      "id": "live-...",
      "title": "Session title",
      "description": "Agenda",
      "date": "2026-04-21",
      "time": "18:00",
      "timezone": "UTC",
      "duration": 60,
      "max_seats": 100,
      "access_type": "public|enrolled-only|thr-wallet-only|pledge-only|invite-only",
      "stream_url": "https://...",
      "replay_url": "https://... | null",
      "reward_amount": 0.0,
      "attendance": ["learnerA", "learnerB"],
      "invitees": [],
      "created_at": "2026-04-15 12:00:00 UTC"
    }
  ]
}
```

## 2) API Contracts

### Pricing & settlement rules
1. THR is the canonical pricing unit for courses.
2. Stripe/card is a mirror rail that references THR price as estimated fiat.
3. Teacher payout remains in THR.
4. Reward issuance is controlled (claim-based), not automatic on completion.

### Enroll in course
- `POST /api/v1/courses/{course_id}/enroll`
- Request:
```json
{
  "payment_method": "thr | stripe",
  "student_thr": "THR... (optional for stripe)",
  "learner_id": "guest-123 (optional)",
  "auth_secret": "required for thr",
  "passphrase": "optional",
  "stripe_payment_intent": "optional for stripe"
}
```
- Response:
```json
{
  "status": "success",
  "tx": {},
  "reward_eligible": true,
  "learner_id": "THR...",
  "new_balance_from": 123.45
}
```

### Claim reward
- `POST /api/v1/courses/{course_id}/claim_reward`
- Request: `{ "learner_id": "THR..." }`
- Response: `{ "status": "success", "reward_claimed": true }`

### Live sessions
- `GET /api/v1/courses/{course_id}/live_sessions`
- `POST /api/v1/courses/{course_id}/live_sessions`
- `POST /api/v1/courses/{course_id}/live_sessions/{session_id}/join`
- `PATCH /api/v1/courses/{course_id}/live_sessions/{session_id}`
- `DELETE /api/v1/courses/{course_id}/live_sessions/{session_id}`
- `GET /api/v1/courses/{course_id}/enrollment/{learner_id}`

### Access check rules
1. Stripe payment => course access only.
2. THR wallet connected => reward eligibility.
3. Pledge gates only `pledge-only` live sessions/features.
4. Live session create/edit/delete requires course teacher auth or admin auth.
5. Rewards become claimable only when completion-eligible + reward-eligible + wallet-connected.
6. `teacher_approval` and `admin_approval` reward policies are modeled but pending full workflow endpoints/UI.

## 3) React Component Structure (Reference)

```txt
src/features/learn2earn/
  Learn2EarnPage.tsx
  components/
    EnrollmentCard.tsx
    EnrollmentBadges.tsx
    PledgeShortcutCard.tsx
    PaymentSelector.tsx
    RewardEligibilityBanner.tsx
    LiveSessionCard.tsx
    LiveSessionList.tsx
    AttendancePill.tsx
  hooks/
    useEnrollmentState.ts
    useRewardEligibility.ts
    useLiveSessions.ts
  services/
    enrollments.api.ts
    liveSessions.api.ts
    rewards.api.ts
    pledgeGateway.api.ts
```

## 4) Route Structure

- UI
  - `/courses` (Learn2Earn)
  - `/courses/:courseId/live` (optional dedicated live page)
  - `/pledge` (pledge shortcut destination)
- API
  - `/api/v1/courses/:courseId/enroll`
  - `/api/v1/courses/:courseId/claim_reward`
  - `/api/v1/courses/:courseId/live_sessions`
  - `/api/v1/courses/:courseId/live_sessions/:sessionId/join`

## 5) Migration Notes

1. Backfill old enrollments with:
   - `payment_method="thr"`
   - `wallet_connected=true`
   - `reward_eligible=true`
2. For guest/legacy entries without wallet:
   - `wallet_connected=false`
   - `reward_eligible=false`
3. Create `data/l2e_live_sessions.json` as `{}` on first deploy.
4. Keep pledge internals outside L2E; only call pledge access checks for explicitly gated features.

## 6) Edge Cases

1. Stripe-enrolled user later connects wallet: allow update path to mark `reward_eligible=true`.
2. Same person enrolls once as guest and once as wallet: merge strategy required.
3. Invite-only session + seat limit reached.
4. Replay URL missing for completed sessions.
5. Reward claim attempted before completion.
6. Pledge outage should not block non-pledge course access.
7. Reward duplicate claims must return conflict (`409`).
8. Duplicate live joins must return conflict (`409`).

## 7) Test Plan

1. THR enrollment happy path (balance debit + enrollment record).
2. Stripe enrollment happy path (no THR debit, access granted).
3. Reward eligibility toggles correctly with/without `student_thr`.
4. Claim reward:
   - blocked for `reward_eligible=false`
   - success for eligible completed enrollment.
5. Live session join checks:
   - public
   - enrolled-only
   - thr-wallet-only
   - pledge-only
   - invite-only
6. UI badges/CTA visibility:
   - `Pledge Required`
   - `Pledge Recommended`
   - `THR Reward Eligible`
   - `No Reward Wallet`
   - `Stripe Enrollment`
   - `THR Enrollment`

## 8) Academic extension (additive)
- Quiz supports multiple question types with per-question weights.
- Pass threshold uses `pass_threshold_score` with fallback to prior pass score fields.
- Additive result states exposed:
  - `completion_status`
  - `quiz_score`
  - `pass_fail_status`
  - `certificate_eligibility`
  - `reward_eligibility`
- Certificate model fields on course:
  - `certificate_enabled`
  - `certificate_threshold_score`
  - `certificate_template_name`
  - `certificate_issuer_identity`
