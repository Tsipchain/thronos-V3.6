# L2E Policy Evaluation Model

## Objective
Provide a stable internal policy-evaluation envelope compatible with future external policy-engine integration.

## Evaluation output fields
- policy_version
- action
- actor_role
- actor_identity
- course_id
- tenant_context (requested + course tenant/institution)
- constraints (tenant requirement, delegate constraints, learner context)
- allowed
- denial_reason

## Current usage
Applied for approval permissions, issuance permissions, export/history permissions, tenant visibility, and delegate limitations.
