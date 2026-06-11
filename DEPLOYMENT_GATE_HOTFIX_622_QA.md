# DEPLOYMENT GATE: Hotfix #622 Manual QA Verification

**Branch**: main (commit f5d166a)  
**Hotfix Commit**: c2d4f1b (Production crash fix)  
**Status**: AWAITING MANUAL QA VERIFICATION

---

## Pre-QA: Deployment to Railway

**Step 1: Deploy to Railway Production**
```bash
# Option A: Via Railway CLI
railway deploy --env production

# Option B: Via Git push (if Railway is configured for auto-deploy)
git push origin main

# Verify deployment status:
# 1. Check Railway dashboard
# 2. Confirm new build deployed
# 3. Wait for service to be healthy (green status)
```

**Verify Deployment Successful**:
- [ ] Railway build completed without errors
- [ ] Service is HEALTHY (green indicator)
- [ ] New commit f5d166a deployed
- [ ] API responding at https://api.thronos.io/health (200 OK)

---

## QA SCENARIO A: Canonical Exists → NO /pledge Requests

### Setup
1. Open https://app.thronos.io/wallet in browser
2. Press **F12** to open DevTools
3. Go to **Network** tab
4. **Filter**: Type = XHR/Fetch OR use search filter "pledge"
5. Open **Console** tab in another area (split view recommended)

### Action
```javascript
// In Browser Console:
localStorage.setItem('wallet_v1_canonical_address', 'THRtest1234567890');
localStorage.setItem('wallet_v1_address', 'THRtest1234567890');
location.reload();
```

### Expected Results

**Network Log** (F12 → Network):
```
EXPECTED ✅:
- Zero requests to /pledge (any method)
- Zero requests to /pledge_submit
- Zero requests to /api/pledge/*
- May see: GET /api/wallet/v1/status?address=THR...  (OK - state refresh)

FAILURE ❌ if you see:
- GET /pledge HTTP 200
- POST /pledge_submit
- GET /api/pledge/...
```

**Console** (F12 → Console):
```
EXPECTED ✅:
- Zero ReferenceError messages
- Zero TypeError messages
- Status: 200 responses OK
- No red error text

FAILURE ❌ if you see:
- ReferenceError: advancedImportForm is not defined
- ReferenceError: hasCanonical is not defined
- Any red error messages
```

**UI Display**:
```
EXPECTED ✅:
- Pledge Activation Panel is HIDDEN
- Mode dropdown shows "Unlock" or "Import Signing Key"
- "Create Wallet V1" option DISABLED or hidden
- Page loaded normally

FAILURE ❌ if you see:
- Pledge panel visible with "Go to Pledge Activation" button
- "Create Wallet V1" clickable in dropdown
- 500 error or blank page
```

### Record Result
- [ ] PASS: Zero /pledge requests + console clear + UI correct
- [ ] FAIL: (describe exact request chain below)

**If FAIL - Document exact request chain**:
```
Timeline of requests:
T+0s: <METHOD> <URL> → <STATUS> <RESPONSE>
T+0.5s: <METHOD> <URL> → <STATUS> <RESPONSE>
...

Console errors:
<Error text here>

UI state:
<Screenshot or description>
```

---

## QA SCENARIO B: Canonical Missing → /pledge Allowed

### Setup
1. Open https://app.thronos.io/wallet
2. Press **F12** for DevTools
3. Go to **Network** tab
4. Filter: "pledge"

### Action
```javascript
// In Browser Console:
localStorage.removeItem('wallet_v1_canonical_address');
localStorage.removeItem('wallet_v1_address');
location.reload();
```

### Expected Results

**Network Log**:
```
EXPECTED ✅ (after page loads):
- /pledge endpoint is accessible
- GET /pledge returns 200 if user clicks button
- Pledge flow can be initiated

FAILURE ❌ if you see:
- /pledge returns 500 or blocked
- "Pledge not allowed" error
- Wallet prevents any pledge flow
```

**Console**:
```
EXPECTED ✅:
- Zero ReferenceError messages
- Page loads cleanly
- No 500 errors

FAILURE ❌ if you see:
- ReferenceError: advancedImportForm...
- Network errors accessing /pledge
```

**UI Display**:
```
EXPECTED ✅:
- "Go to Pledge Activation" button VISIBLE and GREEN
- Button clickable (not disabled)
- "Create Wallet V1" option visible in dropdown
- Pledge panel displayed

FAILURE ❌ if you see:
- Pledge panel hidden
- Button disabled or missing
- "Create Wallet V1" option disabled
```

### Record Result
- [ ] PASS: Pledge button visible + clickable + /pledge accessible
- [ ] FAIL: (describe issue below)

**If FAIL - Document exact issue**:
```
What happened when you:
1. Clicked "Go to Pledge Activation" button?
2. Checked Network tab?
3. Navigated to /pledge directly?

<Description>
```

---

## QA SCENARIO C: Restore Kit → State Refresh After Canonical Set

### Setup
1. Set canonical in localStorage (like Scenario A)
2. Open **Network** tab
3. Filter: "wallet/v1/status" or "status"
4. Have a test recovery kit ready (JSON or file)

### Action
1. Click **"Import Signing Key"** or **"Restore Recovery Kit"** button
2. Upload recovery kit or paste JSON
3. Watch the **Network tab** during restore process

### Expected Results

**Network Log** (in order):
```
Timeline:
T+0s   → (Recovery kit processing starts)
T+0.5s → ✅ GET /api/wallet/v1/status?address=THRxxxxxx... 200
         Response includes: { "modal_state": "active_wallet_..." }
T+1.0s → Zero POST /pledge_submit requests
T+1.2s → Page updates showing unlock/import form (NOT pledge panel)

FAILURE ❌ if you see:
T+0.5s → No GET /api/wallet/v1/status request
T+0.8s → POST /pledge_submit (should NOT happen)
T+1.0s → Pledge panel appears on screen
```

**Console**:
```
EXPECTED ✅:
- Zero ReferenceError
- GET /api/wallet/v1/status returns 200
- modal_state value logged (if dev tools show it)

FAILURE ❌ if you see:
- ReferenceError during restore
- /api/wallet/v1/status returns 500
- Error messages in console
```

**UI After Restore**:
```
EXPECTED ✅:
- Modal/mode refreshes quickly
- Pledge panel HIDDEN
- Shows "Unlock" or import-related form
- No "Go to Pledge Activation" button visible
- State switches away from "no_active_wallet"

FAILURE ❌ if you see:
- Pledge panel shows after restore complete
- Modal stuck on "no_active_wallet"
- User redirected to /pledge
- Restore fails with error
```

### Record Result
- [ ] PASS: /api/wallet/v1/status called + pledge panel stays hidden
- [ ] FAIL: (describe exact network sequence below)

**If FAIL - Document exact request sequence**:
```
Network requests in order:
1. <METHOD> <URL> → <STATUS> <RESPONSE>
2. <METHOD> <URL> → <STATUS> <RESPONSE>
3. <METHOD> <URL> → <STATUS> <RESPONSE>
...

Timing:
- Request at T+___ ms
- Response at T+___ ms

UI state after restore:
<Description of what you see>
```

---

## DEPLOYMENT GATE DECISION

### All 3 Scenarios PASS ✅
```
Scenario A: ✅ PASS (canonical exists, NO /pledge requests)
Scenario B: ✅ PASS (canonical missing, /pledge allowed)
Scenario C: ✅ PASS (restore state refresh works)
Console: Zero ReferenceError occurrences
```

**NEXT ACTION**: 
```bash
# Proceed to merge PR #618
git checkout main
git merge --no-ff <PR #618 branch> -m "Merge PR #618 after hotfix #622 QA passes"
git push origin main
```

---

### Any Scenario FAILS ❌
```
Scenario A: ❌ FAIL (saw /pledge requests when canonical exists)
OR
Scenario B: ❌ FAIL (pledge button not working when canonical missing)
OR
Scenario C: ❌ FAIL (no state refresh after restore)
OR
Console: ReferenceError: advancedImportForm is not defined
```

**STOP - DO NOT MERGE PR #618**

**Report Failure**:
```
Failing Scenario: [A / B / C]

Exact request chain that failed:
1. <METHOD> <URL> → <STATUS> <RESPONSE>
2. <METHOD> <URL> → <STATUS> <RESPONSE>
...

Console error (if any):
<Full error text>

Expected behavior:
<What should have happened>

Actual behavior:
<What actually happened>

Steps to reproduce:
<Exact steps in console/UI>
```

---

## Sign-Off Checklist

### QA Verification Completed
- [ ] Scenario A tested and result recorded
- [ ] Scenario B tested and result recorded  
- [ ] Scenario C tested and result recorded
- [ ] Console checked for ReferenceError (all 3 scenarios)
- [ ] Network logs captured for failing scenarios (if any)

### Deployment Status

**If ALL PASS**:
- [ ] Ready to merge PR #618
- [ ] Ready for production monitoring (24h)
- [ ] Ready to proceed to PR #621

**If ANY FAIL**:
- [ ] STOP - Do not merge PR #618
- [ ] Report exact failing request chain
- [ ] Open new hotfix for regression

---

## Technical Details

### What "Pass" Means
- **Scenario A**: `canonical exists` → `zero /pledge requests` + `console clean`
- **Scenario B**: `canonical missing` → `/pledge accessible` + `button works`
- **Scenario C**: `restore triggered` → `GET /api/wallet/v1/status called` + `pledge panel hidden`

### Critical Error Signals
- `ReferenceError: advancedImportForm is not defined` → FAIL (hotfix didn't work)
- `/pledge_submit` called when canonical exists → FAIL (guard not working)
- Pledge panel visible after restore with canonical → FAIL (state refresh not working)

### Network Log Analysis

**Good Flow** (Scenario A):
```
GET /api/wallet/v1/status?address=THRxxxx 200
GET /api/wallet/profile 200
Zero /pledge requests
```

**Bad Flow** (would indicate regression):
```
GET /api/wallet/v1/status?address=THRxxxx 200
POST /pledge_submit ← ❌ SHOULD NOT HAPPEN
GET /pledge 200 ← ❌ SHOULD NOT HAPPEN
```

---

## Support

If you encounter issues:

1. **ReferenceError in Console**:
   - Check commit c2d4f1b is deployed
   - Verify `const advancedImportForm` at line 6024
   - Full page refresh (Ctrl+Shift+Del → clear cache → refresh)

2. **/pledge Request When Canonical Exists**:
   - Check commit c2d4f1b is deployed
   - Verify pledge button has `hasCanonical()` guard at line 1604
   - Check localStorage shows `wallet_v1_canonical_address` set correctly

3. **No State Refresh After Restore**:
   - Check `/api/wallet/v1/status` endpoint is responding
   - Verify `refreshWalletStateFromServer()` called in import/restore handlers
   - Check network response includes `modal_state` field

---

**DEPLOYMENT GATE**: Ready for manual QA verification by QA team.

Once all 3 scenarios pass, PR #618 can be merged and deployment complete.

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce
