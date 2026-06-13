# Wallet V1 Address Resolution Fix - Critical Production Unlock Fix

## Problem Statement

**Critical Issue**: Users attempting to unlock Wallet V1 with a canonical (mirage) address encounter key mismatch errors even when the correct signing key is present in the recovery kit.

**Root Cause**: When a wallet is pledged, the signing key is created and stored under the legacy pledge address. However, during migration, the canonical V1 address is created. The system failed to recognize that the signing key stored under the legacy address actually belongs to (and should be used by) the canonical address.

**Error Pattern**:
```
[UnlockWallet] No binding registered - key mismatch
wallet_signing_key_does_not_match_active_address KEY_MISMATCH
```

## Solution Architecture

### 1. Bidirectional Address Resolution API

**Endpoint**: `POST /api/wallet/v1/resolve-address`

**Purpose**: Given either a canonical or legacy address, resolve to the other.

**Implementation Details** (server.py, lines 22440-22495):
- Uses `search_all_migration_sources()` for flexible lookups
- Supports searching by legacy address OR canonical address
- Returns migration status, legacy address, canonical address, and signing material indicator
- Normalizes all addresses to uppercase for consistent matching

**Example Requests**:
```bash
# Resolve canonical to legacy
curl -X POST /api/wallet/v1/resolve-address \
  -d '{"address":"THR683318ACF083723B3EDFE6C0A30AD62670F00353"}'

# Resolve legacy to canonical  
curl -X POST /api/wallet/v1/resolve-address \
  -d '{"address":"THR79CA94A7EB70A6AA99D12D7FDB01446EF246301A"}'
```

**Response**:
```json
{
  "ok": true,
  "canonical_v1_address": "THR683318ACF083723B3EDFE6C0A30AD62670F00353",
  "legacy_address": "THR79CA94A7EB70A6AA99D12D7FDB01446EF246301A",
  "migration_status": "confirmed",
  "has_signing_material": true
}
```

### 2. Enhanced Unlock Flow with Address Resolution Fallback

**Location**: static/wallet_session.js, lines 725-801

**Unlock Flow**:

```
1. User attempts unlock with PIN for canonical address
2. Decrypt signing key from localStorage
3. Derive public key and address from decrypted key
4. Check if derived address matches canonical address
   ├─ YES: Standard unlock (direct match)
   └─ NO: Check binding
         ├─ Binding exists: Use bound signer (re-key ceremony case)
         └─ Binding missing: TRY ADDRESS RESOLUTION FALLBACK
             ├─ Call resolve-address API with canonical address
             ├─ If legacy address found:
             │  ├─ Check if derived address matches legacy address
             │  ├─ If match: Create binding and allow unlock
             │  └─ If no match: Fail with appropriate error
             └─ If resolution fails: Fail with final error
```

**Key Logic** (wallet_session.js):
```javascript
// When no direct binding exists, try address resolution
const resolveRes = await fetch('/api/wallet/v1/resolve-address', {
  method: 'POST',
  body: JSON.stringify({ address: activeAddr })
});

// If canonical resolves to legacy
const legacyAddr = resolveData.legacy_address;
if (derivedNormalized === normalizeAddress(legacyAddr)) {
  // Create binding and allow unlock
  await fetch('/api/wallet/v1/bind-public-key', {
    method: 'POST',
    body: JSON.stringify({
      canonical_v1_address: activeAddr,
      public_key: derivedPublicKey,
      bound_key_address: legacyAddr,
      address_resolution_context: 'legacy_to_canonical_migration'
    })
  });
  
  unlockedPrivateKeyHex = decryptedPrivKeyHex;
  unlockedForAddress = activeAddr;
  return true;
}
```

## Migration Record Structure

**File**: `data/wallet_v1_migrations.json`

**Structure**:
```json
{
  "migrations": {
    "LEGACY_ADDRESS_UPPERCASE": {
      "version": 3,
      "old_address": "LEGACY_ADDRESS",
      "new_v1_address": "CANONICAL_ADDRESS",
      "status": "confirmed",
      "has_signing_material": true,
      "verified": true,
      "key_binding_verified": true,
      "recovery_kit_generated": true
    }
  },
  "index_new": {
    "CANONICAL_ADDRESS": "LEGACY_ADDRESS"
  }
}
```

**Critical**: All addresses MUST be uppercase for consistent normalization in search functions.

## Error Handling

**Error Flow**:
1. **Direct Match Success**: Unlock proceeds without binding
2. **Bound Signer Match**: Unlock with known bound key
3. **Address Resolution Success**: Create binding and unlock
4. **All Methods Failed**: Return `wallet_signing_key_does_not_match_active_address` error

**Error Details Include**:
- `error_type`: Specific failure mode (binding_not_registered, binding_check_failed, binding_hash_mismatch, etc.)
- `derived_address`: Address derived from signing key
- `active_address`: Canonical address user attempted to unlock
- `binding_address`: Bound key address if binding exists
- `decrypt_succeeded`: Whether key decryption succeeded

## Testing

**Test Cases**:
1. ✅ Canonical address resolution → legacy address
2. ✅ Legacy address resolution → canonical address  
3. ✅ Bidirectional lookup both directions
4. ✅ Missing address handling (returns 404)
5. ✅ Unlock with legacy key bound to canonical

**Production Validation**:
```
$ curl -X POST http://localhost:8000/api/wallet/v1/resolve-address \
  -H "Content-Type: application/json" \
  -d '{"address":"THR683318ACF083723B3EDFE6C0A30AD62670F00353"}'

{
  "ok": true,
  "canonical_v1_address": "THR683318ACF083723B3EDFE6C0A30AD62670F00353",
  "legacy_address": "THR79CA94A7EB70A6AA99D12D7FDB01446EF246301A",
  "migration_status": "confirmed",
  "has_signing_material": true
}
```

## Files Modified

1. **server.py** (Lines 22440-22495)
   - Added `/api/wallet/v1/resolve-address` endpoint
   
2. **static/wallet_session.js** (Lines 725-801)
   - Enhanced unlock flow with address resolution fallback
   - Checks if derived address matches legacy address
   - Creates binding if match found
   - Allows unlock with legacy signer bound to canonical address

## Expected User Experience

**Before Fix**:
- User imports wallet with canonical address THR683318...
- Attempts unlock → "Key mismatch" error
- Cannot proceed → Wallet locked

**After Fix**:
- User imports wallet with canonical address THR683318...
- Attempts unlock → System detects address mismatch
- Automatically resolves canonical → legacy address
- Validates signing key matches legacy address
- Creates binding for future unlocks
- ✅ Unlock succeeds

**On Subsequent Unlocks**:
- System finds binding directly
- No need for address resolution
- Fast unlock with previously established binding

## Migration Path

1. User attempts unlock with canonical address
2. System fails to find direct binding
3. System calls address resolution API
4. API returns legacy address and migration status
5. System checks if signing key matches legacy address
6. If match: creates binding and completes unlock
7. Future unlocks use the binding directly

## Security Considerations

1. **Binding Creation**: Only created after verification that signing key actually matches the legacy address
2. **One-time Resolution**: Address resolution only happens when binding is missing
3. **Error Transparency**: Clear error messages for debugging without exposing sensitive data
4. **Case Normalization**: All addresses normalized to uppercase to prevent case-sensitivity bugs

## Rollback Plan

If issues arise with address resolution:
1. Endpoint can be disabled by removing route from server.py
2. Unlock will fallback to original error behavior
3. Users can still unlock with direct key matches or existing bindings
4. No data loss - all migration records preserved

## Related Systems

- **wallet_v1_migration.py**: Migration record management
- **wallet_v1_production_final.py**: Wallet state machine
- **wallet_session.js**: Client-side wallet unlock flow
- **public_key_bindings.json**: Stores bound signer relationships
- **wallet_v1_migrations.json**: Legacy↔canonical address mappings

## Commits

- `3d1bb92`: "Implement bidirectional address resolution for Wallet V1 unlock"
  - Added resolve-address API endpoint
  - Enhanced wallet unlock logic with address resolution fallback

