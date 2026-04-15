# Learn2Earn Approval Workflow (Phase 3)

## Scope
Phase 3 introduces explicit certificate approval actions with manual transitions.

## Supported Transitions
- `eligible -> pending_approval` (`request_approval`)
- `pending_approval -> issuable` (`approve`)
- `pending_approval -> rejected` (`reject`)
- `issuable -> issued` (`issue`)

## Endpoints
- `GET /api/v1/courses/<course_id>/certificates/queue`
- `POST /api/v1/courses/<course_id>/certificates/<learner_id>/request_approval`
- `POST /api/v1/courses/<course_id>/certificates/<learner_id>/approve`
- `POST /api/v1/courses/<course_id>/certificates/<learner_id>/reject`

## Authorization Model (Current)
- Teacher of course or admin can operate.
- Approval/rejection reason fields are persisted when supplied.
