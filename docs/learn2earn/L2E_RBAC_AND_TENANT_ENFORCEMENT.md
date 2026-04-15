# L2E RBAC and Tenant Enforcement Hooks (Phase 3)

## Current Hooks
- teacher-or-admin actor enforcement for approval and issuance operations
- tenant/institution ownership consistency checks at operation time
- issuer identity consistency check during issuance

## Why Hooks (Not Full RBAC Yet)
This phase adds compatibility groundwork for future RBAC/tenant isolation without introducing full runtime tenancy boundaries.

## Deferred
- role matrix and delegated roles
- tenant-scoped auth tokens
- strict tenant data partitions
