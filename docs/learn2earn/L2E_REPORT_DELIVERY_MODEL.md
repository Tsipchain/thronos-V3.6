# L2E Report Delivery Model

## Delivery object
- delivery_id
- tenant_id
- report_type
- status
- requested_by
- requested_role
- requested_at
- filters
- delivery_channel
- schema_version

## Supported report types
- operational
- approval_history
- issuance_history
- learner_history
- audit_history

## Access model
- tenant_admin/delegate_operator: tenant-scoped only
- global_admin: global access with admin authorization
