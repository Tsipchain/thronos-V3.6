# Production Hotfix: Missing display:none on walletV1CreateMode

**Issue**: Wallet V1 mode dropdown shows "Unlock Wallet V1" but visible CTA button shows "Create Wallet V1"

**Root Cause**: The `walletV1CreateMode` HTML div was missing `style="display:none;"` in its initial inline style

**Fix Commit**: `bdef989`

**PR**: #622 (Draft - pending review and merge)

---

## The Bug in Production

User reports:
```
Dropdown shows: "Unlock Wallet V1"
Visible CTA shows: "Create Wallet V1" (WRONG - should be "Unlock Wallet V1")
```

This caused user confusion when trying to unlock existing wallets.

---

## Technical Root Cause

### Before Fix
All mode divs had `display:none` EXCEPT the CREATE mode:

```html
<!-- UNLOCK: ✓ has display:none -->
<div id="walletV1UnlockMode" style="display:none; margin-top:10px;">

<!-- RESTORE: ✓ has display:none -->
<div id="walletV1RestoreMode" data-wallet-legacy-repair="1" style="display:none; margin-top:10px;">

<!-- MIGRATE: ✓ has display:none -->
<div id="walletV1MigrateMode" data-wallet-legacy-repair="1" style="display:none; margin-top:10px;">

<!-- IMPORT: ✓ has display:none -->
<div id="walletV1ImportMode" style="display:none; margin-top:10px;">

<!-- ADMIN_SIGNER: ✓ has display:none -->
<div id="walletV1AdminGenerateSignerMode" data-wallet-legacy-repair="1" style="display:none; margin-top:10px;">

<!-- CREATE: ❌ MISSING display:none -->
<div id="walletV1CreateMode" style="margin-top:10px;">  <!-- BUG: defaults to visible! -->
```

### Impact of Missing display:none

Because the CREATE div had no initial `display:none`:
1. Browser renders it as **visible by default** on page load
2. The atomic visibility update (hide all, show one) runs in JavaScript
3. But browser may have already cached/rendered the CREATE div as visible
4. The visual update might not reflect the DOM change

**Result**: User sees the CREATE button text even when UNLOCK mode should be displayed.

### After Fix
Added `style="display:none;"` to match all other mode divs:

```html
<!-- CREATE: ✓ now has display:none (FIXED) -->
<div id="walletV1CreateMode" style="display:none; margin-top:10px;">
```

---

## What Changed

**File**: `templates/base.html`

**Line**: 1696

**Change**: Added `display:none;` to initial inline style

```diff
- <div id="walletV1CreateMode" style="margin-top:10px;">
+ <div id="walletV1CreateMode" style="display:none; margin-top:10px;">
```

**Scope**: 1 line changed (HTML attribute)

**Risk Level**: MINIMAL
- Simple HTML structure fix
- No JavaScript logic changes
- Aligns CREATE div with all other mode divs
- No side effects

---

## Test Results: All PASS ✅

### Acceptance Test: PASS
```
[STEP 1] Reproduce failing state: dropdown=unlock, create visible, CTA=Create ✓
[STEP 2] Call switchWalletV1Mode('unlock') ✓
[STEP 3] Assert fix: only unlock visible, CTA=Unlock ✓
✅ ALL ACCEPTANCE CRITERIA PASSED
```

### Regression Test Suite: 13/13 PASS
- ✅ Mode→CTA Mapping (5 tests)
- ✅ Runtime DOM Structure (4 tests)
- ✅ E2E Verification (4 tests)

### Total Test Coverage: 14/14 PASS

---

## Production Deployment Steps

### Pre-Deployment (In This Session)
- [x] Root cause identified
- [x] Fix implemented (1 line HTML change)
- [x] Acceptance test: PASS
- [x] Regression tests: 14/14 PASS
- [x] PR #622 created

### Deployment
1. **Merge PR #622** into `main`
2. **Deploy** to production
3. Monitor `/api/health` for commit update

### Post-Deployment Verification (REQUIRED)

#### Step 1: Verify Commit
```bash
# Check that production is running the new commit
curl https://api.thronoschain.org/api/health | jq '{git_commit, build_id}'

# Verify commit matches PR #622
# Expected: bdef989 (or later if merged with other commits)
git log -1 --format="%H" main  # Compare with above
```

#### Step 2: Manual Browser Testing

**Open incognito/private window** (to avoid cache):
```
https://api.thronoschain.org
```

**Test Scenario A: Mode=Unlock**
1. Open DevTools (F12) → Console
2. Run: `document.getElementById('walletWidgetMode').value = 'unlock'; switchWalletV1Mode();`
3. Verify:
   - [ ] Dropdown shows: "Unlock Wallet V1"
   - [ ] Visible CTA text: "Unlock Wallet V1" (NOT "Create")
   - [ ] Console shows NO errors
4. Run: `validateWalletV1ModeCTAMatch()` → should return `true`

**Test Scenario B: Mode=Create**
1. Run: `document.getElementById('walletWidgetMode').value = 'create'; switchWalletV1Mode();`
2. Verify:
   - [ ] Dropdown shows: "Create Wallet V1"
   - [ ] Visible CTA text: "Create Wallet V1"

**Test Scenario C: Mode=Unlock (again)**
1. Run: `document.getElementById('walletWidgetMode').value = 'unlock'; switchWalletV1Mode();`
2. Verify:
   - [ ] Dropdown shows: "Unlock Wallet V1"
   - [ ] Visible CTA text: "Unlock Wallet V1"

**Test Scenario D: Hard Refresh**
1. Ctrl+Shift+R (or Cmd+Shift+R on Mac)
2. Wait for page to load
3. Verify: No console errors
4. Inspect element on wallet widget - verify no strange CSS overrides

#### Step 3: Screenshot Proof

**REQUIRED**: Screenshot showing:
- Browser address bar: `https://api.thronoschain.org`
- Wallet widget visible
- Mode dropdown: "Unlock Wallet V1" (selected)
- CTA button text: "Unlock Wallet V1" (NOT "Create")
- No error messages in console
- Timestamp showing deployment time

---

## Rollback Procedure (If Needed)

If post-deployment verification FAILS:

```bash
# Revert just this commit
git revert bdef989

# Push rollback
git push origin main

# Production will redeploy from previous working state
```

---

## Why This Bug Happened

The atomic visibility fix (commit 4fad6d6) implemented the JavaScript logic correctly:
1. Hide all mode divs
2. Show exactly one based on displayMode
3. Sync dropdown value

However, the HTML structure still had the CREATE div visible by default, which undermined the JavaScript fix. The missing `display:none` on the CREATE div was an oversight in the original HTML template structure.

---

## Files Changed

| File | Lines | Change | Type |
|------|-------|--------|------|
| `templates/base.html` | 1696 | Add `display:none;` to CREATE mode div | HTML Structure |

---

## Sign-Off Checklist

### Pre-Deployment ✅
- [x] Root cause identified and documented
- [x] Fix implemented (1 line)
- [x] Acceptance test: PASS
- [x] All regression tests: PASS (14/14)
- [x] PR created: #622

### Post-Deployment (Complete After Merge & Deploy)
- [ ] Production commit verified
- [ ] Browser test A: unlock mode works ✓
- [ ] Browser test B: create mode works ✓
- [ ] Browser test C: unlock again works ✓
- [ ] Hard refresh loads clean ✓
- [ ] No console errors
- [ ] Screenshot provided

### Final Approval
- [ ] All criteria met → **APPROVED FOR PRODUCTION**
- [ ] Any criteria failed → **BLOCK DEPLOYMENT** (document issue)

---

## Related Documentation

- **Atomic Visibility Fix**: `DEPLOYMENT_VERIFICATION_MODE_CTA_FIX.md`
- **Acceptance Test**: `tests/test_acceptance_mode_cta_fix.py`
- **PR #621**: Remove infinite recursion in runtime guard
- **PR #622**: Add missing display:none (THIS HOTFIX)

---

**Status**: READY FOR PRODUCTION DEPLOYMENT ✅

**Commit**: `bdef989`

**Risk**: MINIMAL (1-line HTML structure fix)

**Impact**: CRITICAL (fixes user-visible CTA mismatch bug)
