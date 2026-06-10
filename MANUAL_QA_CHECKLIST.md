# Manual QA Checklist: Canonical Address Immutability

**Prepared for PRs #619, #620, #620.1**

Execute these 3 scenarios on a deployed build with Network logging enabled (F12 → Network tab).

---

## SCENARIO A: Canonical Exists → NO /pledge Requests

**Setup**:
1. Open DevTools (F12)
2. Go to Network tab
3. Filter: Type = XHR/Fetch
4. Manually set canonical in localStorage:
   ```javascript
   localStorage.setItem('wallet_v1_canonical_address', 'THRxxxx...(any THR address)');
   localStorage.setItem('wallet_v1_address', 'THRxxxx...');
   ```
5. Reload page (F5)

**Expected Network Log**:
```
✅ NO requests to /pledge or /pledge_submit
✅ NO requests to /api/pledge/...
✅ May see: /api/wallet/v1/status?address=THRxxxx (OK - this is state refresh)
```

**Expected UI**:
```
✅ Pledge Activation Panel is HIDDEN
✅ Create mode in dropdown is DISABLED or not visible
✅ Mode defaults to "Unlock" or "Import Signing Key"
```

**PASS/FAIL**: _______________

---

## SCENARIO B: Canonical Missing → /pledge Allowed

**Setup**:
1. Open DevTools (F12), Network tab
2. Clear localStorage:
   ```javascript
   localStorage.removeItem('wallet_v1_canonical_address');
   localStorage.removeItem('wallet_v1_address');
   ```
3. Reload page (F5)

**Expected Network Log**:
```
✅ Pledge Activation Panel is VISIBLE
✅ "Go to Pledge Activation" button is clickable
✅ Clicking button redirects to /pledge
```

**Expected UI**:
```
✅ Green "Go to Pledge Activation" button visible
✅ Mode dropdown shows "Create" as option
✅ User can initiate pledge flow
```

**PASS/FAIL**: _______________

---

## SCENARIO C: Restore Kit with Canonical → Server State Refresh

**Setup**:
1. Set up canonical in localStorage (as in Scenario A)
2. Open Network tab, filter by: name contains "status" or "wallet"
3. Trigger restore or import operation:
   - Upload Recovery Kit, OR
   - Paste recovery kit JSON, OR
   - Click "Import Signing Key"

**Expected Network Log** (in order):
```
Timeline:
T+0s   → Recovery Kit restore completes (decrypt, verify)
T+0.5s → ✅ GET /api/wallet/v1/status?address=THR... (STATE REFRESH)
         Response includes: { modal_state: 'active_wallet_...' }
T+1.0s → NO /pledge_submit request
T+1.2s → Page updates UI (no pledge panel shown)
```

**Expected UI State After Restore**:
```
✅ Modal/mode refreshes (NOT stuck on "no active wallet")
✅ Pledge Panel HIDDEN
✅ Mode set to "Unlock" or relevant state
✅ User sees unlock/import form, NOT pledge form
```

**PASS/FAIL**: _______________

---

## SERVER-SIDE VERIFICATION

### Verify PR #619 Responses

**Test 1: Repeat Pledge Request**
```bash
# First pledge
curl -X POST http://your-server/pledge_submit \
  -H "Content-Type: application/json" \
  -d '{
    "btc_address": "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD",
    "pledge_text": "test",
    "passphrase": "test1234"
  }'

# Response should have:
{
  "ok": true,
  "canonical_v1_address": "THRxxxx...",
  "created": true,
  "status": "newly_created"
}

# Second pledge (same BTC address)
curl -X POST http://your-server/pledge_submit \
  -H "Content-Type: application/json" \
  -d '{
    "btc_address": "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD",
    "pledge_text": "test",
    "passphrase": "test1234"
  }'

# Response should have:
{
  "ok": true,
  "canonical_v1_address": "THRxxxx...",  ← SAME as first
  "created": false,  ← NOT true
  "status": "already_has_canonical"
}
```

**PASS/FAIL**: _______________

---

## CRITICAL FAILURE CRITERIA

**🛑 STOP AND PATCH IF ANY OF THESE OCCUR:**

- [ ] After restore with canonical present, /pledge_submit is called
- [ ] After restore with canonical present, /pledge form is shown to user
- [ ] "Create Wallet V1" button is clickable when canonical exists
- [ ] Server returns new canonical (created=true) on repeat pledge same user
- [ ] Modal state shows "no_active_wallet" after successful restore
- [ ] User is redirected to /pledge after importing signing key with canonical

---

## PASS CRITERIA

**✅ READY FOR PR #621 IF ALL OF THESE ARE TRUE:**

- [ ] Scenario A: NO /pledge requests, pledge panel hidden
- [ ] Scenario B: /pledge allowed when canonical missing
- [ ] Scenario C: /api/wallet/v1/status called after restore, unlock state shown
- [ ] Server returns created=false on repeat pledge
- [ ] No canonical rotation observed (same address returned)
- [ ] All 3 code-level test suites pass (pytest)

---

## WHAT TO LOOK FOR IN NETWORK LOG

### ✅ GOOD Flow (Canonical Exists → Restore)
```
GET /api/wallet/v1/status?address=THRxxxx... 200
GET /api/wallet/profile?user_id=... 200
POST /api/wallet/v1/unlock 200
GET /assets/balances?... 200
(NO /pledge requests)
```

### ❌ BAD Flow (Would Indicate Bug)
```
GET /api/wallet/v1/status?address=THRxxxx... 200
POST /pledge_submit ...  ← ❌ SHOULD NOT HAPPEN
GET /pledge 200  ← ❌ SHOULD NOT HAPPEN
```

---

## TEST SUMMARY SHEET

| Scenario | Expected | Actual | PASS/FAIL |
|----------|----------|--------|-----------|
| A. Canonical exists, NO /pledge | 0 /pledge requests | ____ | _____ |
| B. Canonical missing, /pledge OK | /pledge shown | ____ | _____ |
| C. Restore → state refresh | /api/wallet/v1/status called | ____ | _____ |
| Server: Repeat pledge | created=false, same canonical | ____ | _____ |
| All tests: Code-level pytest | 13/13 pass | ____ | _____ |

---

**FINAL GATE**: Mark X if ALL are TRUE:
- [ ] Scenario A: PASS
- [ ] Scenario B: PASS
- [ ] Scenario C: PASS
- [ ] Server response verification: PASS
- [ ] Code-level tests: ALL PASS

**IF ALL ✅**: Ready to proceed to **PR #621 (State Machine Contract)**

**IF ANY ❌**: Return to PR #620.1 patch phase
