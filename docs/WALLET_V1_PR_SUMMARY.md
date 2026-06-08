# Wallet V1 Bound Signer Acceptance - PR Summary

**Status**: Ready for Review and Testing  
**Target Branch**: `claude/dreamy-bohr-6j1rO`  
**Related Issue**: Production bug - "Signing Key Mismatch" loop after restore  

---

## Overview

Three surgical PRs to fix the Wallet V1 mismatch loop bug where users restoring with a bound signer key get stuck in a "Signing Key Mismatch" error state, unable to unlock their wallet.

### Root Cause
1. **Restore doesn't unlock wallet** - saved to localStorage but runtime material not loaded
2. **Binding not registered** - backend binding file missing entries for restored bound signers
3. **localStorage keys inconsistent** - different naming conventions between restore and wallet_session
4. **Mismatch error unclear** - doesn't distinguish "wrong key" from "binding not found"
5. **Recovery Kit hidden in production** - legacy repair UI logic hides restore option incorrectly

---

## PR Details

### PR1: Clarify Mismatch Logic and Binding Status (Commit: 9454030)

**File**: `static/wallet_session.js`, `templates/base.html`

**Changes**:
- Enhanced binding verification with detailed logging
- Return specific error types: `binding_not_registered`, `binding_hash_mismatch`, `binding_check_failed`
- Updated UI error handler to show error-specific recovery messages
- Distinguish between "binding not registered" vs "true mismatch"

**Key Code**:
```javascript
// unlockWallet binding check now distinguishes error types
if (binding && binding.bound_key_address && derivedNormalized === normalizeAddress(binding.bound_key_address)) {
  // Binding exists and matches - unlock accepted
  console.info('[UnlockWallet] ✓ Bound signer recognized - unlock accepted');
  return true;
} else if (bindingCheckErr) {
  err.error_type = 'binding_check_failed';
} else if (binding && binding.bound_key_address) {
  err.error_type = 'binding_hash_mismatch';
} else {
  err.error_type = 'binding_not_registered';
}
```

**Impact**:
- Users see clearer error messages
- Easier debugging of binding issues
- Foundation for PR2 automatic binding registration

---

### PR2: Unlock Wallet After Restore + Normalize Keys (Commit: f08a36b)

**Files**: `templates/base.html`, `static/wallet_session.js`

**Changes**:
- After recovery kit decryption, derive public key and address
- Register binding with backend if derived != canonical
- Call `walletSession.unlockWallet()` to load runtime material
- Normalize localStorage keys:
  - `wallet_v1_canonical_address` (identity)
  - `wallet_v1_encrypted_private_key` (encrypted seed)
  - `wallet_v1_public_key` (derived public key)
  - `wallet_v1_bound_signer_address` (optional, re-key ceremony)
- Keep legacy keys for backwards compatibility
- Add `deriveAddressFromPrivateKey()` utility function

**Key Code**:
```javascript
// After restore decryption
const decrypted = await walletSession.decryptPrivateKeyHex(kit.encrypted_private_key_backup, pin);

// Derive address from key
const result = await walletSession.deriveAddressFromPrivateKey(decrypted);
derivedAddr = result.address;
publicKeyHex = result.public_key;

// Save normalized keys
localStorage.setItem('wallet_v1_canonical_address', canonicalAddr);
localStorage.setItem('wallet_v1_encrypted_private_key', kit.encrypted_private_key_backup);
localStorage.setItem('wallet_v1_public_key', publicKeyHex);

// Register binding if needed
if (derivedAddr !== canonicalAddr) {
  await fetch('/api/v1/wallet/bind_public_key', {
    method: 'POST',
    body: JSON.stringify({
      address: canonicalAddr,
      credential_lookup_address: canonicalAddr,
      public_key: publicKeyHex
    })
  });
}

// Unlock wallet to load runtime material
const unlocked = await walletSession.unlockWallet({ pin, address: canonicalAddr });
```

**Impact**:
- Wallet now UNLOCKED after restore, not just restored
- Runtime material immediately available
- No need to enter PIN twice
- Binding automatically registered
- All state consistent (canonical + encrypted + runtime)

---

### PR3: Fix UI Mode/CTA and Production Mode (Commit: dccd361)

**File**: `templates/base.html`

**Changes**:
- Fix `applyWalletV1ProductionMode()` to NOT hide Recovery Kit
  - Restore (Recovery Kit) is PRIMARY feature, not legacy
  - Only hide: migrate, rekey, admin features, legacy recovery
- Update `switchWalletV1Mode()` to prioritize restore when wallet lacks signing key
  - Replace `isLockedImportOnly` with `hasNoSigningKey`
  - Show restore + import options, default to restore
  - Update mode label: "Unlock Method" when no signing key

**Key Code**:
```javascript
// In applyWalletV1ProductionMode:
// NOTE: walletV1RestoreMode is Recovery Kit restore - KEEP IT VISIBLE
// Only hide legacy/admin features
const legacyValues = ['migrate', 'legacy', 'rekey'];  // Removed 'restore'

// In switchWalletV1Mode:
if (hasNoSigningKey) {
  // Recovery Kit (restore) is PRIMARY, import is secondary
  if (restoreOption) restoreOption.disabled = false;  // Always available
  if (importOption) importOption.disabled = false;    // Secondary option
  mode = 'restore';  // Default to restore
}

// Update label
if (hasNoSigningKey && modeLabel) {
  modeLabel.textContent = 'Unlock Method';
}
```

**Impact**:
- Users in production mode can restore via Recovery Kit
- Recovery Kit shown as primary recovery path
- No hidden options in production deployments
- Clearer UX (label changes to "Unlock Method")

---

## Test Coverage

### Test File: `tests/test_wallet_v1_bound_signer_acceptance.py`

Comprehensive test suite covering:
1. Standard restore (canonical == derived)
2. Bound signer with binding registered
3. Bound signer without binding (error case)
4. Wrong key restore (mismatch case)
5. Error type specificity (PR1)
6. localStorage key normalization (PR2)
7. Runtime material loading (PR2)
8. Production mode Recovery Kit visibility (PR3)
9. Mode UI transitions (PR3)
10. Binding endpoints (backend)
11. Regression tests (no mismatch loop)

**Run tests**:
```bash
pytest tests/test_wallet_v1_bound_signer_acceptance.py -v
python tests/test_wallet_v1_bound_signer_acceptance.py  # Direct run
```

---

## Verification Checklist

### Pre-Production Testing

- [ ] **Scenario 1**: Standard restore (canonical == derived)
  - Upload recovery kit → Enter PIN → Verify unlock succeeds without mismatch error
  - Check: localStorage has all 4 normalized keys
  - Check: Runtime material (`unlockedPrivateKeyHex`) loaded

- [ ] **Scenario 2**: Bound signer restore with binding
  - Canonical: `THR683318...`, Derived: `THR767DD58...`
  - Backend binding exists with `bound_key_address == THR767DD58...`
  - Upload recovery kit → Enter PIN → Verify unlock shows "Bound Signer Recognized"
  - Check: No mismatch error loop
  - Check: Runtime material loaded

- [ ] **Scenario 3**: Bound signer without binding
  - Canonical: `THR683318...`, Derived: `THR767DD58...`
  - Backend has NO binding
  - Upload recovery kit → Enter PIN → Verify specific error: "Binding not registered"
  - Check: Clear error message, not generic "Mismatch"
  - Check: Recovery options shown

- [ ] **Scenario 4**: Wrong key restore
  - Canonical: `THR683318...`, Derived: `THRaaabbb...` (completely different)
  - Upload recovery kit → Enter PIN → Verify error: "Signing key does not match wallet"
  - Check: Clear that this is true mismatch, not a binding issue

- [ ] **Scenario 5**: Production mode (LEGACY_REPAIR_UI=0)
  - Wallet state: has canonical address, no encrypted key, no runtime material
  - Verify: Restore option visible in mode selector
  - Verify: Restore is default/selected option
  - Verify: Migrate/ReKey/Admin options hidden
  - Verify: Mode label shows "Unlock Method"

### Regression Testing

- [ ] **No mismatch loop**: With binding, restore → unlock succeeds (not error loop)
- [ ] **localStorage consistency**: All 4 keys present after restore
- [ ] **Runtime material**: Present after restore (not just saved to localStorage)
- [ ] **Session TTL**: 15-minute countdown starts after unlock
- [ ] **Backwards compatibility**: Legacy key names still work
- [ ] **Wallet V1 tests**: Existing 36 tests still pass

---

## Commits

| # | Commit | Message |
|---|--------|---------|
| 1 | `9454030` | fix(wallet-v1): clarify mismatch logic and binding status messages |
| 2 | `f08a36b` | fix(wallet-v1): unlock wallet after restore + normalize localStorage keys |
| 3 | `dccd361` | fix(wallet-v1): fix UI mode/CTA labels and production mode behavior |

---

## Files Changed

**PR1**:
- `static/wallet_session.js` (+60 lines) - Enhanced binding check with error types
- `templates/base.html` (+50 lines) - Updated error handler UI
- `docs/WALLET_V1_MISMATCH_ROOT_CAUSE.md` (new) - Root cause analysis

**PR2**:
- `templates/base.html` (+100 lines) - Unlock after restore + register binding
- `static/wallet_session.js` (+15 lines) - Add `deriveAddressFromPrivateKey()`

**PR3**:
- `templates/base.html` (+50 lines) - Production mode fix + mode UI updates

**Tests**:
- `tests/test_wallet_v1_bound_signer_acceptance.py` (new) - Comprehensive test suite

---

## Deployment Notes

### Staging Testing
1. Deploy PRs to staging environment
2. Run test suite: `pytest tests/test_wallet_v1_bound_signer_acceptance.py -v`
3. Manual test all 5 scenarios
4. Verify no regressions in existing Wallet V1 functionality

### Production Deployment
1. Review code + test results
2. Merge to `main` branch
3. Deploy to production
4. Monitor: Check logs for wallet recovery/restore errors
5. Monitor: Verify no increase in "Signing Key Mismatch" errors

### Rollback Plan
If issues found in production:
1. Revert commits 9454030, f08a36b, dccd361
2. Users can still restore via legacy import (fallback)
3. No wallet data lost (localStorage preserved)

---

## Related PRs

- **#614**: Swap signing unified (Wallet V1 baseline)
- **#615**: Pools signing (Phase 1 - follows this PR)
- **#616+**: Other service migrations (Phase 2-3)

---

## Future Work

After this PR is merged:
- [ ] PR #615: Extend fixes to Pool operations (add/remove/create)
- [ ] PR #616: Extend fixes to Send TXN operation
- [ ] PR #617-#629: Extend to Music tips, L2E, University, Bridge, NFT, AI, IoT, Gaming, DAO, Data
- [ ] Passkey/WebAuthn roadmap (WALLET_V1_PASSKEY_PLAN.md, Q3 2026)

---

## Questions / Contact

For questions on implementation, testing, or deployment:
1. Check docs/WALLET_V1_MISMATCH_ROOT_CAUSE.md for detailed analysis
2. Review test cases in tests/test_wallet_v1_bound_signer_acceptance.py
3. Check PR commits for line-by-line changes
