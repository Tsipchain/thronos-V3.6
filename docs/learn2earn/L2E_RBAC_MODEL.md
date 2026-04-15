# Learn2Earn RBAC Model (Phase 4)

## Roles
- `student`
- `teacher`
- `course_owner`
- `tenant_admin`
- `global_admin`
- `delegate_operator`

## Action Boundaries (current)
- `request_approval`: student + teacher/admin roles
- `approve/reject/issue`: teacher/admin/operator roles
- `view_queue/view_history`: teacher/admin/operator roles

## Notes
- This is enforcement-oriented RBAC groundwork, not a full distributed RBAC system yet.
