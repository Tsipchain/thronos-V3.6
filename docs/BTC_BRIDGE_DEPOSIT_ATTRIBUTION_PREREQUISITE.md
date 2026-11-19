# BTC Bridge deposit attribution prerequisite

Status: **required, not implemented**. `bridge_inbound` must remain disabled.

## Why the shared-address design is insufficient

An HMAC-bound intent can authenticate what the Thronos server displayed to a
recipient. It cannot prove that a later Bitcoin `txid:vout` sent to one shared
`BTC_BRIDGE_INBOUND_ADDRESS` was paid by, or for, that recipient. Transaction
origin heuristics, requested amounts, browser sessions, and timing correlation
are not authoritative attribution evidence.

PR #961 therefore fails closed with
`bridge_deposit_attribution_unavailable` even when the legacy shared-address
configuration is otherwise complete. No configuration flag can bypass this
guard.

## Canonical attribution model

Implement a separate, durable allocator before exposing a real-money deposit
UI:

1. Import a mainnet watch-only descriptor controlled by the Bridge custody
   policy. The web service receives no private key, seed, signer, or broadcaster.
2. Atomically reserve a never-reused derivation index and its unique deposit
   address for one canonical recipient and one intent identifier.
3. Commit the allocation before returning the address. Persist at least:
   network, intent ID, canonical recipient, address, scriptPubKey, descriptor
   fingerprint, derivation index, registry/configuration version, created time,
   expiry time, and state. Enforce unique constraints on `(network, address)`
   and `(network, descriptor_fingerprint, derivation_index)`.
4. Return a short-lived signed presentation envelope. Its HMAC authenticates
   transport metadata only; the persistent unique address is the attribution
   boundary.
5. Observe Bitcoin through the independent Core-backed observer and identify
   the exact integer-satoshi output by `main:txid:vout`. Verify its scriptPubKey
   equals the stored allocation and re-check the canonical chain and required
   confirmation depth before any settlement handoff.
6. Keep expired addresses watched. A late, conflicting, or otherwise ambiguous
   payment enters quarantine/manual reconciliation and is never silently
   reassigned.
7. Pass a persistent, idempotent settlement command to the separately reviewed
   accounting boundary. Address allocation or observation alone never credits a
   balance.

Exact-amount matching on a shared address is not an acceptable substitute: it
can collide, be rounded, be paid twice, or be copied by another payer.

## Custody isolation

The allocated address must be rejected if it collides with any corporate
revenue, pledge vault, hot wallet, settlement reserve, treasury, or other
operator-registered incompatible role. `BTC_BRIDGE_INCOMPATIBLE_CUSTODY_ROLES`
is a strict JSON object mapping operator role names to mainnet addresses. Invalid
registries fail closed; errors and logs must never include configured values.

The allocator must validate descriptor network/genesis identity and preserve
the separation between Bridge watch-only discovery and all signing custody.

## Required acceptance evidence

Before a separate activation review, tests must cover concurrent allocation,
process crash before and after commit, database restart, descriptor gap recovery,
address non-reuse, wrong network, wrong address/script, wrong vout, duplicate and
conflicting observations, late payment, insufficient confirmations, reorg before
handoff, reorg after a credited fixture, and retry without duplicate credit.

Production activation additionally requires an operator-reviewed persistent
volume/database, backup and recovery drill, custody-role inventory, Bitcoin Core
verification evidence, and an explicit independent approval. PR #961 does not
implement settlement, crediting, signing, broadcasting, or activation.
