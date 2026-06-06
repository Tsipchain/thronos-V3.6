# Production E2E Checklist - Wallet V1 Ready

**Purpose**: Manual QA validation before mainnet deployment  
**Status**: Comprehensive checklist for fresh browser + mobile restore  
**Duration**: ~30-45 minutes per scenario

---

## Scenario 1: Fresh Browser (Web)

### Setup
- [ ] Use incognito/private browser window (no existing localStorage)
- [ ] Clear cookies/storage
- [ ] Navigate to production URL

### Recovery Kit Restore

- [ ] Wallet widget shows "Login" button
- [ ] Click button → modal opens
- [ ] DEFAULT MODE: "Create Wallet V1" is shown
- [ ] Has input for PIN (optional)
- [ ] Switch to "Unlock Wallet V1" mode
- [ ] See "Enter PIN" input (required)
- [ ] PIN field is masked (dots, not visible)

### Recovery Kit Upload

- [ ] Modal shows dropdown to select mode
- [ ] "Unlock Wallet V1" mode → PIN + unlock button
- [ ] Recovery Kit file upload option visible (in advanced or as separate form)
- [ ] Upload Recovery Kit JSON file
- [ ] File parses: canonical address shows in diagnostics
- [ ] Enter correct PIN
- [ ] Click "Unlock Wallet V1"
- [ ] Success message: "Wallet unlocked" or similar
- [ ] Wallet widget shows wallet address (first 10 chars + ...)
- [ ] Balance loads (may take 2-3 sec)

### Session Active (15-min TTL)

- [ ] Status shows "Session active: 14:xx" (countdown visible)
- [ ] Can click wallet widget → shows balance, tokens
- [ ] Can perform actions WITHOUT re-entering PIN

### Swap (No PIN Re-entry)

- [ ] Navigate to /swap
- [ ] Page loads without prompting for PIN
- [ ] "From" address is correct (matches restored wallet)
- [ ] Select token pair (e.g., THR → USDC)
- [ ] Enter amount (small test amount)
- [ ] Click "Execute Swap"
- [ ] Swap succeeds, balance updates
- [ ] ✅ No HTTP 500 errors
- [ ] ✅ Error messages are 400 with clear codes (if any error)

### Add Liquidity (No PIN Re-entry)

- [ ] Navigate to /pools
- [ ] Page loads without prompting for PIN
- [ ] Select pool (e.g., THR-USDC)
- [ ] Enter amounts
- [ ] Click "Add Liquidity"
- [ ] Transaction succeeds
- [ ] Balance updates
- [ ] ✅ No errors during session TTL

### Send (No PIN Re-entry)

- [ ] Navigate to /send
- [ ] Page loads without prompting for PIN
- [ ] Recipient address field visible
- [ ] Amount field visible
- [ ] Select token (THR default)
- [ ] Enter test amount
- [ ] Click "Send"
- [ ] Transaction succeeds
- [ ] ✅ Session still active (timer counts down)

### Session TTL Expiry (15 minutes)

- [ ] Let countdown reach 0:00 (or wait 15 min)
- [ ] Try to perform another action (e.g., swap again)
- [ ] UI prompts for PIN again
- [ ] Enter PIN
- [ ] Action succeeds
- [ ] New 15-min session starts

### Music Page (Wallet Stability)

- [ ] Navigate to /music
- [ ] Wallet widget still visible in top bar
- [ ] Wallet widget is responsive (click doesn't freeze)
- [ ] Music page loads (may have 404 covers, that's OK)
- [ ] Wallet balance still shows in widget
- [ ] Can click wallet → still shows correct address
- [ ] Music errors don't affect wallet UI
- [ ] Can navigate back to swap/pools/send
- [ ] Wallet still has session active (countdown visible)

### Browser Refresh (Session Persistence)

- [ ] Press F5 (hard refresh)
- [ ] Page reloads
- [ ] Wallet address still in localStorage
- [ ] Encrypted key still in localStorage
- [ ] Runtime signing material is GONE (expected)
- [ ] Wallet widget shows address BUT with "Unlock" button
- [ ] Countdown timer is RESET (session restarted after refresh)
- [ ] Click "Unlock" → enter PIN again
- [ ] Session restarts (new 15-min timer)

### Logout / Disconnect

- [ ] Click wallet widget → see "Lock" button
- [ ] Click "Lock Wallet"
- [ ] Runtime material cleared (expected)
- [ ] Wallet widget shows address but locked state
- [ ] Try to perform action → prompts for unlock
- [ ] Enter PIN → unlocks

### Clear Wallet / Forget Device

- [ ] Click wallet widget → see "Advanced" or recovery options
- [ ] Click "Clear All Wallet Data"
- [ ] Confirmation: "Are you sure?"
- [ ] Click confirm
- [ ] All localStorage cleared
- [ ] Wallet widget resets to "Login"
- [ ] Must upload Recovery Kit again to restore

---

## Scenario 2: Mobile Reinstall

### Setup
- [ ] Mobile device (iOS or Android)
- [ ] App installed
- [ ] Clear app data / uninstall
- [ ] Reinstall app fresh

### On Fresh Install

- [ ] App opens
- [ ] Wallet widget shows "Login"
- [ ] No localStorage state remaining
- [ ] All previous wallet data is gone (expected)

### Recovery from Recovery Kit

- [ ] Click "Login" in wallet
- [ ] Modal shows mode selection (Create/Unlock/Migrate)
- [ ] Switch to "Unlock" mode
- [ ] Recovery Kit import option available
- [ ] Have Recovery Kit JSON file (from earlier backup)
- [ ] Import Recovery Kit:
  - [ ] Can paste JSON text directly
  - [ ] OR upload file (if file picker available)
- [ ] Canonical address populates
- [ ] Enter PIN
- [ ] Click "Unlock"
- [ ] Success: wallet unlocked
- [ ] Balance loads

### Mobile Session TTL

- [ ] Countdown shows on wallet widget
- [ ] Can perform swap without PIN (within TTL)
- [ ] Can perform send without PIN (within TTL)
- [ ] Can perform pool action without PIN (within TTL)
- [ ] After 15 min: next action prompts for PIN

### Mobile Screen Rotation / Backgrounding

- [ ] Perform swap
- [ ] Rotate phone (landscape → portrait)
- [ ] UI adjusts, session still active
- [ ] Background app (home button)
- [ ] Bring back to foreground
- [ ] Session still active (if less than 15 min elapsed)
- [ ] Countdown still counts down

### Mobile Refresh / App Restart

- [ ] Close app completely
- [ ] Reopen app
- [ ] Wallet address still shows (stored locally)
- [ ] Runtime material is gone (expected)
- [ ] Click "Unlock"
- [ ] Enter PIN
- [ ] New session starts

### Mobile Multiple Apps (Split Screen)

- [ ] Open app + browser in split view
- [ ] Wallet widget functional in app
- [ ] Can perform actions
- [ ] Session countdown visible
- [ ] No state conflicts between app and web

---

## Scenario 3: Edge Cases

### Malformed Recovery Kit

- [ ] Try to import corrupted JSON file
- [ ] Error message: "Invalid Recovery Kit format" (400, not 500)
- [ ] Can dismiss and try again
- [ ] App doesn't crash

### Wrong PIN

- [ ] Import valid Recovery Kit
- [ ] Enter WRONG PIN
- [ ] Error: "Invalid PIN" or "PIN mismatch"
- [ ] Can try again
- [ ] No account lockout (after N attempts, show "contact support")

### Missing Signing Key

- [ ] Situation: canonical address exists but no encrypted key
- [ ] Recovery Kit modal appears (auto-detected)
- [ ] UI forces "Unlock" mode
- [ ] User prompted to upload Recovery Kit
- [ ] ✅ No fallback to legacy auth

### Corrupted Session (Runtime Material Lost)

- [ ] Unlock wallet normally
- [ ] Browser dev tools: delete `walletSession` from memory (dev scenario)
- [ ] Try to perform action
- [ ] Either: shows "Unlock wallet" prompt OR gives clear error
- [ ] ✅ No hang / doesn't silently fail

### 404 Covers on Music Page

- [ ] Navigate to /music
- [ ] Some cover images fail to load (404)
- [ ] Music page shows error for covers but continues loading
- [ ] Wallet widget is NOT affected
- [ ] Can still perform wallet actions

### Concurrent Tabs

- [ ] Open wallet in Tab A
- [ ] Open same wallet in Tab B (same browser)
- [ ] Unlock in Tab A
- [ ] Tab B: wallet still locked (browsers don't sync runtime memory)
- [ ] Unlock in Tab B separately
- [ ] Each tab has independent session TTL
- [ ] No cross-tab conflicts

---

## Performance Checks

### Swap Execution Time

- [ ] Small swap (0.001 THR → USDC)
- [ ] Execution time: target <3 seconds
- [ ] Status: "Swap executed"
- [ ] Balance updates immediately

### Pool Add Liquidity Time

- [ ] Add small liquidity (0.001 THR)
- [ ] Execution time: target <3 seconds
- [ ] Status: "Liquidity added"
- [ ] LP token balance updates

### Music Page Load Time

- [ ] Navigate to /music
- [ ] Page load time: target <2 seconds
- [ ] Music player loads
- [ ] Playlist loads
- [ ] Can play audio without lag

### Wallet Widget Responsiveness

- [ ] Click wallet widget
- [ ] Popup appears instantly (<100ms)
- [ ] Balance visible
- [ ] No jank/freeze

---

## Error Scenarios

### Insufficient Balance

- [ ] Try to swap more than balance
- [ ] Error: "Insufficient balance" (400)
- [ ] Suggested amount shown
- [ ] ✅ NOT HTTP 500

### Invalid Token

- [ ] Try to swap unsupported token
- [ ] Error: "Unsupported token" (400)
- [ ] ✅ NOT HTTP 500

### Slippage Too High

- [ ] Do swap with very high slippage tolerance
- [ ] If slippage exceeded: "Slippage too high" (400)
- [ ] Show expected vs actual amounts
- [ ] ✅ NOT HTTP 500

### Network Timeout

- [ ] Slow network (throttle in dev tools)
- [ ] Perform action
- [ ] Either: timeout error with retry OR completes eventually
- [ ] ✅ NOT hang indefinitely
- [ ] ✅ UI responsive during wait

### Recovery Kit Upload Failure

- [ ] Try to upload invalid Recovery Kit
- [ ] Error: "Invalid Recovery Kit format" (400)
- [ ] Can retry
- [ ] App doesn't crash

---

## Regression Checks

### Legacy Auth Still Works (Backward Compat)

- [ ] Create fresh wallet (no Recovery Kit)
- [ ] Pledge with legacy (auth_secret)
- [ ] Can still use legacy flow for users who haven't migrated
- [ ] ✅ No breaking changes

### Old Wallets Still Accessible

- [ ] Import old wallet (no V1 encryption)
- [ ] Can still access via legacy migrate flow
- [ ] Balance accessible
- [ ] Can perform actions (legacy path)

### Browser Extensions Don't Break

- [ ] Have Metamask/Wallet extensions installed
- [ ] Wallet V1 widget doesn't interfere
- [ ] Extensions still work
- [ ] No console errors about "MaxListenersExceeded"

---

## Success Criteria - ALL MUST PASS

```
✅ Fresh browser restore: <1 min from upload to first action
✅ Session TTL: exactly 15 min countdown
✅ No PIN re-entry within TTL: 15+ actions without re-prompting
✅ After TTL: next action prompts for PIN
✅ Swap: executes in <3 sec, no 500 errors
✅ Pools: executes in <3 sec, no 500 errors
✅ Send: executes in <3 sec, no 500 errors
✅ Music: wallet widget remains responsive, 404 covers don't break wallet
✅ Refresh: encrypted key persists, runtime material lost (expected)
✅ Mobile: same flow works on iOS/Android
✅ Error messages: all user-errors return 400 with clear codes
✅ No regressions: legacy auth still works
✅ No console errors: MaxListenersExceeded, wallet state leaks, etc.
```

---

## Sign-Off

| Scenario | Status | Tester | Date |
|----------|--------|--------|------|
| Fresh Browser (Web) | ☐ PASS / ☐ FAIL | | |
| Mobile Reinstall | ☐ PASS / ☐ FAIL | | |
| Edge Cases | ☐ PASS / ☐ FAIL | | |
| Performance | ☐ PASS / ☐ FAIL | | |
| Error Scenarios | ☐ PASS / ☐ FAIL | | |
| Regression Checks | ☐ PASS / ☐ FAIL | | |

**Overall Result**: ☐ READY FOR PRODUCTION / ☐ NEEDS FIXES

**Issues Found**:
```
1. ...
2. ...
```

**Approved By**: ____________________  
**Date**: ____________________

---

**Checklist Version**: 1.0  
**Last Updated**: 2026-06-06  
**Next Review**: Post-mainnet-deployment
