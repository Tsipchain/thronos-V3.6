# Wallet V1 Legacy Address Migration Plan (Design/Audit)

**Status:** Design Phase Only — No Implementation in This PR

**Branch:** `wallet-v1-legacy-migration-plan`

**Context:** Old onboarding creates THR addresses via `f"THR{int(time.time() * 1000)}"` (timestamp-string, not secp256k1-derived). These addresses cannot sign Wallet V1 transactions directly. This document defines a safe, auditable migration path.

---

## 1. Problem Statement

### 1.1 Legacy Address Format

Existing pledge flow (`pledge_submit.py`, line 62):
```python
thr_addr = f"THR{int(time.time() * 1000)}"
```

This produces addresses like `THR1716384529123` — NOT derived from a secp256k1 public key.

**Consequences:**
- Cannot recover `publicKey` from old address (no keypair exists)
- Cannot sign Wallet V1 ECDSA transactions from old address
- `verify_signed_transaction_core()` would reject: `publicKey` cannot derive to this address format
- Old users are locked out of Wallet V1 without a migration path

### 1.2 Legacy Credential Format

Existing pledge creates:
- `send_seed` — 16-byte hex secret (raw entropy)
- `send_auth_hash` — `sha256(send_seed:recovery_phrase:auth)`
- `send_seed_hash` — `sha256(send_seed)`

The raw `send_seed` is returned once as `send_secret` and embedded in LSB stego image.

**These are HMAC credentials, not keypair credentials.**

---

## 2. Migration Design

### 2.1 Overview

Migration is user-initiated, client-side-keyed, and server-verified:

```
[User: old legacy address + send_secret]
         |
         |  1. Generate new secp256k1 keypair (client-side)
         |  2. Submit migration request to /api/v1/wallet/migrate
         |
         v
[Server: verify old ownership + pledge admission]
         |
         |  3. Verify send_secret authenticates old address
         |  4. Verify old address has pledge/whitelist admission
         |  5. Derive new_v1_address from submitted publicKey
         |  6. Create explicit balance migration tx
         |  7. Bind admission to new_v1_address
         |  8. Mark old address legacy_migrated (read-only)
         |
         v
[User: new Wallet V1 address, same balance, same admission status]
```

### 2.2 Client-Side Keypair Generation

The backend MUST NOT generate or store private keys.

Client generates locally:
```javascript
// Client-side only — private key never sent to server
const ec = new elliptic.ec('secp256k1');
const keyPair = ec.genKeyPair();
const privateKey = keyPair.getPrivate('hex');  // stored locally only
const publicKey = keyPair.getPublic(true, 'hex');  // compressed, sent to server
```

Server receives ONLY:
- `old_thr_address` — legacy address being migrated
- `proof` — authentication using old send_secret (see §2.4)
- `new_compressed_public_key` — 66 hex chars, starts with `02` or `03`
- `signed_migration_request` — optional ECDSA signature with new key (proves possession)

### 2.3 New Address Derivation

Server derives `new_v1_address` from submitted public key using the canonical algorithm:

```python
# Canonical derivation (matches wallet_v1_address_derivation.py)
def derive_v1_address(compressed_public_key_hex: str) -> str:
    pub_bytes = bytes.fromhex(compressed_public_key_hex)
    sha256_hash = hashlib.sha256(pub_bytes).digest()
    ripemd160 = hashlib.new('ripemd160')
    ripemd160.update(sha256_hash)
    address_hash = ripemd160.hexdigest()[:40].upper()
    return f"THR{address_hash}"
```

**Result:** `new_v1_address` is always deterministic from `compressed_public_key`.

### 2.4 Proof of Old Ownership

To prove the user controls the legacy address, they provide:

```python
# Option A: Hash-based proof (simpler, no active signing needed)
proof_hash = hmac.new(
    key=send_secret.encode(),
    msg=f"migrate:{old_thr_address}:{new_compressed_public_key}".encode(),
    digestmod=hashlib.sha256
).hexdigest()

# Server verifies:
expected = hmac.new(
    key=stored_send_seed.encode(),  # from PLEDGE_CHAIN send_seed_hash lookup
    msg=f"migrate:{old_thr_address}:{new_compressed_public_key}".encode(),
    digestmod=hashlib.sha256
).hexdigest()
assert hmac.compare_digest(proof_hash, expected)
```

**Security note:** Server compares against stored `send_seed_hash` via constant-time comparison. The raw `send_seed` is never stored server-side — only its SHA256 hash. The proof verifies knowledge of `send_seed` without transmitting it.

### 2.5 Migration Request Endpoint (Specification)

**Future implementation PR must add:**

```
POST /api/v1/wallet/migrate
Content-Type: application/json

{
  "old_thr_address": "THR1716384529123",
  "new_compressed_public_key": "02abc...",
  "proof": "hmac-hex",
  "signed_migration_request": "ecdsa-der-hex"  // optional but preferred
}
```

**Response (success):**
```json
{
  "ok": true,
  "status": "migrated",
  "old_thr_address": "THR1716384529123",
  "new_v1_address": "THRabc...",
  "migration_tx_id": "MIGRATE-1716384529-abc123",
  "admission_method": "btc_confirmed",
  "pledge_hash": "sha256(...)",
  "recovery_contract_id": "..."
}
```

**NEVER in response:**
- `privateKey`, `mnemonic`, `seed`
- `send_secret`, `auth_secret`, `passphrase`
- `send_seed`, `send_seed_hash`

---

## 3. Server-Side Migration Steps

**Order of operations (all or nothing — fail-closed):**

1. **Validate public key format**
   - Must be 66 hex chars
   - Must start with `02` or `03`
   - Must be valid secp256k1 point

2. **Derive new_v1_address from public key**
   - Use canonical derivation (SHA256 → RIPEMD160 → first-40-hex → uppercase → THR prefix)

3. **Load old address from PLEDGE_CHAIN**
   - Reject if old_thr_address not found: `address_not_found`
   - Reject if old address is already `legacy_migrated`: `already_migrated`
   - Reject if old address is `revoked`: `address_revoked`

4. **Verify proof of old ownership**
   - Reconstruct expected HMAC from stored `send_seed_hash`
   - Constant-time compare with submitted `proof`
   - Reject on mismatch: `invalid_credential`

5. **Verify old address has admission**
   - BTC confirmed OR whitelisted
   - Reject if neither: `no_admission`

6. **Check new_v1_address is not already occupied**
   - Reject if new_v1_address already exists in PLEDGE_CHAIN with active status

7. **Create balance migration tx (explicit, auditable)**
   - Load ledger
   - Read `old_balance = ledger[old_thr_address]`
   - Set `ledger[old_thr_address] = 0`
   - Set `ledger[new_v1_address] = old_balance`
   - Save ledger
   - Append migration tx to CHAIN_FILE:
     ```python
     {
       "type": "wallet_v1_migration",
       "from": old_thr_address,
       "to": new_v1_address,
       "amount": old_balance,
       "fee_burned": 0,  # no fee on migration
       "tx_id": f"MIGRATE-{int(time.time())}-{secrets.token_hex(4)}",
       "status": "confirmed",
       "migration_proof_hash": sha256(proof),  # proof digest, not raw proof
       "pledge_hash": pledge_entry["pledge_hash"]
     }
     ```
   - `persist_normalized_tx(tx)`

8. **Bind admission to new_v1_address**
   - Create new PLEDGE_CHAIN entry for `new_v1_address`:
     ```python
     {
       "thr_address": new_v1_address,
       "compressed_public_key": new_compressed_public_key,
       "wallet_v1": True,
       "admission_method": "migrated_from_legacy",
       "migrated_from": old_thr_address,
       "pledge_hash": old_pledge["pledge_hash"],
       "btc_address": old_pledge["btc_address"],
       "migration_tx_id": tx_id,
       "timestamp": now
     }
     ```

9. **Mark old address as legacy_migrated (read-only)**
   - Update old pledge entry:
     ```python
     old_pledge["status"] = "legacy_migrated"
     old_pledge["migrated_to"] = new_v1_address
     old_pledge["migrated_at"] = now
     ```
   - Save PLEDGE_CHAIN

10. **Return migration result**
    - Include: old address, new address, migration tx_id, admission method
    - Never include secrets

---

## 4. Balance Policy

**Decision: Explicit migration transaction (preferred)**

Rationale:
- Provides auditable record in CHAIN_FILE
- Visible in `/api/transfers` for both addresses
- Consistent with production ledger model
- Enables forensic review if dispute arises
- Zero fee (migration, not transfer)

**Alternative considered (rejected):** Bind legacy balance lookup to new address
- Rejected: Creates two ledger entries for same balance
- Rejected: Invisible in `/api/transfers`
- Rejected: Complicates fee calculations and auditing

**Migration tx properties:**
- `type: "wallet_v1_migration"` (distinguishable from transfers)
- `fee_burned: 0` (no network fee on migration)
- `source: "wallet_v1_legacy_migration"`
- Appears in `/api/transfers` for both old and new address

---

## 5. Post-Migration State

### 5.1 Old Address

| Property | After Migration |
|----------|----------------|
| Balance | 0 (transferred to new) |
| Pledge status | `legacy_migrated` |
| Legacy HMAC writes | Rejected: `address_migrated` |
| Wallet V1 writes | Rejected: `address_migrated` |
| Balance reads | Allowed (shows 0) |
| Transfer history | Preserved (shows migration tx) |

### 5.2 New Address

| Property | After Migration |
|----------|----------------|
| Balance | Full balance from old address |
| Pledge status | `migrated_from_legacy` |
| Admission | Inherited from old (btc_confirmed or whitelisted) |
| Wallet V1 writes | Allowed (ECDSA signature required) |
| Legacy HMAC writes | Not applicable (new address has no send_seed) |

---

## 6. Recovery Artifact Update

After migration, the recovery artifact MUST be regenerated:

**Updated recovery metadata (no secrets ever):**

```json
{
  "version": "1.0",
  "wallet_v1": true,
  "chain_id": "thronos-mainnet",
  "thr_address": "THRabc...",
  "compressed_public_key": "02abc...",
  "created_at": "2026-05-21T12:34:56Z",

  "migration": {
    "migrated_from": "THR1716384529123",
    "migration_tx_id": "MIGRATE-...",
    "migrated_at": "2026-05-21T12:34:56Z"
  },

  "pledge_metadata": {
    "btc_address": "1ABC...XYZ",
    "pledge_hash": "sha256(...)",
    "admission_method": "btc_confirmed",
    "pledge_txid": "abc123...",
    "pledge_confirmed_at": "2026-05-21T12:00:00Z"
  },

  "recovery_commitment": {
    "method": "lsb_png",
    "image_hash": "sha256(stego_image)",
    "commitment": "hash(new_compressed_public_key + image_hash + migrated_at)"
  },

  "NEVER_STORE": [
    "privateKey",
    "mnemonic",
    "seed",
    "send_secret",
    "auth_secret",
    "passphrase",
    "send_seed"
  ]
}
```

---

## 7. What Is NOT Permitted

1. **No server-side private key generation** — keypair is always generated client-side
2. **No migration without admission** — old address must have BTC confirmed or whitelist
3. **No double migration** — already-migrated addresses cannot migrate again
4. **No writes from migrated old address** — marked read-only post-migration
5. **No secrets in any response** — privateKey, mnemonic, seed, send_secret, auth_secret, passphrase
6. **No balance binding trick** — explicit migration tx only, no dual-reference
7. **No bypass of old credential check** — proof must be verified before migration proceeds

---

## 8. Whitelisted Address Migration

Whitelisted addresses follow the same migration path with one difference:
- `admission_method: "whitelisted"` instead of `"btc_confirmed"`
- No `pledge_txid` (replaced with whitelist membership proof)
- No `btc_address` required

**Whitelist proof in recovery artifact:**
```json
{
  "pledge_metadata": {
    "admission_method": "whitelisted",
    "whitelist_entry": "confirmed",
    "pledge_txid": null
  }
}
```

---

## 9. Migration Attempt Limits

To prevent abuse:
- Rate limit: 1 migration attempt per old address per 10 minutes
- Maximum attempts: 5 per day per old address (after which old address is locked)
- Failed proof attempts are logged (for audit)
- Migration cannot be reversed once complete

---

## 10. Required Tests (Specification for Future Implementation PR)

### 10.1 Rejection Tests

```python
def test_wrong_send_secret_rejected():
    """
    Migration with incorrect send_secret proof must return 403.
    Old address and balance unchanged.
    """
    result = migrate(old_address, wrong_proof, new_pubkey)
    assert result["error"] == "invalid_credential"
    assert result["status"] == 403
    assert ledger[old_address] == original_balance  # unchanged

def test_unpledged_address_migration_rejected():
    """
    Address with no BTC payment and not whitelisted cannot migrate.
    """
    result = migrate(unpledged_address, correct_proof, new_pubkey)
    assert result["error"] == "no_admission"
    assert result["status"] == 403

def test_already_migrated_cannot_migrate_again():
    """
    Once migrated, old address cannot initiate a second migration.
    """
    migrate(old_address, proof, new_pubkey)  # first migration
    result = migrate(old_address, proof, another_pubkey)  # second attempt
    assert result["error"] == "already_migrated"
    assert result["status"] == 409

def test_migrated_old_address_cannot_write():
    """
    After migration, old address is read-only.
    Both HMAC and Wallet V1 writes from old address rejected.
    """
    migrate(old_address, proof, new_pubkey)

    # Legacy HMAC write attempt
    result = legacy_send(old_address, send_secret, amount=1)
    assert result["error"] == "address_migrated"

    # Wallet V1 write attempt (even with new keypair signed for old address)
    result = wallet_v1_send(old_address, ecdsa_sig, amount=1)
    assert result["error"] == "address_migrated"
```

### 10.2 Acceptance Tests

```python
def test_correct_secret_and_new_pubkey_accepted():
    """
    Correct send_secret + valid new publicKey succeeds.
    """
    result = migrate(old_address, correct_proof, new_pubkey)
    assert result["ok"] is True
    assert result["status"] == "migrated"
    assert result["new_v1_address"] is not None

def test_new_pubkey_derives_to_new_v1_address():
    """
    Returned new_v1_address must be canonically derived from new_compressed_public_key.
    """
    result = migrate(old_address, correct_proof, new_pubkey)
    derived = canonical_derive(new_pubkey)
    assert result["new_v1_address"] == derived

def test_old_admission_transfers_to_new_address():
    """
    After migration, new_v1_address has same admission as old.
    """
    # old_address has btc_confirmed admission
    migrate(old_address, proof, new_pubkey)
    status = get_activation_status(new_v1_address)
    assert status["active"] is True
    assert status["admission_method"] == "migrated_from_legacy"
    assert status["original_admission"] == "btc_confirmed"

def test_whitelisted_old_address_migration_works():
    """
    Whitelisted addresses can migrate to Wallet V1.
    """
    # old_address is whitelisted (not BTC pledged)
    result = migrate(whitelisted_address, proof, new_pubkey)
    assert result["ok"] is True
    status = get_activation_status(result["new_v1_address"])
    assert status["admission_method"] == "migrated_from_legacy"
    assert status["original_admission"] == "whitelisted"

def test_balance_migrated_explicitly():
    """
    Exact balance from old address appears in new address after migration.
    Old address balance becomes 0.
    Migration tx appears in /api/transfers.
    """
    old_balance = get_balance(old_address)  # e.g. 500.0 THR
    result = migrate(old_address, proof, new_pubkey)
    new_v1 = result["new_v1_address"]
    tx_id = result["migration_tx_id"]

    assert get_balance(old_address) == 0
    assert get_balance(new_v1) == old_balance

    # Verify migration tx in transfers
    transfers = get_transfers()
    migration_tx = next(t for t in transfers if t["tx_id"] == tx_id)
    assert migration_tx["type"] == "wallet_v1_migration"
    assert migration_tx["from"] == old_address
    assert migration_tx["to"] == new_v1
    assert migration_tx["fee_burned"] == 0
```

### 10.3 Security Tests

```python
def test_no_secrets_in_migration_response():
    """
    Migration response must never include secrets.
    """
    result = migrate(old_address, correct_proof, new_pubkey)
    forbidden = ["privateKey", "mnemonic", "seed", "send_secret",
                 "auth_secret", "passphrase", "send_seed"]
    for field in forbidden:
        assert field not in result, f"{field} leaked in migration response"

def test_new_wallet_v1_address_can_sign_after_migration():
    """
    After migration, new_v1_address accepts Wallet V1 ECDSA signatures.
    """
    result = migrate(old_address, proof, new_pubkey)
    new_v1 = result["new_v1_address"]

    # Fund new address first (balance was migrated)
    signed_tx = sign_with_private_key(new_privkey, {
        "from": new_v1,
        "to": recipient,
        "amount": 1.0,
        ...
    })
    response = post_wallet_v1_tx(signed_tx)
    assert response["ok"] is True
```

---

## 11. Preservation Rules (Locked In)

| Rule | Status |
|------|--------|
| Existing pledge flow unchanged | ✅ Must not break |
| Legacy HMAC sending works for non-migrated addresses | ✅ Must not break |
| Migration is opt-in, not forced | ✅ Users choose when to migrate |
| Balance preserved exactly during migration | ✅ Required |
| Admission (BTC/whitelist) preserved after migration | ✅ Required |
| Secrets never generated server-side | ✅ Required |
| Old address read-only after migration | ✅ Required |
| Migration tx visible in /api/transfers | ✅ Required |
| Cannot migrate twice | ✅ Required |

---

## 12. What This PR Does NOT Do

- ❌ Modify `server.py`
- ❌ Modify `pledge_submit.py`
- ❌ Modify `wallet_v1_execution_adapter.py`
- ❌ Modify `wallet_v1_handlers.py`
- ❌ Implement migration endpoint
- ❌ Implement recovery artifact regeneration
- ❌ Add tests or test files

**This is design/audit only.**

---

## 13. Future Implementation PRs

**Implementation PR 1: Migration Endpoint**
- `wallet_v1_migration.py` — migration logic module
- `server_ext.py` — register `/api/v1/wallet/migrate` endpoint
- `tests/test_wallet_v1_migration.py` — full test suite

**Implementation PR 2: Activation Check Integration**
- Update `wallet_v1_activation.py` to recognize `migrated_from_legacy` status
- Ensure `require_active_thr_address()` accepts migrated addresses
- Update existing activation tests

**Implementation PR 3: Recovery Artifact**
- Update `secure_pledge_embed.py` to regenerate LSB artifact post-migration
- Include migration metadata (old address, migration tx_id)
- Never include secrets

All implementation PRs will:
- Reference this design document
- Preserve all existing behavior
- Include tests for every specified case
- Be reviewed before merge
