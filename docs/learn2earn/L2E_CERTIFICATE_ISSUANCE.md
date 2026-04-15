# Learn2Earn Certificate Issuance (Phase 3)

## Non-Automatic Issuance Guarantee
Certificate issuance is explicit and never automatic on completion/quiz pass.

## Issuance Endpoint
- `POST /api/v1/courses/<course_id>/certificates/<learner_id>/issue`

## Issuance Persistence
On successful issuance:
- `issued_at`
- `certificate_id`
- `certificate_issuer_identity`
- lifecycle updated to `issued`

## Preconditions
- certificate lifecycle must be `issuable`
- tenant/institution consistency checks must pass
- issuer identity must match configured course issuer identity
