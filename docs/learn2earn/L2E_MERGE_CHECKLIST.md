# L2E Merge Checklist

## Merge-ready checks
- [x] THR canonical pricing is enforced in backend and UI.
- [x] Teacher payout pathway remains THR-denominated.
- [x] Stripe path is mirror access-only and not an independent pricing rail.
- [x] Completion does not auto-issue rewards.
- [x] Claim-time reward issuance uses eligibility + wallet + policy gates.
- [x] Reward lifecycle states are represented in enrollment status.
- [x] UI copy states rewards are not automatic and not guaranteed.

## Remaining gaps (intentionally deferred)
- [ ] Teacher approval workflow execution (`teacher_approval`) endpoints.
- [ ] Admin approval workflow execution (`admin_approval`) endpoints.
- [ ] Dedicated approval UI for pending/rejected reward claims.

## Post-merge roadmap
1. Implement approval queue APIs for teacher/admin policy modes.
2. Add audit log for reward approvals/rejections and rationales.
3. Add stronger fiat mirror source integration (oracle/config governance).
4. Add migration script to backfill legacy enrollments with explicit lifecycle fields.
