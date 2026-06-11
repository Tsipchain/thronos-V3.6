# Wallet V1 UI Bug - Diagnostic Report

**Status**: Root cause identified + surgical fix plan ready

---

## Phase 1: Diagnostic Findings

### ROOT CAUSE: localStorage Key Mismatch

**The Problem**:
- `hasCanonical()` function checks ONLY `wallet_v1_canonical_address` (line 2699)
- Multiple code paths set `wallet_v1_address` WITHOUT setting `wallet_v1_canonical_address`
- Result: hasCanonical() returns FALSE even when canonical exists in localStorage

### Evidence

**Location 1: hasCanonical() Function**
```
File: templates/base.html
Line: 2699-2701

function hasCanonical() {
    const canonical = localStorage.getItem('wallet_v1_canonical_address');  // ❌ ONLY checks this key
    return !!(canonical && canonical.startsWith('THR') && canonical.length > 10);
}
```

**Issue**: Only checks `wallet_v1_canonical_address`, but production code sometimes sets only `wallet_v1_address`

---

**Location 2: Recovery Kit Restore Path**
```
File: templates/base.html
Line: 3431

localStorage.setItem('wallet_v1_address', canonical);  // ❌ Sets wallet_v1_address
// Missing: localStorage.setItem('wallet_v1_canonical_address', canonical);
```

**Impact**: Restore Kit saves canonical to `wallet_v1_address` but not `wallet_v1_canonical_address`, so hasCanonical() returns false.

---

**Location 3: Admin Signer Key Binding**
```
File: templates/base.html
Line: 7982

localStorage.setItem('wallet_v1_address', canonicalAddr);  // ❌ Sets only wallet_v1_address
// Missing: localStorage.setItem('wallet_v1_canonical_address', canonicalAddr);
```

**Impact**: Same as above - canonical not set to wallet_v1_canonical_address.

---

**Location 4: Correct Path (for reference)**
```
File: templates/base.html
Lines: 7578 + 7588

localStorage.setItem('wallet_v1_canonical_address', canonicalAddr);  // ✅ Sets canonical_address
localStorage.setItem('wallet_v1_address', canonicalAddr);             // ✅ Also sets legacy address
```

**Status**: This path is CORRECT - sets both keys. Used by other restore flows.

---

**Location 5: sanitizeWalletV1ProductionState()**
```
File: templates/base.html
Line: 6140

const canonicalAddr = localStorage.getItem('wallet_v1_address');  // ⚠️ Reads wallet_v1_address
// ...
console.log(..., canonicalAddrPreserved: !!canonicalAddr);
```

**Issue**: Sanitizer checks `wallet_v1_address` to verify canonical preserved, but hasCanonical() checks `wallet_v1_canonical_address`. Mismatch!

---

**Location 6: Where Create Mode is Gated**
```
File: templates/base.html
Line: 6337

const createAllowed = !hasCanonical() && (allowWebCreate || hasPledge);
```

**Logic**: If hasCanonical() returns false (because it doesn't see wallet_v1_canonical_address), then createAllowed becomes TRUE.

```javascript
// Line 6456 - This shows create mode if createAllowed is true
if (createEl) createEl.style.display = (displayMode === 'create' && createAllowed) ? 'block' : 'none';
```

---

## Symptom Reconstruction

**User sees**:
1. ❌ THR Address input shows canonical address (e.g., THRxxxx)
2. ❌ Mode dropdown shows "Unlock Wallet V1" 
3. ❌ But primary button shows "Create Wallet V1" (CTA mismatch)
4. ❌ Dropdown includes "Create Wallet V1" option (should be disabled)
5. ⚠️ Console shows: "canonicalAddrPreserved: false" (but canonical exists in wallet_v1_address!)

**Why this happens**:
1. User restores from Recovery Kit → canonical saved to wallet_v1_address (line 3431)
2. hasCanonical() checks wallet_v1_canonical_address (line 2700) → finds nothing → returns FALSE
3. createAllowed = !hasCanonical() && ... → becomes TRUE (line 6337)
4. UI shows create mode as allowed even though canonical exists
5. Dropdown shows both "Unlock" and "Create" options
6. Mode selector defaults/shows "Unlock" but UI shows "Create Wallet V1" button

---

## All localStorage Keys Involved

| Key Name | Set By | Read By | Issue |
|-----------|--------|---------|-------|
| `wallet_v1_canonical_address` | Lines 7578, 4449 | hasCanonical (2700), imports (7206) | ✅ Canonical key |
| `wallet_v1_address` | Lines 3431, 7588, 7982 | sanitizer (6140), unlock (6728), others | ❌ Legacy key, sometimes ONLY this is set |
| `wallet_v1_active_address` | (not found) | (not checked by hasCanonical) | ⚠️ Potential variant |
| `wallet_v1_encrypted_priv` | Multiple | Sanitizer (6139) | Encryption key |
| `wallet_v1_public_key` | Multiple | (no check) | Public key |
| `thr_address` | Lines 3439, 7989 | (no check by wallet v1) | Legacy compat key |

---

## The Surgical Fix Strategy

**Fix 1**: Make hasCanonical() defensive - check ALL possible keys
```javascript
function hasCanonical() {
    // Check all known canonical address keys
    const canonical = localStorage.getItem('wallet_v1_canonical_address')
        || localStorage.getItem('wallet_v1_address')
        || localStorage.getItem('wallet_v1_active_address');
    return !!(canonical && canonical.startsWith('THR') && canonical.length > 10);
}
```

**Fix 2**: Ensure all setters write BOTH canonical keys
- Line 3431: Add `localStorage.setItem('wallet_v1_canonical_address', canonical);` after line 3431
- Line 7982: Add `localStorage.setItem('wallet_v1_canonical_address', canonicalAddr);` after line 7982
- Sanitizer should migrate: if wallet_v1_address exists but not wallet_v1_canonical_address, copy it

**Fix 3**: Ensure UI respects canonical immutability
- Line 6375: Disable create option if hasCanonical() true
- Line 6456: Never show create div if hasCanonical() true (double-guard)

---

## Files to Patch

| File | Lines | Change |
|------|-------|--------|
| templates/base.html | 2699-2701 | Make hasCanonical() check multiple keys |
| templates/base.html | 3431 | Add wallet_v1_canonical_address setItem |
| templates/base.html | 7982 | Add wallet_v1_canonical_address setItem |
| templates/base.html | 6140 | Optional: migrate keys if needed |

---

## Regression Tests (Must Fail Before Fix, Pass After)

1. **test_hasCanonical_accepts_wallet_v1_address**
   - Set only wallet_v1_address (not wallet_v1_canonical_address)
   - hasCanonical() should return TRUE
   - Currently fails (returns false)

2. **test_create_option_hidden_with_any_canonical_variant**
   - Set wallet_v1_address to canonical
   - switchWalletV1Mode()
   - Create option should be disabled/hidden
   - Currently fails

3. **test_restore_sets_canonical_address_key**
   - Restore from Recovery Kit
   - wallet_v1_canonical_address should be set
   - Currently fails (only wallet_v1_address is set)

4. **test_cta_matches_mode_unlock**
   - Mode dropdown = "Unlock"
   - Primary button text = "Unlock Wallet V1"
   - Currently fails (shows "Create")

---

## Summary Table

| Item | Current Status | Severity |
|------|---|---|
| hasCanonical() checks only wallet_v1_canonical_address | ❌ BUG | HIGH |
| Recovery Kit sets only wallet_v1_address | ❌ BUG | HIGH |
| Admin signer sets only wallet_v1_address | ❌ BUG | HIGH |
| Correct restore path sets BOTH keys | ✅ OK | Reference |
| createAllowed gate uses hasCanonical() | ✅ OK | Correct logic |
| UI hides create div if createAllowed=false | ✅ OK | Correct logic |

---

**Next**: Implement 4 surgical fixes + 4 regression tests

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce
