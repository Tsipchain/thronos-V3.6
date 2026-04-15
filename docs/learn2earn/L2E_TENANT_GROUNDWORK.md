# L2E Tenant Groundwork

## Scope
Groundwork only (no full tenant boundary enforcement in this phase).

## Structural fields
- `tenant_id` (optional)
- `institution_id` (optional)
- tenant branding placeholders (template/name metadata)

## Ownership model notes
- Courses are tenant-ownable.
- Teachers can be tenant-associated.
- Certificates can be tenant/institution branded.
- Certificate issuer identity can be tenant/institution scoped.

## Deferred behavior
- Tenant permission boundaries and isolation policy checks.
- Tenant-level approval queue routing and policy administration UI.
