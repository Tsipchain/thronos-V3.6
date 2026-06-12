# Regression-First Surgical Continuation: Phase 1 & Phase 2 Roadmap

**Overall Status**: Foundation complete (b3d6113-b24057d), now preparing PR #621

---

## PHASE 1: Deploy Gate Verification (Production Check Only)

**Commit**: b24057d on main (already merged)  
**Script**: `phase1_deploy_gate_verification.sh`

### Step 1: Verify Production Commit
```bash
curl https://api.throschain.org/api/health
# Extract git_commit, build_id, version
# Verify: b24057d (or later)
```

### Step 2: Manual QA (Browser - F12 Network + Console)

**SCENARIO A: Canonical exists (legacy key only)**
```javascript
localStorage.setItem('wallet_v1_address', 'THRxxxxxxxxxxxxxxxx');
location.reload();
```

**Expected ✅**:
- hasCanonical() returns: true
- wallet_v1_canonical_address: auto-populated (migrated from wallet_v1_address)
- Mode dropdown: "Unlock Wallet V1" (NOT "Create")
- CTA button: "Unlock Wallet V1" (NOT "Create")
- Network: ZERO /pledge requests
- Console: NO ReferenceError

**If FAIL ❌**: 
- Screenshot Network chain (show /pledge requests if any)
- Screenshot Console errors
- Report: METHOD PATH STATUS

---

**SCENARIO B: Canonical missing**
```javascript
localStorage.removeItem('wallet_v1_canonical_address');
localStorage.removeItem('wallet_v1_address');
location.reload();
```

**Expected ✅**:
- Pledge panel visible
- "Go to Pledge Activation" button clickable
- Mode dropdown includes "Create Wallet V1"
- Console: NO errors

---

**SCENARIO C: Restore/Import with canonical present**
```javascript
localStorage.setItem('wallet_v1_address', 'THRxxxxxxxxxxxxxxxx');
location.reload();
// Click: Import Matching Signing Key OR Restore Recovery Kit
```

**Expected ✅**:
- GET /api/wallet/v1/status called (Network tab)
- Pledge panel HIDDEN after restore
- Mode: "Unlock" (not "Create")
- ZERO /pledge_submit requests
- Console: NO ReferenceError

---

### Gate Decision

**IF all 3 PASS ✅**:
```
✅ APPROVED: Safe to merge PR #621 (State Machine Contract)
```

**IF ANY FAIL ❌**:
```
❌ BLOCKED: Do NOT merge PR #621
- Debug using: WALLET_V1_UI_BUG_DIAGNOSTIC.md
- Report exact failure + network chain
```

---

## PHASE 2: PR #621 - State Machine Contract

**Commit**: a79bf8b on main (documentation + tests staged)  
**Status**: Tests written, 3/5 PASS, 2/5 FAIL (expected)

### Documentation: WALLET_V1_STATE_MACHINE.md

**5 Frozen Modes** (no auto-transition):
1. `unlock` - Pin unlock when signing key exists
2. `restore_recovery_kit` - Recovery kit restore when key missing
3. `import_signing_key` - Bound key import for device change
4. `mirage_legacy` - Admin-only legacy migration (hidden in production)
5. `pledge_new` - Create canonical when none exists (FORBIDDEN if canonical present)

**Hard Rules**:
- **Canonical Immutability**: pledge_new forbidden if canonical exists
- **No Auto-Navigation**: Restore/import never redirect to /pledge
- **Explicit Selection**: No auto-flip between modes
- **Admin-Only Mirage**: Legacy options hidden unless WALLET_V1_LEGACY_REPAIR_UI_ENABLED=true
- **Server-First State**: switchWalletV1Mode() uses server modal_state (window.walletV1LastStatus)

### Regression Tests: test_pr_621_state_machine_contract.py

**Test Results**:
```
✅ PASS (3): Mode-to-CTA mapping, Create option gating, Hard override
❌ FAIL (2): Import success pledge check, Legacy/mirage hiding (expected - to be fixed)
```

**Tests to Fix**:
1. **Import success path** - Verify NO /pledge redirect in import handler
2. **Legacy hiding** - Ensure applyWalletV1ProductionMode properly hides legacy/mirage

---

## Implementation Plan for PR #621

### Minimal Glue Code (1-3 lines, if needed)

**If import handler has /pledge redirect** (line ~7200):
```javascript
// Remove or guard any window.location.href='/pledge' in import success path
// If canonical exists, never redirect
```

**If legacy/mirage not hidden in production** (line ~6000):
```javascript
// In applyWalletV1ProductionMode() when !legacyRepairEnabled:
// Ensure: migrateForm.style.display = 'none'
// Ensure: restoreForm.style.display = 'none' (legacy restore, not Recovery Kit)
```

**If mode selection allows 'create' with canonical** (line ~6350):
```javascript
// Hard override: if (hasCanonical() && mode === 'create') { displayMode = 'unlock'; }
```

---

## Deliverables for PR #621

```
PR #621: Wallet V1 State Machine Contract

Files:
  + WALLET_V1_STATE_MACHINE.md (frozen modes + hard rules documented)
  + tests/test_pr_621_state_machine_contract.py (5 tests, 3 PASS, 2 FAIL → all PASS)
  ± templates/base.html (0-3 surgical lines if needed)

Diff Stats:
  - Documentation: +300 lines (state machine contract)
  - Tests: +200 lines (regression test suite)
  - Code: 0-3 lines (minimal glue)
  Total: +500 lines, 0-3 code changes

Test Status BEFORE:
  ✅ 3/5 PASS
  ❌ 2/5 FAIL (expected)

Test Status AFTER:
  ✅ 5/5 PASS (all regression tests pass)
```

---

## Timeline

```
T+0h:   Phase 1 - Deploy b24057d to production
T+0.5h: Phase 1 - Run Manual QA Scenarios A/B/C
T+1h:   Phase 1 - Gate decision: APPROVED or BLOCKED
T+2h:   Phase 2 - Fix failing tests (if needed)
T+3h:   Phase 2 - All tests PASS (5/5)
T+4h:   Phase 2 - Create PR #621 with minimal glue
T+5h:   Phase 2 - Code review complete
T+6h:   Phase 2 - Merge PR #621 to main
```

---

## Risk Mitigation

### Why Phase 1 Must PASS Before Phase 2 Merge

Phase 1 validates:
- ✅ Production has correct commit
- ✅ localStorage migration working
- ✅ Canonical detection robust
- ✅ No unintended /pledge redirects
- ✅ UI shows correct mode and CTA

**Without Phase 1 validation**, PR #621 merge could deploy with:
- ❌ Stale production state (wrong commit)
- ❌ localStorage keys not migrated
- ❌ Legacy options not hidden
- ❌ Unexpected /pledge redirects

### Rollback Procedure (If Needed)

```bash
git revert a79bf8b b24057d 358a793 820d745 b3d6113
git push origin main
# Reverts all changes, back to safe state
```

---

## Files & Documentation

### Phase 1
- `phase1_deploy_gate_verification.sh` - Verification script + manual QA steps

### Phase 2
- `WALLET_V1_STATE_MACHINE.md` - 5 modes + hard rules + code locations
- `tests/test_pr_621_state_machine_contract.py` - 5 regression tests
- `WALLET_V1_STATE_MACHINE.md` - Frozen mode contract

### Reference (Earlier Phases)
- `WALLET_V1_UI_BUG_DIAGNOSTIC.md` - Root cause analysis
- `WALLET_V1_UI_FIX_SUMMARY.md` - Surgical fix details
- `WALLET_V1_UI_FIX_DEPLOYMENT.md` - Phase 1 deployment guide

---

## Next Action Items

**Immediate** (Phase 1):
1. Deploy commit b24057d to production (if not already deployed)
2. Run `./phase1_deploy_gate_verification.sh https://api.throschain.org`
3. Manually verify Scenarios A/B/C in browser
4. Decision: APPROVED or BLOCKED

**If APPROVED** (Phase 2):
1. Fix failing tests (if needed) in templates/base.html
2. Re-run tests: all 5/5 should PASS
3. Create PR #621 with:
   - WALLET_V1_STATE_MACHINE.md
   - tests/test_pr_621_state_machine_contract.py
   - (0-3 lines glue code if needed)
4. Code review + merge

---

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce
