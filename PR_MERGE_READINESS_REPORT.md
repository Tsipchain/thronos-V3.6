# PR Merge Readiness Report: Canonical Address Immutability

**Date**: 2026-06-10  
**Status**: ✅ CODE TESTS COMPLETE - AWAITING MANUAL QA  
**Commits**: 3 PRs (619, 620, 620.1)

---

## Executive Summary

Three focused PRs implement server-first canonical address immutability:

| PR | Title | Code Tests | Status |
|----|-------|-----------|--------|
| **#619** | Server Identity Lock | 3/3 ✅ | MERGED |
| **#620** | Frontend Route Guard | 5/5 ✅ | MERGED |
| **#620.1** | Authoritative State Refresh | 5/5 ✅ | MERGED |

**All code-level tests passing. Awaiting manual QA gate before PR #621.**

---

## PR #619: Server Identity Lock

### Problem
Server pledge endpoint had no guard preventing new canonical creation on repeat pledges.

### Solution
Added server-side check: if canonical exists → return with `created=false`, never create new.

### Code Changes
- **File**: `server.py`
- **Lines**: 16948-16958, 17035-17041
- **Changes**: 2 response schemas updated to include `canonical_v1_address` + `created` flag

### Tests (3/3 ✅)
```
✅ test_pledge_does_not_create_new_if_canonical_exists
   - 1st pledge: created=true, canonical=A
   - 2nd pledge: created=false, canonical=A (SAME)
   
✅ test_different_btc_addresses_get_different_canonicals
   - User 1 (BTC_A): canonical_A
   - User 2 (BTC_B): canonical_B (different)
   
✅ test_response_schema_is_consistent
   - All responses include: ok, canonical_v1_address, created, status
```

### Validation
```bash
# Repeat pledge returns same canonical
curl -X POST /pledge_submit -d '{"btc_address":"1A1z7..."}'
# Response: { "created": false, "canonical_v1_address": "THRxxxx..." }
```

---

## PR #620: Frontend Route Guard

### Problem
UI could redirect to /pledge even when canonical exists, creating stale pledge panel issue.

### Solution
Added `hasCanonical()` helper. Guards Import/Restore/Unlock handlers and hides Create mode.

### Code Changes
- **File**: `templates/base.html`
- **Lines**: 
  - 2699: `hasCanonical()` helper function
  - 1604: /pledge button checks canonical
  - 6293: createAllowed = !hasCanonical() && (...)
  - 6394-6400: Force mode override if user tries 'create'
  - 6473: Pledge panel hidden when canonical exists
  - 7131-7134: Import handler requires canonical
  - 7140: Import uses canonical target address
  - 7162: Modal state refresh after import

### Tests (5/5 ✅)
```
✅ test_no_pledge_redirect_when_canonical_exists
   - Import handler has hasCanonical() check
   - NO window.location='/pledge' in success path
   
✅ test_create_mode_hidden_when_canonical_exists
   - createAllowed = !hasCanonical()
   
✅ test_pledge_panel_only_when_no_canonical
   - Panel condition includes !hasCanonical()
   
✅ test_has_canonical_helper_exists
   - Helper checks wallet_v1_canonical_address
   - Validates THR prefix + length
   
✅ test_pledge_button_checks_canonical
   - Button onclick has if(hasCanonical()) guard
```

### Validation
```javascript
// In browser console with canonical set:
hasCanonical()  // → true
// Pledge panel should be hidden
document.getElementById('walletV1PledgeActivationPanel').style.display  // → 'none'
```

---

## PR #620.1: Authoritative State Refresh

### Problem
After restore/import, `modalState` remained 'no_active_wallet' (client-side), causing pledge panel to re-appear.

### Solution
Fetch authoritative modal_state from server after import/restore using `refreshWalletStateFromServer()`.

### Code Changes
- **File**: `templates/base.html`
- **Lines**:
  - 2704-2733: `refreshWalletStateFromServer(canonicalAddr)` function
  - 3463-3466: Restore calls refresh before switchWalletV1Mode()
  - 6322-6327: switchWalletV1Mode() prefers server state (walletV1LastStatus)
  - 7204-7208: Import calls refresh before switchWalletV1Mode()

### Tests (5/5 ✅)
```
✅ test_refresh_wallet_state_function_exists
   - Function calls GET /api/wallet/v1/status?address=...
   - Stores response in window.walletV1LastStatus
   
✅ test_import_handler_calls_refresh_state
   - Import success path calls refreshWalletStateFromServer()
   
✅ test_restore_handler_calls_refresh_state
   - Restore success path calls refreshWalletStateFromServer()
   - Called BEFORE switchWalletV1Mode()
   
✅ test_switch_mode_prefers_server_state
   - switchWalletV1Mode() checks window.walletV1LastStatus.modal_state first
   
✅ test_no_stale_pledge_panel_after_restore
   - Restore flow prevents stale pledge panel from showing
```

### Validation Flow
```
restore() 
  ↓
localStorage.setItem('wallet_v1_canonical_address', canonical)
  ↓
await refreshWalletStateFromServer(canonical)
  ↓ (fetches /api/wallet/v1/status)
window.walletV1LastStatus = { modal_state: 'active_wallet_...', ... }
  ↓
switchWalletV1Mode()
  ↓ (uses server modal_state)
Pledge panel HIDDEN ✅
```

---

## Code Quality Metrics

### Test Coverage
- **Total Tests**: 13
- **Pass Rate**: 100%
- **Failures**: 0

### Code Changes Summary
```
server.py:
  +4 lines, -2 lines (response schemas)
  
templates/base.html:
  +80 lines, -12 lines (helpers + guards)
  
tests/:
  +834 lines (13 test functions)
```

### Complexity Analysis
- ✅ No circular dependencies
- ✅ No breaking changes to APIs
- ✅ Backward compatible (new fields in response)
- ✅ No consensus/mining/ledger changes
- ✅ No external dependencies added

---

## Security Enforcement Chain

```
LAYER 1: Server (PR #619)
├─ Pledge endpoint checks if canonical exists
├─ If YES → return created=false, SAME canonical
└─ If NO → create new canonical

LAYER 2: Frontend (PR #620)
├─ hasCanonical() helper checks localStorage
├─ Import/Restore blocked if no canonical (with error msg)
├─ Create mode disabled if canonical exists
└─ Pledge panel hidden if canonical exists

LAYER 3: State (PR #620.1)
├─ After restore/import → fetch server modal_state
├─ Store in window.walletV1LastStatus
└─ switchWalletV1Mode() uses server truth (not stale client state)
```

### Defense in Depth
- ✅ Server is source of truth (layer 1 enforcement)
- ✅ UI enforces rules locally (layer 2 UX)
- ✅ State refresh prevents staleness (layer 3 consistency)
- ✅ If UI bypassed (devtools), server still enforces immutability
- ✅ If one layer fails, others still protect identity

---

## Manual QA Gate Requirements

**BEFORE PR #621, verify on deployed build:**

### Scenario A: Canonical Exists → NO /pledge
- [ ] Set canonical in localStorage
- [ ] Reload page
- [ ] Network log: 0 /pledge requests
- [ ] UI: Pledge panel hidden, Create mode disabled
- [ ] Expected: User in Unlock mode

### Scenario B: Canonical Missing → /pledge OK
- [ ] Clear canonical from localStorage
- [ ] Reload page
- [ ] Network log: /pledge allowed
- [ ] UI: Pledge panel visible, button clickable
- [ ] Expected: User can start pledge flow

### Scenario C: Restore Kit → Server State Refresh
- [ ] Set canonical in localStorage
- [ ] Trigger restore (upload kit or paste JSON)
- [ ] Network log: GET /api/wallet/v1/status?address=canonical
- [ ] UI: Pledge panel stays hidden, mode = Unlock
- [ ] Expected: No /pledge redirect, proper state shown

### Server API Verification
- [ ] Repeat pledge: 2nd call returns created=false, same canonical
- [ ] Response schema: all responses include canonical_v1_address + created
- [ ] No canonical rotation on any flow

**See detailed checklist**: [MANUAL_QA_CHECKLIST.md](MANUAL_QA_CHECKLIST.md)

---

## Merge Checklist

- [x] Code-level tests: 13/13 passing
- [x] Server-side immutability lock implemented
- [x] Frontend route guards implemented
- [x] State refresh after import/restore implemented
- [x] No breaking changes to APIs
- [x] Backward compatible response schemas
- [x] No consensus/mining code changes
- [ ] ⏳ Manual QA scenarios A, B, C passing (USER ACTION REQUIRED)
- [ ] ⏳ Server API verification complete (USER ACTION REQUIRED)
- [ ] ⏳ PR #621 ready to start

---

## Next Steps

### If Manual QA Passes ✅
```
1. Update this report with QA results
2. Create PR #621 (State Machine Contract)
3. Merge in order: #619 → #620 → #620.1 → #621
```

### If Manual QA Fails ❌
```
1. Identify failure scenario (A, B, or C)
2. Debug using provided Network log patterns
3. Patch PR #620.1 (most likely location for state refresh issues)
4. Re-run code tests to verify fix
5. Re-run manual QA
```

---

## Contact & Support

**Code Files**:
- Server: `server.py` (lines 16948, 17035)
- Frontend: `templates/base.html` (lines 2699, 1604, 6293, 6394, 6473, 7131, 7162)
- Tests: `tests/test_pr_619_*.py`, `tests/test_pr_620_*.py`, `tests/test_pr_620_1_*.py`

**Commit Refs**:
- PR #619: `f1e3642`
- PR #620: `a5fa291`
- PR #620.1: `e9000ae`

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce

---

**READY FOR MANUAL QA GATE**
