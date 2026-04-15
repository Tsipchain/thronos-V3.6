# Learn2Earn Result States (Phase 2)

## Objective
Keep academic outcomes explicit and decoupled.

## Required Separated Dimensions
- `completion_status`
- `quiz_score`
- `pass_fail_status`
- `certificate_eligibility`
- `reward_eligibility`

## Additive Envelope
Endpoints expose `result_state` with:
- score thresholds (`quiz_pass_threshold`, `certificate_threshold`)
- separated state fields (completion/pass-fail/certificate/reward)
- policy context (reward policy, certificate approval mode)
- tenant context (tenant/institution/issuer/branding/tenant notes)

## Compatibility
Legacy response fields remain; `result_state` is additive.
