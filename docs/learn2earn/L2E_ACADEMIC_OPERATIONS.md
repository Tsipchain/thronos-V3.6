# L2E Academic Operations (Teacher/Admin)

## Teacher-issued lesson completion flow
1. Learner enrolls and attends.
2. Learner submits quiz.
3. System records weighted score + pass/fail.
4. If passing conditions met, completion status is updated.
5. Reward remains claim-controlled and separate from completion.

## Certificate eligibility flow
1. Check `certificate_enabled`.
2. Compare `quiz_score` with `certificate_threshold_score`.
3. Set eligibility + lifecycle status:
   - `issuable` for manual mode
   - `pending_approval` for teacher/admin approval modes
4. Issuance remains separate, explicit operation.

## Future approval queue logic (modeled, pending)
- Teacher approval queue for `teacher_approval` certificates/rewards.
- Admin approval queue for `admin_approval` certificates/rewards.
- Audit trail requirements:
  - approver identity
  - decision timestamp
  - reason metadata

## Institution / tenant ownership model
- Tenant/institution identifiers persist on course/enrollment records.
- Tenant branding and issuer identity fields are reserved for certificate pipelines.
- Full tenant policy enforcement is deferred to next phase.
