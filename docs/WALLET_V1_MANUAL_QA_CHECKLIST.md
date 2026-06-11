# Manual QA Checklist - Wallet V1 Mismatch Bug Fixes

**Duration**: ~15 minutes  
**Devices**: Desktop (Chrome/Firefox) + Mobile (iOS Safari / Android Chrome)  
**Setup**: Fresh browser, clear cache/cookies, DevTools open

---

## Part 1: Fresh Browser → Pledge → Recovery Kit Restore

### Setup
```javascript
// Open DevTools Console and run:
localStorage.removeItem('wallet_v1_canonical_address');
localStorage.removeItem('wallet_v1_address');
localStorage.removeItem('wallet_v1_encrypted_priv');
localStorage.clear();
location.reload();
```

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Open wallet modal | "No active wallet" state, pledge CTA visible | ⬜ |
| 2 | Click "Go to Pledge" | Navigate to /pledge page | ⬜ |
| 3 | Complete pledge | Get canonical address THR683318... | ⬜ |
| 4 | Return to wallet modal | "Recovery Kit Restore" shown as PRIMARY | ⬜ |
| 5 | Click "Restore from Recovery Kit" | Mode = "restore", Recovery Kit form visible | ⬜ |
| 6 | Upload valid recovery kit JSON | File accepted, no errors | ⬜ |
| 7 | Enter PIN from test kit | Accept button enabled | ⬜ |
| 8 | Click "Restore & Unlock" | API call succeeds, wallet auto-unlocked | ⬜ |
| 9 | Verify no mismatch error | If derived == canonical: unlocks cleanly | ⬜ |
| 10 | Check localStorage | All 4 keys present (canonical, encrypted, public, bound) | ⬜ |
| 11 | Check session TTL | 15-min countdown visible in modal | ⬜ |
| 12 | Close wallet modal | Address visible in header | ⬜ |

**Console Expected**:
```
✓ No errors in console
✓ Logs: [Restore] Wallet unlocked successfully
✓ Logs: Session TTL: 15 min
```

---

## Part 2: Bound Signer Restore (Canonical ≠ Derived with Binding)

### Setup
```javascript
// Test addresses
canonical = 'THR683318ACF083723B3EDFE6C0A30AD62670F00353'
derived_signer = 'THR767DD58E0E04978819932467BB693ACE33886D36'

// Clear and setup
localStorage.clear();
localStorage.setItem('wallet_v1_canonical_address', canonical);
location.reload();
```

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Open wallet modal | Mode = "restore" (primary), import is secondary | ⬜ |
| 2 | Upload recovery kit with derived_signer key | File accepted | ⬜ |
| 3 | Enter correct PIN | Accept button enabled | ⬜ |
| 4 | Click "Restore & Unlock" | Binding check happens (network call visible) | ⬜ |
| 5 | If binding exists + matches | Shows "✓ Bound Signer Recognized" message | ⬜ |
| 6 | Verify unlock succeeds | No mismatch error, runtime material loaded | ⬜ |
| 7 | Check UI message | Canonical: THR683318..., Signer: THR767DD58... | ⬜ |
| 8 | Check session TTL | Starts 15-min countdown | ⬜ |
| 9 | Verify NO mismatch loop | No error pop-ups, wallet is operational | ⬜ |
| 10 | Close modal | Address shows in header | ⬜ |

**Console Expected**:
```
✓ [Restore] Binding check completed: found=true, bound_key_address=THR767DD58...
✓ [UnlockWallet] ✓ Bound signer recognized - unlock accepted
✓ No "Signing Key Mismatch" error
```

---

## Part 3: Bound Signer WITHOUT Binding (Error Case)

### Setup
```javascript
// Same setup but binding NOT registered in backend
canonical = 'THR683318ACF083723B3EDFE6C0A30AD62670F00353'
derived_signer = 'THR767DD58E0E04978819932467BB693ACE33886D36'
// Assume /api/wallet/v1/key-binding/<canonical> returns: {ok: true, binding: null}
```

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Upload recovery kit with unregistered signer | File accepted | ⬜ |
| 2 | Enter correct PIN | Accept button enabled | ⬜ |
| 3 | Click "Restore & Unlock" | Binding check runs, returns null | ⬜ |
| 4 | Verify error message | Shows "⚠️ Bound Signer Not Registered" (NOT generic mismatch) | ⬜ |
| 5 | Check error details | Shows error_type = "binding_not_registered" | ⬜ |
| 6 | Verify recovery options | "Clear This Key" + "Import Correct Key" buttons visible | ⬜ |
| 7 | Click "Clear This Key" | Confirm → key removed from localStorage | ⬜ |
| 8 | Verify address preserved | Canonical address still present | ⬜ |
| 9 | Mode returns to restore | Recovery Kit is still primary option | ⬜ |

**Console Expected**:
```
✓ [UnlockWallet] Binding check completed: found=false
✓ Error type: binding_not_registered
✓ No generic "Signing Key Mismatch" message
```

---

## Part 4: Swap Within Session TTL (No Second PIN)

### Setup
- Complete Part 1 or Part 2 (wallet unlocked, session active)
- Navigate to /swap

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Navigate to /swap | Page loads, wallet state preserved | ⬜ |
| 2 | Check localStorage | canonical_address still present | ⬜ |
| 3 | Select token pair (e.g., THR → USDT) | Pair selected | ⬜ |
| 4 | Enter amount (e.g., 100 THR) | Amount validated | ⬜ |
| 5 | Click "Swap" | API call to /api/swap/execute with signature | ⬜ |
| 6 | Verify request | Has: canonical_v1_address, signature, public_key | ⬜ |
| 7 | No PIN prompt | Uses cached runtime material (no re-auth) | ⬜ |
| 8 | Verify response | 200 OK or 400 (validation error) - NO 500 errors | ⬜ |
| 9 | If swap succeeds | Balance updated, swap recorded | ⬜ |
| 10 | Check console | No ReferenceError, no "loading...", clean logs | ⬜ |

**Network Expected**:
```
✓ POST /api/swap/execute
✓ Status: 200 OK (or 400 with error_code)
✓ No 500 Internal Server Error
✓ Request includes signature + public_key
```

---

## Part 5: Pools → Add Liquidity Within TTL

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Navigate to /pools | Pool list loads | ⬜ |
| 2 | Select a pool | Pool details visible | ⬜ |
| 3 | Enter liquidity amounts | Amounts validated | ⬜ |
| 4 | Click "Add Liquidity" | API call to /api/v1/pools/add (signed) | ⬜ |
| 5 | No PIN prompt | Uses cached runtime material | ⬜ |
| 6 | Verify request | Has signature, public_key, canonical_v1_address | ⬜ |
| 7 | Check response | 200 OK or 400 (validation) - NO 500 | ⬜ |
| 8 | If succeeds | LP token balance updated | ⬜ |

---

## Part 6: Session TTL Expiry (15 min)

### Setup
- Complete Part 1 (wallet unlocked)
- Wait 15 minutes + 1 second (or manually trigger TTL expiry)

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Check TTL countdown | Timer shows 0, session expired message | ⬜ |
| 2 | Try to perform action (swap) | PIN prompt appears, wallet_locked | ⬜ |
| 3 | Check localStorage | canonical_address still present (NOT cleared) | ⬜ |
| 4 | Verify runtime material cleared | unlockedPrivateKeyHex = null | ⬜ |
| 5 | Enter PIN again | Unlock succeeds, new 15-min TTL starts | ⬜ |
| 6 | Perform swap | Works with new session | ⬜ |

---

## Part 7: Production Mode (LEGACY_REPAIR_UI=0)

### Setup
```javascript
// Force production mode
window.WALLET_V1_LEGACY_REPAIR_UI_ENABLED = false;
// Wallet state: has canonical address, NO signing key, NO runtime material
```

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Open wallet modal | Mode selector visible | ⬜ |
| 2 | Check mode options | Visible: restore, create, unlock, import_signing_key | ⬜ |
| 3 | Check hidden options | Hidden: migrate, rekey, admin, legacy_recovery | ⬜ |
| 4 | Check default mode | "restore" is selected/default | ⬜ |
| 5 | Check mode label | Shows "Unlock Method" (not "Mode") | ⬜ |
| 6 | Click restore option | Recovery Kit form visible | ⬜ |
| 7 | Try to select migrate | Option disabled/greyed out | ⬜ |
| 8 | Try to select admin signer | Option disabled/greyed out | ⬜ |

---

## Part 8: Mobile Responsive UX

### Setup
- Open on iOS Safari or Android Chrome
- Use DevTools mobile emulation if needed

### Test Steps
| # | Action | Expected | Status |
|---|--------|----------|--------|
| 1 | Open wallet modal | Modal renders, readable on small screen | ⬜ |
| 2 | Recovery Kit upload | File picker opens (native mobile file selection) | ⬜ |
| 3 | Enter PIN | Mobile keyboard appears, input not obscured | ⬜ |
| 4 | Button sizes | Adequate for touch (not too small) | ⬜ |
| 5 | TTL countdown | Visible and readable on small screen | ⬜ |
| 6 | Error messages | Clear and actionable on mobile view | ⬜ |

---

## Part 9: Error Handling & Edge Cases

| # | Scenario | Expected | Status |
|---|----------|----------|--------|
| 1 | Wrong PIN | Error message shown, no 500 | ⬜ |
| 2 | Invalid JSON recovery kit | Parse error message "Invalid JSON" (400) | ⬜ |
| 3 | Malformed address | Error "Invalid address format" (400) | ⬜ |
| 4 | Network error during restore | Graceful error message, allow retry | ⬜ |
| 5 | Multiple rapid swaps | All signed correctly, no race condition | ⬜ |
| 6 | Concurrent wallet modals | Only one modal at a time | ⬜ |
| 7 | Browser sleep (mobile) | Session TTL paused, resumed on wake | ⬜ |
| 8 | Clear localStorage manually | Address cleared, recovery required | ⬜ |

---

## Final Verification

### Console Checks
```javascript
// Run in DevTools Console:

console.log('=== FINAL VERIFICATION ===');

// 1. localStorage keys
const keys = Object.keys(localStorage);
console.log('localStorage keys:', keys);

// 2. Check normalized keys exist
const canonical = localStorage.getItem('wallet_v1_canonical_address');
const encrypted = localStorage.getItem('wallet_v1_encrypted_private_key');
const publicKey = localStorage.getItem('wallet_v1_public_key');
console.log('Normalized keys:', { canonical: !!canonical, encrypted: !!encrypted, publicKey: !!publicKey });

// 3. Legacy compat
const legacyAddr = localStorage.getItem('wallet_v1_address');
const legacyEnc = localStorage.getItem('wallet_v1_encrypted_priv');
console.log('Legacy keys (compat):', { legacyAddr: !!legacyAddr, legacyEnc: !!legacyEnc });

// 4. Session state
if (window.walletSession) {
  console.log('Session state:', {
    isBound: window.walletSession.isBound?.(),
    isLocked: window.walletSession.isLocked?.(),
    hasRuntimeMaterial: !!window.walletSession.hasRuntimeSigningMaterial?.(),
    ttlRemaining: window.walletSession.getSessionTimeRemaining?.()
  });
}

// 5. No errors in console
console.log('Console errors: check above ↑');
```

**Expected Output**:
```javascript
localStorage keys: ['wallet_v1_canonical_address', 'wallet_v1_encrypted_private_key', 'wallet_v1_public_key', ...]
Normalized keys: {canonical: true, encrypted: true, publicKey: true}
Legacy keys (compat): {legacyAddr: true, legacyEnc: true}
Session state: {isBound: true, isLocked: false, hasRuntimeMaterial: true, ttlRemaining: 899xxx}
Console errors: (none - all clean)
```

---

## Sign-Off

| Item | Pass | Notes |
|------|------|-------|
| Part 1: Pledge → Restore → Unlock | ⬜ | Fresh → Restored → Unlocked |
| Part 2: Bound signer WITH binding | ⬜ | "Bound Signer Recognized" |
| Part 3: Bound signer WITHOUT binding | ⬜ | Clear error message |
| Part 4: Swap within TTL | ⬜ | No PIN prompt, works |
| Part 5: Pools add within TTL | ⬜ | Works without re-auth |
| Part 6: Session TTL expiry | ⬜ | Lock + re-unlock works |
| Part 7: Production mode | ⬜ | Recovery Kit primary, legacy hidden |
| Part 8: Mobile responsive | ⬜ | Usable on small screens |
| Part 9: Error handling | ⬜ | 400 errors, no 500s |
| Final verification | ⬜ | Console checks pass |

---

**Tester**: ________________  
**Date**: ________________  
**Overall Result**: ☐ PASS  ☐ FAIL

**Issues Found**:
```
[List any bugs or issues here]
```

**Sign-Off Comments**:
```
[Any notes or observations]
```
