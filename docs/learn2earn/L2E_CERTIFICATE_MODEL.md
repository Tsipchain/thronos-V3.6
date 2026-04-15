# L2E Certificate Model (Ready-to-Issue Data Layer)

Certificate issuance is modeled as a data layer extension and eligibility state,
without forcing immediate certificate minting workflows.

## Course-level certificate fields
- `certificate_enabled` (bool)
- `certificate_threshold_score` (int)
- `certificate_template_name` (optional)
- `certificate_issuer_identity` (teacher or institution identity)

## Enrollment/attempt-level certificate fields
- `certificate_eligibility` (bool)
- `certificate_status` (`not_eligible | eligible | issued | revoked`)
- `issued_at` (optional timestamp)

## Behavior in current phase
- Eligibility is calculated at quiz completion/score evaluation.
- Automatic certificate issuance is not forced in this phase.
- Issuance workflow can be added in a later phase with issuer signatures and branding templates.
