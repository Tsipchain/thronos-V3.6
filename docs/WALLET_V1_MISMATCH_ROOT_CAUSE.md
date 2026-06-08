# Wallet V1 Mismatch Loop - Root Cause Analysis

**Status**: Production Bug - Confirmed  
**Impact**: Users restoring with bound signer keys get "Signing Key Mismatch" error  
**Reproduction**: Restore recovery kit → Enter PIN → See mismatch error  

---

## Symptom

After user restores recovery kit containing a bound signer key:

```
Active Address: THR683318A...  (canonical / identity)
Derived Address: THR767DD58... (from restored key / signer)
Error: "Signing Key Mismatch"
Runtime Material: NO
localStorage: encrypted_key=yes, but no runtime material
```

Expected: Wallet unlocks, runtime material loads, transaction signing works  
Actual: Mismatch error, loop between "Clear Key" and "Import Correct Key"

---

## Root Causes (4 issues)

### 1. Restore Doesn't Unlock Wallet (No Runtime Material)

**Location**: `templates/base.html` lines 7520-7565 (`restoreWalletV1FromRecoveryKit`)

**Current Flow**:
```javascript
// Step 1: Decrypt with PIN
const decrypted = await walletSession.decryptPrivateKeyHex(kit.encrypted_private_key_backup, pin);

// Step 2: Save to localStorage
localStorage.setItem('wallet_v1_encrypted_priv', kit.encrypted_private_key_backup);
localStorage.setItem('wallet_v1_address', kit.canonical_v1_address);

// Step 3: Call updateHeaderWalletUi()
updateHeaderWalletUi();  // ← No unlock happens here!

alert('✓ Recovery kit restored successfully!');
```

**Problem**: 
- Wallet is restored to localStorage but NOT UNLOCKED
- Runtime signing material (`unlockedPrivateKeyHex`) never gets set in walletSession
- User must manually enter PIN again to unlock
- But if derived address != canonical, binding check fails

**Fix**:
- After successful decryption, call `walletSession.unlockWallet({pin, address: canonical})`
- Or load decrypted material directly into `walletSession` before returning

---

### 2. Binding Not Registered in Backend

**Location**: `server.py` lines 36278-36331 (binding endpoints)

**Current Problem**:
- Recovery kit restore writes to localStorage but doesn't register binding with backend
- When unlock happens later, it calls `getActiveKeyBinding(canonical)` 
- Backend has no entry because binding was never registered
- Therefore binding check returns `null` and unlock fails with mismatch

**Example Scenario**:
```
1. User has canonical address: THR683318A...
2. User imports/creates bound signer key for: THR767DD58...
3. Backend binding file SHOULD have:
   {
     "bindings": {
       "THR683318A...": {
         "address": "THR683318A...",
         "public_key_address": "THR767DD58...",
         "bound_at": "...",
         "proof": "legacy_auth_secret"
       }
     }
   }
4. But after recovery kit restore, binding entry is MISSING
5. So getActiveKeyBinding returns null
6. Unlock fails: can't verify binding
```

**Fix**:
- After restore, if kit contains `canonical_v1_address` and public key:
  - Derive the address from the public key
  - If derived != canonical, register binding with backend BEFORE returning
  - Or: restore endpoint should NOT complete until binding is verified/registered

---

### 3. localStorage Key Naming Inconsistency

**Location**: Multiple files

**Current Keys Used**:
```javascript
// templates/base.html (restore)
localStorage.setItem('wallet_v1_address', kit.canonical_v1_address);
localStorage.setItem('wallet_v1_encrypted_priv', kit.encrypted_private_key_backup);
localStorage.setItem('wallet_v1_public_key', publicKey);
localStorage.setItem('wallet_v1_bound_address', kit.bound_key_address);

// static/wallet_session.js (constants)
const V1_ADDRESS_KEY = 'wallet_v1_address';
const V1_ENCRYPTED_KEY = 'wallet_v1_encrypted_priv';
const V1_PUBLIC_KEY = 'wallet_v1_public_key';

// recovery kit structure
kit.canonical_v1_address    // ← Different naming!
kit.encrypted_private_key_backup
kit.bound_key_address
```

**Problem**:
- `canonical_v1_address` in kit vs `wallet_v1_address` in localStorage
- `bound_key_address` in kit vs nothing in walletSession for tracking signer
- Mismatch in naming makes code confusing and error-prone

**Fix**:
- Normalize to single naming convention:
  - `wallet_v1_canonical_address` (identity)
  - `wallet_v1_encrypted_private_key` (encrypted seed)
  - `wallet_v1_public_key` (derived public key)
  - `wallet_v1_bound_signer_address` (optional, for re-key ceremony)
- Update all references across files

---

### 4. Mismatch Error Doesn't Show Binding Status

**Location**: `templates/base.html` lines 6586-6684 (`showKeyMismatchRecovery`)

**Current Logic**:
```javascript
// Line 6617: If binding valid, show "Bound Signer Recognized"
if (isValidBinding) {
  // Show success message
}

// Line 6645-6683: Otherwise show "Signing Key Mismatch (Not Bound)"
// But user doesn't know WHY binding check failed
```

**Problem**:
- Binding check is ASYNC and happens in the UI error handler
- User sees "Signing Key Mismatch" before binding check completes
- If binding endpoint is slow/unreachable, user sees wrong error
- Doesn't clearly explain: "binding not found" vs "wrong key" vs "binding mismatch"

**Fix**:
- Move binding check EARLIER in unlock pipeline
- Before throwing mismatch error in `walletSession.unlockWallet()`
- Return specific error codes: `binding_not_found`, `binding_mismatch`, `key_mismatch`
- UI shows specific recovery message per error type

---

## Fix Strategy (3 PRs)

### PR1: Accept Valid Bound Signers (Mismatch Logic)

**Files**: `static/wallet_session.js`

**Changes**:
1. Binding check already exists (lines 643-655)
2. But error handling could be clearer
3. Add logging to understand why binding check fails
4. Return specific error codes for debugging:
   - `binding_check_failed` (network error)
   - `binding_not_registered` (no entry in backend)
   - `binding_hash_mismatch` (entry exists but derived != bound_key_address)
   - `key_mismatch` (true mismatch, no binding at all)

**Test**:
- Canonical: THR683318...
- Import key that derives to: THR767DD58...
- Verify: With binding registered, unlock succeeds
- Verify: Without binding, error message is clear

---

### PR2: Unlock Wallet After Restore + Normalize Keys

**Files**: `templates/base.html`, `static/wallet_session.js`

**Changes**:
1. After restore decryption, call `walletSession.unlockWallet()`
2. Normalize localStorage key names (migration helper)
3. Ensure restore writes:
   - wallet_v1_canonical_address (identity)
   - wallet_v1_encrypted_private_key (encrypted seed)
   - wallet_v1_public_key (derived public key)
   - wallet_v1_bound_signer_address (if kit contains it)
4. Register binding with backend if needed

**Flow**:
```
1. User: Upload recovery kit + enter PIN
2. Frontend: Decrypt key with PIN
3. Frontend: Derive address from key → get derived address
4. Frontend: Get canonical address from kit
5. If canonical != derived:
   a. Check if binding exists with derived == bound_key_address
   b. If not, register binding with backend
6. Call walletSession.unlockWallet({pin, address: canonical})
7. Verify: runtime material now loaded
8. Success: wallet is UNLOCKED, not just restored
```

**Tests**:
- Restore with canonical == derived (standard case)
- Restore with canonical != derived, binding exists (bound signer case)
- Restore with canonical != derived, binding missing (error case with clear message)
- localStorage has all required keys after restore

---

### PR3: UI Mode/CTA + Production Mode

**Files**: `templates/base.html`

**Changes**:
1. Fix mode selector to show correct buttons per mode
2. Ensure Recovery Kit is PRIMARY when signing key missing (even with LEGACY_REPAIR_UI=0)
3. Add walletV1ResolveSignerIdentity function to unify mismatch/binding checks
4. Fix labels and transitions

**Rules**:
- If canonical address exists + encrypted key missing + runtime material missing:
  - Show Recovery Kit as PRIMARY option
  - Hide other options (don't show "Create New Wallet")
  - Don't show legacy import/migrate options
- If canonical address + encrypted key exists:
  - Show "Unlock Wallet V1" as primary
  - Show "Import Different Key" as secondary
  - Never auto-transition to legacy

---

## Test Cases

### Test 1: Standard Restore (Canonical = Derived)
```
Kit: canonical=THR683318, derived_address=THR683318
Expected: Unlock succeeds, runtime material loads, no mismatch
```

### Test 2: Bound Signer Restore (Canonical ≠ Derived, Binding Registered)
```
Kit: canonical=THR683318, derived_address=THR767DD58
Backend binding: THR683318 → {bound_key_address: THR767DD58, status: active}
Expected: Unlock succeeds, runtime material loads, shows "Bound Signer Recognized"
```

### Test 3: Bound Signer Restore (Canonical ≠ Derived, Binding NOT Registered)
```
Kit: canonical=THR683318, derived_address=THR767DD58
Backend binding: (none)
Expected: Unlock fails, error: "Binding not registered for bound signer"
Recovery: Register binding OR clear key and import correct one
```

### Test 4: Wrong Key Restore (Completely Unrelated Address)
```
Kit: canonical=THR683318, derived_address=THRaaabbbccc (some random key)
Backend binding: (none)
Expected: Unlock fails, error: "Signing key does not match wallet"
Recovery: Clear key and restore with correct kit
```

### Test 5: Production Mode (LEGACY_REPAIR_UI=0)
```
State: canonical address exists, encrypted key missing, runtime material missing
Expected: Recovery Kit shown as PRIMARY, legacy options hidden
```

---

## Verification Checklist

After implementing PR1, PR2, PR3:

- [ ] Standard restore → unlock succeeds immediately
- [ ] Bound signer restore with binding → unlock succeeds with "Recognized" message  
- [ ] Bound signer restore without binding → clear error message
- [ ] Wrong key restore → specific error message
- [ ] localStorage has all 4 keys after restore (canonical, encrypted, public, bound)
- [ ] runtime material (`unlockedPrivateKeyHex`) is set after restore
- [ ] Production mode (LEGACY_REPAIR_UI=0) hides legacy options
- [ ] Mode selector shows correct CTAs for each mode
- [ ] No "Signing Key Mismatch" loop
- [ ] Wallet V1 tests pass (36 tests minimum)

---

## Commits

1. **Commit 1 (PR1)**: Clarify mismatch error messages + binding check logging
2. **Commit 2 (PR2)**: Unlock after restore + normalize localStorage keys
3. **Commit 3 (PR3)**: UI mode/CTA fixes + production mode behavior
