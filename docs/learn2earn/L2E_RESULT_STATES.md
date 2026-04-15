# L2E Result States

This document defines explicit, separable academic/result state dimensions.

## Quiz/result axis
- `quiz_score` (weighted)
- `pass_fail_status` (`pass|fail`)

## Completion axis
- `completion_status` (`completed|incomplete`)

## Certificate axis
- `certificate_eligibility` (bool)
- `certificate_status` (`not_enabled|eligible|pending_approval|issuable|issued|rejected`)

## Reward axis
- `reward_eligibility` (eligible/not_eligible)
- reward claimability/claimed states handled separately in reward lifecycle model

## Why this separation matters
- Passing quiz does not automatically mean certificate issued.
- Completion does not automatically mean reward paid.
- Academic evidence, certification, and token rewards remain modular but linked.
