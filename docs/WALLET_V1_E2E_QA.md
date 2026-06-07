# Wallet V1 E2E QA Checklist - Manual Testing

## Pre-Test Setup

### Environment
- [ ] Staging environment deployed (PR #614 merged)
- [ ] Clear browser cache/cookies (Cmd+Shift+Delete or Ctrl+Shift+Delete)
- [ ] Open DevTools (F12) - check for console errors
- [ ] Network tab open - monitor API calls

### Test Devices
- [ ] Desktop (Chrome/Firefox/Safari)
- [ ] Mobile (iOS Safari / Android Chrome) - *if available*
- [ ] No active wallet in localStorage before tests

---

## Test Scenario 1: Fresh Browser → Pledge → Recovery Kit Restore

### Setup
```javascript
// Clear all wallet state
localStorage.removeItem('canonical_v1_address');
localStorage.removeItem('wallet_v1_encrypted_priv');
localStorage.clear();
// Refresh page
location.reload();
```

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Open wallet modal (click wallet icon) | Modal opens, no ReferenceError | ⬜ | Check console for JS errors |
| 2 | Observe initial state | "no_active_wallet" state visible, pledge CTA shown | ⬜ | Should NOT show "loading..." |
| 3 | Click "Go to Pledge" or equivalent | Navigate to /pledge page | ⬜ | User gets canonical address after pledge |
| 4 | Complete pledge (or use test account with address) | Address returned, stored in localStorage | ⬜ | Address should be canonical THR... format |
| 5 | Return to wallet modal (click icon) | Modal shows "Recovery Kit Restore" as PRIMARY | ⬜ | Other options hidden/disabled |
| 6 | Upload Recovery Kit (test file) | File picker opens, accepts .json | ⬜ | Verify MIME type is JSON |
| 7 | Enter PIN (from test kit) | Accept button enabled, ready to submit | ⬜ | Should validate PIN format (4-8 digits) |
| 8 | Click "Restore & Unlock" | API call to /api/wallet/v1/<restore endpoint> | ⬜ | Check network tab for request |
| 9 | Observe signing material unlocked | Session TTL timer starts (15 min countdown visible) | ⬜ | Runtime material in memory, not stored |
| 10 | Close modal | Modal closes, wallet icon shows canonical address (short) | ⬜ | Address persists, TTL continues |

**Pass Criteria**: All 10 steps complete without errors, session TTL starts

---

## Test Scenario 2: Swap Within Session TTL (No Second PIN)

### Precondition
- Wallet unlocked from Scenario 1
- Within 15-minute session window

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Navigate to /swap | Page loads, wallet state preserved | ⬜ | Check localStorage canonical_v1_address still present |
| 2 | Select tokens (e.g., THR → USDT) | Token pair selected | ⬜ | No wallet modal re-prompt |
| 3 | Enter swap amount (e.g., 100 THR) | Amount validated | ⬜ | No network error from status fetch |
| 4 | Click "Swap" | API call to /api/swap/execute (signed request) | ⬜ | Check request has signature, public_key, action |
| 5 | Verify signature format | Request includes: canonical_v1_address, signature, public_key | ⬜ | No "Sign with PIN" prompt (runtime material used) |
| 6 | Observe swap result | 200 response, swap executed OR 400 with error_code | ⬜ | **NO 500 ERRORS** allowed |
| 7 | If swap succeeds: check balance | USDT balance updated, THR decreased | ⬜ | Verify blockchain state |
| 8 | Check console | No errors, no ReferenceError, no "loading..." | ⬜ | Clean console logs |

**Pass Criteria**: Swap executes without second PIN prompt, no 500 errors

---

## Test Scenario 3: Pools - Add Liquidity Within TTL

### Precondition
- Same wallet unlocked from Scenario 1
- Session TTL still active (< 15 min)

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Navigate to /pools | Pool list loads | ⬜ | Wallet state preserved |
| 2 | Select a pool (or create new) | Pool details shown | ⬜ | No wallet re-prompt |
| 3 | Enter liquidity amounts | Amounts validated | ⬜ | No "loading..." status |
| 4 | Click "Add Liquidity" | API call to /api/v1/pools/add (signed) | ⬜ | Check request signature |
| 5 | Verify NO PIN prompt | Transaction signed with cached material | ⬜ | Within TTL: no re-auth |
| 6 | Observe result | 200 response, liquidity added OR 400 | ⬜ | No 500 errors |
| 7 | Check LP token balance | LP tokens received | ⬜ | On-chain verification |

**Pass Criteria**: Add liquidity without PIN prompt, within TTL

---

## Test Scenario 4: Session TTL Expiry (15 min)

### Setup
- Complete Scenario 1 (unlock wallet)
- Wait 15 minutes 01 second (or simulate by forcing expiry)

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Check TTL countdown | Timer should show 0 or re-auth message | ⬜ | Session expired |
| 2 | Try to perform action (swap/send) | PIN prompt appears (wallet_locked_reunlock_required) | ⬜ | No cached material used |
| 3 | Close modal | Address still in localStorage (NOT cleared) | ⬜ | Canonical address persists |
| 4 | Verify runtime material cleared | localStorage does NOT contain wallet_v1_encrypted_priv | ⬜ | Only encrypted key cleared, address kept |
| 5 | Enter PIN again | Accept PIN, unlock succeeds | ⬜ | New 15-min session starts |
| 6 | Perform swap | Works again with new TTL | ⬜ | Session re-starts |

**Pass Criteria**: TTL enforced, address persists, runtime material cleared, re-unlock works

---

## Test Scenario 5: Wrong PIN / Wrong Recovery Kit

### Precondition
- Fresh browser state

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Upload Recovery Kit | File accepted | ⬜ | |
| 2 | Enter WRONG PIN | Error message shown (4-8 digit mismatch) | ⬜ | **Not a 500 error** |
| 3 | Verify error code | {ok: false, error: 'invalid_pin'} or similar | ⬜ | Check network tab response |
| 4 | Try again with CORRECT PIN | Unlock succeeds | ⬜ | No lockout after 1 failure |
| 5 | (Optional) Upload WRONG Recovery Kit | Error: 'invalid_recovery_kit' or 'decryption_failed' | ⬜ | Clear error message |
| 6 | Verify NO 500 errors | All errors are 400 with descriptive code | ⬜ | User-friendly, not server crashes |

**Pass Criteria**: Wrong inputs → 400 errors, helpful messages, no 500s

---

## Test Scenario 6: Signing Key Mismatch (Advanced)

### Precondition
- Wallet with mismatched signing key (encrypted key doesn't derive canonical address)

### Steps (if applicable)

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Open wallet modal | "Signing key mismatch detected" or recovery UI | ⬜ | State machine shows recovery option |
| 2 | Show mismatch details | Short addresses shown (no secrets) | ⬜ | Privacy: show THR6... not full key |
| 3 | Option: Import correct key | Recovery Kit upload/paste form | ⬜ | Alternative path to fix |
| 4 | Option: Clear bad key | Button "Clear signing key" available | ⬜ | Force re-import next time |
| 5 | Click clear | Key removed, Recovery Kit becomes PRIMARY | ⬜ | Back to Scenario 1 flow |

**Pass Criteria**: Mismatch detected, recovery options clear, no secrets leaked

---

## Test Scenario 7: Music Page - Wallet State Stability

### Precondition
- Wallet unlocked

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Navigate to /music | Page loads, wallet state persists | ⬜ | Address still canonical |
| 2 | Click on artist profile | Detail page loads | ⬜ | No modal disruption |
| 3 | Click "Tip Artist" (e.g., 1 USDT) | Tip modal appears | ⬜ | Wallet state unchanged |
| 4 | Perform tip transaction | Sign with V1 (no PIN within TTL) | ⬜ | Uses cached material |
| 5 | Observe tip success | Balance updated, tip recorded | ⬜ | On-chain visible |
| 6 | Navigate back to music list | Page stable, previous state preserved | ⬜ | No crashes, no infinite loops |
| 7 | Check console | No wallet-related errors or state leaks | ⬜ | Clean logs |

**Pass Criteria**: Music page works with V1, state stable, no UI corruption

---

## Test Scenario 8: Refresh Behavior

### Precondition
- Wallet unlocked, performing actions

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Unlock wallet (PIN or kit) | Session established, runtime material in memory | ⬜ | |
| 2 | Refresh page (F5 or Cmd+R) | Page reloads | ⬜ | |
| 3 | Check wallet state after refresh | Canonical address recovered (from localStorage) | ⬜ | Address persists |
| 4 | Verify runtime material cleared | NO signing happens without PIN | ⬜ | TTL/session ended |
| 5 | Try to swap | PIN prompt appears (locked) | ⬜ | Runtime material properly cleared |
| 6 | Enter PIN again | Unlock succeeds, new session TTL starts | ⬜ | No state corruption |

**Pass Criteria**: Refresh clears runtime material, address persists, re-unlock works

---

## Test Scenario 9: Responsive/Mobile UX

### Precondition
- Mobile device (iOS/Android) or DevTools mobile emulation

### Steps

| # | Action | Expected | Status | Notes |
|---|--------|----------|--------|-------|
| 1 | Open wallet modal (mobile view) | Modal renders, readable on small screen | ⬜ | No overflow, text visible |
| 2 | Recovery Kit upload | File picker opens (mobile file selection) | ⬜ | Works on iPhone/Android |
| 3 | Enter PIN (mobile keyboard) | Keyboard appears, numbers visible | ⬜ | Input not obscured |
| 4 | Swap (mobile view) | Button sizes adequate for touch | ⬜ | No accidental clicks |
| 5 | TTL countdown (mobile) | Timer visible and readable | ⬜ | Font size OK |
| 6 | Session expiry message | Message clear on small screen | ⬜ | Actionable (PIN button) |

**Pass Criteria**: Mobile UX usable, no layout breaks

---

## Test Scenario 10: Error States & Edge Cases

| # | Scenario | Expected | Status | Notes |
|---|----------|----------|--------|-------|
| 1 | No internet connection | Graceful error "Fetch failed" | ⬜ | Safe default applied |
| 2 | API returns 500 (simulated) | Display error to user (no silent hang) | ⬜ | Show message, allow retry |
| 3 | Malformed Recovery Kit JSON | Parse error message "Invalid JSON" | ⬜ | 400, not 500 |
| 4 | Multiple rapid swaps | All signed correctly, no race condition | ⬜ | TTL/nonce handling correct |
| 5 | Concurrent open modals | Only one wallet modal at a time | ⬜ | No state collision |
| 6 | Browser going to sleep (mobile) | Session TTL paused, resumed on wake | ⬜ | Timer syncs to server |
| 7 | Switching networks (if applicable) | Re-fetch wallet status with address | ⬜ | Helper used |
| 8 | Clearing localStorage manually | Address cleared, recovery required | ⬜ | No phantom state |

**Pass Criteria**: Edge cases handled gracefully, no 500s or crashes

---

## Network/API Verification

### /api/wallet/v1/status Calls

- [ ] Called with `?address=THR...` query parameter (never bare)
- [ ] Not called if address is missing (safe default used)
- [ ] Response: `{ok: true/false, legacy_repair_ui_enabled: bool}`
- [ ] Error: 400 "Missing address parameter" (if caller omits it)

### /api/swap/execute Calls

- [ ] Request includes: canonical_v1_address, signature, public_key, action, payload
- [ ] Response: 200 (success) or 400 (validation error) - **NO 500s**
- [ ] Error codes: invalid_signature, insufficient_balance, etc.

### Session/TTL Behavior

- [ ] TTL starts at unlock, counts down 15 min
- [ ] After 15 min: next action requires PIN
- [ ] PIN re-entry starts new 15-min TTL
- [ ] Address persists across refreshes
- [ ] Runtime material cleared on TTL expiry or refresh

---

## Sign-Off Checklist

| Item | Pass? | Tester | Date |
|------|-------|--------|------|
| Scenario 1: Fresh → Pledge → Kit | ⬜ | | |
| Scenario 2: Swap within TTL | ⬜ | | |
| Scenario 3: Pools add within TTL | ⬜ | | |
| Scenario 4: TTL expiry behavior | ⬜ | | |
| Scenario 5: Wrong PIN/Kit errors | ⬜ | | |
| Scenario 6: Signing mismatch (if relevant) | ⬜ | | |
| Scenario 7: Music stability | ⬜ | | |
| Scenario 8: Refresh behavior | ⬜ | | |
| Scenario 9: Mobile/responsive | ⬜ | | |
| Scenario 10: Edge cases | ⬜ | | |
| Network calls verified | ⬜ | | |
| No 500 errors observed | ⬜ | | |
| Console clean (no errors) | ⬜ | | |

---

## Final Verification

```javascript
// Run in DevTools Console after all tests:

console.log('=== WALLET V1 QA FINAL CHECKS ===');
console.log('localStorage keys:', Object.keys(localStorage));
console.log('Canonical address:', localStorage.getItem('canonical_v1_address'));
console.log('Has encrypted key:', !!localStorage.getItem('wallet_v1_encrypted_priv'));
console.log('Runtime material (session only):', window.walletSession?.isBound?.());
console.log('Session TTL remaining:', window.walletSession?.getSessionTimeRemaining?.());
console.log('=== All checks complete ===');
```

**Expected Output**:
- canonical_v1_address: `THR...` (present)
- wallet_v1_encrypted_priv: (present, encrypted)
- isBound(): false (runtime cleared) or true (still in session)
- No errors in console

---

## Approval & Deployment

**Manual QA Pass**: ✅ All 10 scenarios + edge cases + network verified  
**Tester Name**: ________________  
**Date**: ________________  
**Ready for Production**: [ ] YES [ ] NO

**Sign-off Comments**:
```
[Include any issues found, workarounds, or notes]
```

---

**PR #614 Deployment**: After manual QA approval → Merge → Deploy to production

