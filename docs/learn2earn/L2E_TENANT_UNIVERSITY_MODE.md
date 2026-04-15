# L2E Tenant / University Mode (Architecture Notes)

This note defines additive tenant-ready fields without rewriting the current single-tenant flow.

## Tenant-ready identifiers
- `tenant_id`
- `institution_id`

## Tenant ownership model
- Tenant-owned courses (`course.tenant_id`)
- Tenant-scoped teachers (teacher identities mapped to tenant)
- Tenant certificate branding (template name + issuer identity)
- Tenant pass policies (per-tenant threshold defaults)

## Current implementation scope
- Data fields are present on course model and can be persisted now.
- Full tenant access-control boundary enforcement is future-phase.
- Certificate branding workflows are future-phase.

## Future-phase roadmap
1. Tenant-scoped teacher permission checks.
2. Tenant certificate templates and issuer key management.
3. Tenant policy registry for pass thresholds and reward policy defaults.
4. Tenant dashboard for analytics and completion/certificate reporting.
