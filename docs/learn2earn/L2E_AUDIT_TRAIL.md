# Learn2Earn Audit Trail (Phase 4)

## Persisted Events
- approval requested
- approved
- rejected
- issued

## Recorded Fields
- actor identity
- actor role
- tenant / institution context
- timestamp
- reason
- lifecycle transition (`from_state`, `to_state`)
- certificate id (where available)

## Endpoints
- `GET /api/v1/courses/<course_id>/certificates/<learner_id>/history`
- `GET /api/v1/courses/<course_id>/certificates/history`
- `GET /api/v1/courses/<course_id>/results/<learner_id>/history`
