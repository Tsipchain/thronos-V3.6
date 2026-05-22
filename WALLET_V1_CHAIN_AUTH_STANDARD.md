# Wallet V1 Chain-Wide Authorization Standard

**Status:** Draft (Do not mark production-ready)  
**Scope:** Thronos core + external services  
**Date:** May 21, 2026

---

## 1) Purpose

This document defines a chain-wide authorization model that replaces secret-based write authorization (`auth_secret`, `seed`, `mnemonic`, `privateKey`, `passphrase`) with **client-side signed Wallet V1 envelopes** using ECDSA/secp256k1.

This applies to all state-changing operations, including:
- send
- stake
- swap
- bridge
- pledge
- L2E
- music
- tokens
- pools
- commerce
- VerifyID
- MEDICE
- roadway assistant
- gateway
- external apps

---

## 2) Non-Negotiable Security Rules

1. No service may require or transmit:
   - `auth_secret`
   - `privateKey`
   - `mnemonic`
   - `seed`
   - `passphrase`
2. Every write endpoint must accept a signed Wallet V1 envelope.
3. Backend must verify signature + identity binding + replay/timestamp controls.
4. Replica/read-only nodes must reject writes with `503`.
5. Fee/burn behavior must remain canonical per service.
6. Legacy secret endpoints are deprecated first, removed only after migration completion.

---

## 3) Canonical Envelope Contract (v1)

All write requests MUST include a top-level envelope object:

```json
{
  "kind": "<operation_kind>",
  "from": "THR...",
  "nonce": "unique-client-nonce",
  "timestamp": 1710000000,
  "payload": {
    "...service-specific fields...": "..."
  },
  "publicKey": "02... or 03...",
  "signature": "DER_HEX"
}
```

### 3.1 Required fields
- `kind`: operation discriminator (e.g., `thr_send`, `stake_create`, `swap_exact_in`)
- `from`: signer wallet address
- `nonce`: unique replay-protection token
- `timestamp`: UNIX epoch seconds
- `payload`: service-specific signed body
- `publicKey`: compressed secp256k1 (66 hex, prefix `02` or `03`)
- `signature`: ECDSA DER hex over canonical message

### 3.2 Canonical signing bytes
Signed message MUST be deterministic:
- JSON encoding with `sort_keys=true`
- compact separators `(',', ':')`
- UTF-8 bytes
- sign exactly this object:

```json
{
  "kind": "...",
  "from": "...",
  "nonce": "...",
  "timestamp": 1710000000,
  "payload": { ... }
}
```

`publicKey` and `signature` are not part of signed body.

---

## 4) Backend Verification Pipeline (all services)

For every write endpoint:

1. **Envelope schema validation**
   - required fields present
   - forbid secret fields (`auth_secret`, `mnemonic`, `privateKey`, `seed`, `passphrase`)
2. **Public key validation**
   - compressed secp256k1, 66 hex, starts with `02`/`03`
3. **Address binding**
   - derive THR address from `publicKey`
   - derived address MUST equal `from`
4. **Timestamp window**
   - reject if outside configured skew (default ±300s)
5. **Nonce replay protection**
   - Redis-based global nonce set with TTL
   - second use rejected
   - Redis unavailable => fail-closed
6. **Signature verification**
   - verify DER ECDSA over canonical bytes
7. **Capability/permission authorization**
   - ensure `kind` allowed for address/service role
8. **Replica guard**
   - if `NODE_ROLE=replica` or `READ_ONLY=true` => 503
9. **Execute operation**
   - use existing canonical business logic + fee/burn policy

---

## 5) Error Model (normalized)

Suggested response format:

```json
{
  "ok": false,
  "error": "<machine_error>",
  "detail": "<optional_debug_detail>",
  "code": "<optional_domain_code>"
}
```

Required machine errors:
- `missing_envelope`
- `invalid_envelope_schema`
- `forbidden_legacy_secret_field`
- `invalid_public_key`
- `address_public_key_mismatch`
- `timestamp_outside_tolerance`
- `nonce_replay_detected`
- `nonce_store_unavailable`
- `signature_invalid`
- `read_only_replica`
- `insufficient_balance`
- service-specific execution errors

---

## 6) Fee/Burn Invariant

Wallet V1 authorization MUST NOT alter service economics.

Per service operation, execution MUST call the same canonical fee functions currently used in production.

Examples:
- THR send: `calculate_fixed_burn_fee` + `split_and_credit_fee`
- swap/pool/bridge/etc: their existing canonical fee handlers

Required invariants:
- sender debit includes fee where applicable
- receiver/target credits remain unchanged from legacy semantics
- burn and treasury/account split unchanged
- `/api/transfers` and related feeds retain expected fee fields

---

## 7) Replica/Read-Only Node Behavior

All state-changing Wallet V1 endpoints MUST:
- return `503` with `error=read_only_replica` on replica/read-only nodes
- remain readable for health/metadata endpoints

---

## 8) Legacy Compatibility + Deprecation

### 8.1 Transitional policy
- Legacy secret endpoints remain available during migration.
- New Wallet V1 endpoints reject legacy secret fields.
- Add deprecation headers/telemetry on legacy writes.

### 8.2 Legacy wallet migration flow
1. user proves legacy ownership with existing `old_address + auth_secret`
2. user generates Wallet V1 keypair locally
3. user signs bind/migration envelope
4. backend binds legacy account -> Wallet V1 identity
5. balances/state preserved
6. fee policy unchanged

### 8.3 Sunset controls
- publish timeline
- monitor legacy usage
- freeze new legacy wallet creation
- staged disable by service

---

## 9) Service Envelope Kinds (initial registry)

- `thr_send`
- `stake_create`, `stake_withdraw`
- `swap_exact_in`, `swap_remove_liquidity`, `swap_add_liquidity`
- `bridge_deposit_intent`, `bridge_withdraw`
- `pledge_create`, `pledge_update`
- `l2e_enroll`, `l2e_claim`
- `music_tip`, `music_purchase`
- `token_transfer`, `token_mint`, `token_burn`
- `commerce_checkout`, `commerce_refund`
- `verifyid_submit`, `verifyid_attest`
- `medice_record_write`
- `roadway_action_submit`
- `gateway_payment_intent`

Each kind must define strict payload schema.

---

## 10) Testing Requirements (minimum)

Per migrated service:
1. invalid signature rejected
2. address/publicKey mismatch rejected
3. replay nonce rejected
4. forbidden secret fields rejected
5. legacy secrets not accepted on V1 endpoint
6. valid signed operation executes
7. payload tampering after signing rejected
8. replica write rejected with 503
9. fee/burn parity with legacy path preserved

Cross-service integration tests:
- normalized error responses
- nonce isolation/collision behavior
- tx feed/indexing consistency

---

## 11) Observability + Audit

Required telemetry fields:
- `kind`, `from`, `node_role`, `read_only`
- verifier stage failure (`schema`, `pubkey`, `derive`, `timestamp`, `nonce`, `signature`, `capability`)
- execution result (`accepted/rejected`)
- tx_id
- fee/burn outputs

Add dashboards for:
- signature failure rate
- replay attempts
- legacy endpoint usage trend
- replica write attempts

---

## 12) Phased PR Plan (required)

1. **Standard + shared verifier**
   - envelope spec, shared verification middleware/helpers
2. **Browser wallet signer**
   - implement client signer API (`getPublicKey`, `signTransaction`) with lock/PIN semantics
3. **Send migration**
   - `/send` to Wallet V1 envelope path
4. **Stake/swap/bridge migration**
5. **Pledge/L2E/music migration**
6. **External app signing SDK**
7. **Legacy endpoint shutdown plan**

Do not migrate all services in one PR.

---

## 13) Immediate Next Steps

- Approve this standard doc.
- Build shared verifier package and envelope schema registry.
- Implement wallet signer methods in browser wallet session module.
- Re-run staged browser/network validation before any merge.

