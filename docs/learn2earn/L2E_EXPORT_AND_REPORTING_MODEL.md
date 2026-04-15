# L2E Export and Reporting Model

## Export domains
- approval history
- issuance history
- learner academic history
- tenant-scoped operational history
- certificate event history

## Export semantics
All export/report payloads are structured with schema/version metadata and generation timestamp.

## Access constraints
- tenant admins and delegates: tenant-scoped visibility only
- global admins: global visibility via admin authorization
- students: no privileged history/report exports
