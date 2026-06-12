# Wallet V1 Pledge → Mirage Flow — Status & Missing Algorithm

## Current Status (Branch: `claude/dreamy-bohr-6j1rO`)

### ✅ Completed Fixes

1. **Post-Pledge Canonical Address Persistence** (`templates/pledge_form.html`)
   - `activateWallet()` now async
   - Explicitly persists canonical address via `walletSession.persistActiveUserAddress()` or direct localStorage
   - Calls `refreshWalletStateFromServer()` + `switchWalletV1Mode()` to re-render UI
   - **Result**: `hasCanonical()` returns true after pledge

2. **Legacy User Activation** (`templates/pledge_form.html`)
   - Changed pledge-success handler to call `activateWallet()` whenever `thr_address` is present
   - **Previously**: only called if fresh `send_secret` was minted (legacy users blocked)
   - **Now**: legacy users (no fresh secret) are activated and canonical is recognized

3. **Mode/CTA Dropdown Mismatch** (`templates/base.html`)
   - Added `reconcileWalletV1ModeCTA()` — deterministic guard ensuring dropdown == visible CTA
   - Disabled `create` option in production (canonical addresses born from pledge, not client-side creation)
   - Allow `unlock` form with no active wallet (returning users type their pledged/mirage address)
   - **Result**: dropdown "Unlock Wallet V1" always shows Unlock form, never Create button

4. **Key Mismatch Recovery Crash** (`templates/base.html`)
   - Fixed undefined `diagnostics` variable in `showKeyMismatchRecovery()`
   - Now uses extracted `derivedAddr` parameter instead

### ⏳ Pending — Requires Algorithm

The complete flow breaks at this point:

```
User pledges BTC
        ↓
Get pledge address: THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a
        ↓
[BLOCKED] Need to derive mirage address: THR683318ACF083723B3EDFE6C0A30AD62670F00353
        ↓
Import Recovery Kit (has mirage address)
        ↓
Unlock with PIN succeeds
```

## Missing: Mirage Derivation Algorithm

### What's Needed

**Endpoint**: `/api/wallet/v1/restore-migration` (POST)

```javascript
// Input
{
  "legacy_address": "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a",  // pledge address
  "migration_proof": ""  // optional: send_secret or migration tx id
}

// Output (success)
{
  "ok": true,
  "canonical_v1_address": "THR683318ACF083723B3EDFE6C0A30AD62670F00353",  // mirage address
  "migration_status": "confirmed",
  "has_signing_material": false
}

// Output (error)
{
  "ok": false,
  "error": "migration_not_found"
}
```

### Where It's Called

**Client-side**: `static/wallet_session.js` line 214
```javascript
const response = await fetch('/api/wallet/v1/restore-migration', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    legacy_address: normalized,
    migration_proof: migrationProof || ''
  })
});
```

**Server-side**: Create endpoint in `server.py`
```python
@app.route("/api/wallet/v1/restore-migration", methods=["POST"])
def api_wallet_v1_restore_migration():
    data = request.get_json() or {}
    legacy_address = (data.get("legacy_address") or "").strip()
    migration_proof = (data.get("migration_proof") or "").strip()
    
    # TODO: Apply mirage derivation algorithm
    # legacy_address (THR79ca...) → mirage_address (THR683...)
    
    canonical_v1_address = derive_mirage(legacy_address, migration_proof)
    
    return jsonify({
        "ok": True,
        "canonical_v1_address": canonical_v1_address,
        "migration_status": "confirmed",
        "has_signing_material": False
    }), 200
```

## How It Will Complete the Flow

Once the algorithm is implemented:

1. User pledges → gets `THR79ca...`
2. `activateWallet()` calls `/api/wallet/v1/restore-migration`
3. Server returns mirage `THR683318A...`
4. Client sets mirage as canonical (via `persistActiveUserAddress()`)
5. Recovery Kit import works (key is for mirage address, canonical matches)
6. Unlock with PIN succeeds
7. User can set additional PIN protection / passkey

## Algorithm Details Needed

The user mentioned: "HMAC → SHA256D"

Please provide:
1. **Input**: What is hashed? (pledge address, send_secret, timestamp, or combination?)
2. **HMAC key**: What's the secret key for HMAC?
3. **Formula**: Exact transformation from pledge address → mirage address
4. **Storage/Lookup**: Is there a migrations.json file, or compute on-demand?

Once you provide this, the endpoint can be completed in ~10 minutes.
