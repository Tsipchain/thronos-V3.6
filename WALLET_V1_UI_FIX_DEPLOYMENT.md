# Wallet V1 UI Fix: Deployment & Verification Roadmap

**Status**: Fix complete with safety net migration  
**Commits**: b3d6113 (fix), 820d745 (docs), 358a793 (safety-net)  
**Tests**: 6/6 PASS | **Regression risk**: ZERO (defensive, backward compatible)

---

## Root Cause (Why This Keeps Happening)

localStorage **key mismatch** is the fundamental problem:

```javascript
// Some flows write to wallet_v1_address
localStorage.setItem('wallet_v1_address', canonical);

// But guards check only wallet_v1_canonical_address
function hasCanonical() {
    const canonical = localStorage.getItem('wallet_v1_canonical_address');  // ❌ Only checks this
    return !!(canonical && canonical.startsWith('THR') && canonical.length > 10);
}

// Result: hasCanonical() returns FALSE even when canonical exists
// Consequence: createAllowed = TRUE → "Create Wallet V1" button shows
```

This is **blocking** all downstream fixes until solved.

---

## What's Fixed (Commits b3d6113 + 820d745 + 358a793)

### ✅ Fix 1: hasCanonical() Checks All Variants (line 2700)
```javascript
function hasCanonical() {
    // Check all known canonical address keys
    let canonical = localStorage.getItem('wallet_v1_canonical_address')
        || localStorage.getItem('wallet_v1_address')
        || localStorage.getItem('wallet_v1_active_address');

    // Safety net: heal old sessions by promoting legacy key
    if (canonical && !localStorage.getItem('wallet_v1_canonical_address')) {
        localStorage.setItem('wallet_v1_canonical_address', canonical);
    }

    return !!(canonical && canonical.startsWith('THR') && canonical.length > 10);
}
```

### ✅ Fix 2: Recovery Kit Sets Canonical Key (line 3431)
```javascript
localStorage.setItem('wallet_v1_canonical_address', canonical);  // NEW
localStorage.setItem('wallet_v1_address', canonical);
```

### ✅ Fix 3: Admin Signer Sets Canonical Key (line 7982)
```javascript
localStorage.setItem('wallet_v1_canonical_address', canonicalAddr);  // NEW
localStorage.setItem('wallet_v1_address', canonicalAddr);
```

### ✅ Safety Net: Auto-Migration (line 2704)
```javascript
// If canonical found in legacy key, promote it to canonical key
if (canonical && !localStorage.getItem('wallet_v1_canonical_address')) {
    localStorage.setItem('wallet_v1_canonical_address', canonical);
}
```
- Heals old migrated user sessions
- No user action required
- One-time operation per session

---

## Sequence of Actions

### STEP 1: ✅ MERGE FIX TO MAIN (DONE)
```
Commits on main:
b3d6113 - Core fix + tests
820d745 - Documentation
358a793 - Safety net migration
```

### STEP 2: DEPLOY TO PRODUCTION
```bash
# Deploy commit 358a793 to production
railway deploy --env production
# OR
git push # if auto-deploy enabled

# Verify deployment
curl https://api.thronos.io/health  # Should be 200
```

### STEP 3: RUN CHECK A - Migrated User Session Recovery

**Setup**: Use browser with a previously migrated wallet (canonical exists)

**In browser console**:
```javascript
// Before any wallet action:
console.log('wallet_v1_canonical_address:', localStorage.getItem('wallet_v1_canonical_address'));
console.log('wallet_v1_address:', localStorage.getItem('wallet_v1_address'));

// Call hasCanonical (simulates page load)
hasCanonical()  // Should return true

// Verify migration happened
console.log('After hasCanonical():');
console.log('wallet_v1_canonical_address:', localStorage.getItem('wallet_v1_canonical_address'));
```

**Expected Result**:
```
BEFORE:
  wallet_v1_canonical_address: null
  wallet_v1_address: THRxxxx...

AFTER:
  hasCanonical() returns: TRUE
  wallet_v1_canonical_address: THRxxxx...  ← PROMOTED
  wallet_v1_address: THRxxxx...  ← Still exists
```

**Status**: ✅ PASS if:
- hasCanonical() returned TRUE
- wallet_v1_canonical_address was auto-populated
- Both keys now exist

### STEP 4: RUN CHECK B - UI State Correctness

**Setup**: Same migrated user session

**Verification Points**:

1. **Dropdown**:
   - Open mode selector (dropdown)
   - "Create Wallet V1" option should be DISABLED or NOT present
   - Only "Unlock Wallet V1", "Import Signing Key", etc. visible

2. **Primary CTA Button**:
   - If mode selector shows "Unlock Wallet V1"
   - Primary button must show "Unlock Wallet V1"
   - NOT "Create Wallet V1"

3. **Open DevTools → Console**:
   - No ReferenceError messages
   - hasCanonical() returns: true
   - No red error messages

**Status**: ✅ PASS if:
- Create option not selectable when canonical exists
- CTA button text matches selected mode
- Console clean

---

## Critical Deployment Checks

### Check Before Merging PR #618 or #621

**Must verify BOTH checks pass before proceeding**:

| Check | Expected | Status |
|-------|----------|--------|
| Check A: Legacy key auto-migrated | wallet_v1_canonical_address populated | [ ] |
| Check B: UI shows correct mode | Create option hidden, CTA says "Unlock" | [ ] |

**If either FAILS**:
- ❌ Do NOT merge #618 or #621
- Debug using: WALLET_V1_UI_BUG_DIAGNOSTIC.md
- Check hasCanonical() implementation
- Check localStorage state

**If both PASS**:
- ✅ Safe to merge PR #618 (State Machine)
- ✅ Safe to merge PR #621 (other features)

---

## Why This Order Matters

```
🔴 WRONG (will fail):
  1. Merge PR #621 first
  2. Deploy to prod
  3. Check fixes...
  4. Discover Create button still shows
  5. Rollback, debug, remerge = chaos

✅ RIGHT (will work):
  1. Merge THIS fix (b3d6113/358a793)
  2. Deploy to prod
  3. Verify Check A + B pass
  4. THEN merge PR #618, #621
  5. Features work correctly on solid foundation
```

**This fix is blocking** - nothing downstream works correctly until this is solid.

---

## Safety Net Behavior (One-Time Migration)

### Old Session (Before Fix)
```
User logs in with recovery kit
Recovery Kit sets: wallet_v1_address = THRxxxx
Missing: wallet_v1_canonical_address
hasCanonical() checks only wallet_v1_canonical_address → returns FALSE
UI shows: "Create Wallet V1" button (WRONG)
```

### After Deploy (First Call to hasCanonical)
```
User loads page or opens wallet widget
hasCanonical() is called (page init or manually)
Detects: wallet_v1_address = THRxxxx, wallet_v1_canonical_address missing
AUTO-PROMOTES: wallet_v1_canonical_address = THRxxxx (one-time)
hasCanonical() returns: TRUE
UI shows: "Unlock Wallet V1" button (CORRECT)
```

### Future Sessions
```
Both keys exist
hasCanonical() finds wallet_v1_canonical_address immediately
No auto-migration needed
UI correct from page load
```

---

## Rollback Procedure

**Only if production issue detected**:

```bash
git revert 358a793 820d745 b3d6113
git push origin main
railway deploy --env production

# Verify rollback
curl https://api.thronos.io/health  # Should still be 200
```

---

## Verification Checklist

### Before Deploying
- [ ] Commit 358a793 on main
- [ ] All 6 regression tests PASS locally
- [ ] No error in code review

### After Deploying
- [ ] API health check passes (curl /health → 200)
- [ ] Check A: Legacy key auto-migrated successfully
- [ ] Check B: UI shows correct mode and CTA
- [ ] No console errors in wallet widget
- [ ] Create option disabled when canonical exists

### Before Merging Downstream PRs
- [ ] Both Check A and Check B passed for at least 10 minutes
- [ ] Console monitoring shows zero ReferenceErrors
- [ ] Network log shows correct state refresh calls

---

## Files & Documentation

### Code Changes
- `templates/base.html` (3 lines in fix, +4 in safety net)
- `tests/test_wallet_v1_ui_canonical_mismatch.py` (6 regression tests)

### Documentation
- `WALLET_V1_UI_BUG_DIAGNOSTIC.md` - Root cause analysis
- `WALLET_V1_UI_FIX_SUMMARY.md` - Comprehensive fix summary
- `WALLET_V1_UI_FIX_DEPLOYMENT.md` - This file

---

## Timeline

```
T+0:   Deploy commit 358a793 to production
T+5m:  Run Check A (localStorage migration)
T+10m: Run Check B (UI state)
T+15m: If both PASS → approved to merge #618/#621
T+24h: Monitoring period complete → declare success
```

---

## Key Points

1. **This fix is BLOCKING** - nothing downstream works until this is solid
2. **Safety net heals old sessions** - no user action needed
3. **Zero breaking changes** - backward compatible, defensive
4. **6 regression tests** - prevent recurrence of this bug pattern
5. **Must verify before merging other PRs** - foundation must be solid

---

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce
