# Wallet V1 Legacy Address Migration Plan

## Purpose
Define how legacy THR addresses transition to Wallet V1 authority while preserving historical continuity and service state.

## Core Rule
- A legacy address remains historical/read-only after migration.
- A Wallet V1 secp256k1-derived address becomes future write/signing authority.

## Ecosystem-Wide Migration Surfaces
Migration scope MUST cover all Thronos surfaces that reference legacy THR addresses:
- EVN / internal identity
- mining payout addresses and mining history
- pools / pool ownership / pool rewards
- NFTs / NFT ownership and creator records
- pledge/admission records
- whitelist records
- token balances and token ownership
- L2E
- music
- commerce
- gateway
- VerifyID
- MEDICE
- roadway assistant
- recovery / LSB wallet contract artifacts
- external app bindings

## Preservation Requirements
Migration MUST preserve:
- balances
- NFT ownership
- pool ownership
- pool reward claims
- mining reward history
- pledge / whitelist admission
- service entitlements
- recovery metadata
- audit trail mapping `old_address -> new_v1_address`

## Secret Handling Prohibitions
Migration MUST NEVER expose or store:
- private keys
- mnemonics
- seeds
- old send secrets
- old auth secrets
- passphrases

## Legacy Ownership Proof (Correctness Constraint)

If the server stores only `send_seed_hash` (e.g., `sha256(send_seed)`), then:
- it **cannot** recompute HMAC/challenge-response proofs that require raw `send_seed`
- it **cannot** validate challenge signatures keyed by raw secret unless another compatible verifier already exists

Therefore migration MUST use one valid design:

### Design A (allowed): one-time TLS secret submission
- User submits legacy secret over TLS once during migration.
- Server checks `sha256(submitted_secret) == stored_send_seed_hash`.
- On success, server performs bind/cutover and immediately discards submitted secret.
- Secret is never persisted, logged, or replayed.

### Design B (allowed only if pre-existing verifier exists)
- Use an already-stored verifier that natively supports challenge-response without raw secret.
- If such verifier does not exist, challenge-response is **not possible** with only `sha256(secret)`.

### Explicit prohibition
- Do not implement pseudo-logic that derives HMAC/challenge validation from `stored_send_seed_hash` alone.
