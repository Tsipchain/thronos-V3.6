# Deploy Checklist: Hotfix #622 - Production Crash + Canonical Immutability

**Date**: 2026-06-10  
**Hotfix**: #622  
**Commits**: c2d4f1b (hotfix), abdad03 (tests)  
**Branch**: claude/dreamy-bohr-6j1rO  
**PR**: #619 (GitHub)

---

## Phase 1: Pre-Deploy Verification (LOCAL)

### Code Review
- [x] All 6 regression tests passing
- [x] No undefined variable references
- [x] DOM access is null-safe
- [x] Pledge button has pathname check
- [x] No breaking API changes
- [x] Backward compatible response schemas

### Test Suite Status
```bash
python tests/test_hotfix_622_production_mode_crash.py
```

Expected Output:
```
✅ ALL REGRESSION TESTS PASSED (6/6)

✓ test_applyWalletV1ProductionMode_no_undefined_vars
✓ test_applyWalletV1ProductionMode_null_safe_dom_access
✓ test_pledge_button_no_self_redirect_on_pledge_route
✓ test_no_pledge_redirect_when_canonical_exists
✓ test_create_mode_disabled_when_canonical_loaded
✓ test_pledge_submit_returns_created_false_when_canonical_exists
```

- [ ] Tests pass locally
- [ ] No Python errors
- [ ] No regex exceptions

---

## Phase 2: Staging Deployment

### Environment Preparation
- [ ] Staging database backup created
- [ ] Staging server health check passed
- [ ] Network connectivity verified

### Deploy Steps (Staging)
```bash
# 1. Pull latest commits
git fetch origin claude/dreamy-bohr-6j1rO
git checkout claude/dreamy-bohr-6j1rO

# 2. Deploy code
./deploy.sh staging --hotfix-622

# 3. Restart services
systemctl restart thronos-wallet-service
systemctl status thronos-wallet-service
```

- [ ] Deploy completed without errors
- [ ] Services restarted successfully
- [ ] No new log errors

### Browser Verification (Staging)

**Open**: http://staging.thronos.local/wallet

1. **Console Check (F12 → Console)**:
   ```javascript
   // Should show NO errors
   // Look for: ReferenceError, TypeError, SyntaxError
   ```
   - [ ] Zero ReferenceError messages
   - [ ] Zero "advancedImportForm" errors
   - [ ] All warnings acceptable

2. **Test Scenario A: Canonical Exists**:
   ```javascript
   // In browser console:
   localStorage.setItem('wallet_v1_canonical_address', 'THRtest123456789');
   localStorage.setItem('wallet_v1_address', 'THRtest123456789');
   location.reload();
   ```
   - [ ] Page loads without crash
   - [ ] Pledge panel is HIDDEN
   - [ ] Create mode is DISABLED
   - [ ] Mode shows "Unlock" or "Import"

3. **Test Scenario B: Canonical Missing**:
   ```javascript
   // In browser console:
   localStorage.removeItem('wallet_v1_canonical_address');
   localStorage.removeItem('wallet_v1_address');
   location.reload();
   ```
   - [ ] Page loads without crash
   - [ ] Pledge panel is VISIBLE
   - [ ] "Go to Pledge Activation" button clickable
   - [ ] Create mode shows in dropdown

4. **Test Scenario C: Pledge Button Self-Redirect**:
   ```javascript
   // Go to page without canonical
   location.href = '/pledge';
   // Wait 1 second
   // Click "Go to Pledge Activation" button
   ```
   - [ ] No self-redirect loop
   - [ ] Page stable (no reloads)
   - [ ] Button click does not refresh page if already on /pledge
   - [ ] Button is functional

### Network Log Verification (Staging)

**Open DevTools → Network tab**

- [ ] Filter for `/pledge` requests
- [ ] Filter for `/api/wallet/v1/status` requests
- [ ] Verify request patterns match expected flows:
  - Canonical exists: NO /pledge requests ✓
  - Canonical missing: /pledge requests OK ✓

### QA Scenario Checklist (Staging)

Run scenarios from MANUAL_QA_CHECKLIST.md:

| Scenario | Expected | Actual | PASS |
|----------|----------|--------|------|
| A: Canonical exists, NO /pledge | 0 /pledge requests | _____ | [ ] |
| B: Canonical missing, /pledge OK | /pledge shown | _____ | [ ] |
| C: Restore → state refresh | /api/wallet/v1/status called | _____ | [ ] |
| Server: Repeat pledge | created=false, same canonical | _____ | [ ] |

---

## Phase 3: Production Deployment

### Pre-Production Checklist
- [ ] Staging QA passed all scenarios
- [ ] No new errors in staging logs
- [ ] Database migrations verified (if any)
- [ ] Rollback procedure tested

### Production Deploy Steps
```bash
# 1. Notify on-call team
echo "Deploying hotfix #622 - Production Crash Fix"

# 2. Create deployment backup
./backup.sh production --label=pre-hotfix-622

# 3. Deploy code
./deploy.sh production --hotfix-622

# 4. Verify deployment
curl https://api.thronos.io/health
curl https://api.thronos.io/api/wallet/v1/status?address=THRtest

# 5. Monitor services
./monitor.sh --duration=5m
```

- [ ] Deployment completed
- [ ] All services healthy
- [ ] Error rate normal

### Post-Deploy Verification (PRODUCTION)

**First 15 minutes**:

1. **Error Monitoring**:
   ```bash
   tail -f logs/thronos-wallet.log | grep -i "referenceerror\|advancedImportForm"
   ```
   - [ ] Zero ReferenceError occurrences
   - [ ] Zero "advancedImportForm" errors
   - [ ] Request rate normal

2. **API Verification**:
   ```bash
   # Test pledge response structure
   curl -X POST https://api.thronos.io/pledge_submit \
     -H "Content-Type: application/json" \
     -d '{
       "btc_address": "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD",
       "pledge_text": "test",
       "passphrase": "test1234"
     }' | jq .
   ```
   - [ ] Response includes `canonical_v1_address`
   - [ ] Response includes `created` field
   - [ ] Response includes `status` field
   - [ ] HTTP 200 status

3. **User Traffic Check**:
   - [ ] /pledge requests: 0-10 (expected new user rate)
   - [ ] Wallet page loads: > 100 (normal traffic)
   - [ ] Error rate: < 0.1%

### 24-Hour Monitoring Window

**Monitor these metrics continuously**:

| Metric | Baseline | Alert Threshold | Status |
|--------|----------|-----------------|--------|
| ReferenceError count | 0 | > 0 | [ ] |
| /pledge requests | 5-20/hour | > 50/hour | [ ] |
| Wallet page 5xx errors | 0-1/hour | > 5/hour | [ ] |
| API response time | <100ms | > 500ms | [ ] |
| Server CPU | <40% | > 80% | [ ] |

**Log grep commands** (run hourly):
```bash
# Check for ReferenceError
grep -i "referenceerror\|advancedImportForm" logs/thronos-wallet.log | wc -l

# Check for /pledge spam
grep "GET /pledge" logs/access.log | wc -l

# Check for new errors
grep "ERROR\|CRITICAL" logs/thronos-wallet.log | tail -20
```

- [ ] Hour 1: No new errors
- [ ] Hour 6: Stable operation
- [ ] Hour 12: All metrics normal
- [ ] Hour 24: Declare success

---

## Phase 4: Rollback Procedure

**Only if critical issues detected**:

### Rollback Steps
```bash
# 1. Identify issue
# 2. Create incident ticket
# 3. Notify stakeholders
# 4. Execute rollback

git revert c2d4f1b abdad03  # Reverts to commit 589adaa

./deploy.sh production --hotfix-rollback

# 5. Verify rollback
curl https://api.thronos.io/health
```

### Rollback Criteria
Execute ONLY if:
- [ ] ReferenceError reappears (> 10 occurrences/hour)
- [ ] Wallet pages returning 500 errors (> 5/hour)
- [ ] /pledge requests causing redirect loops
- [ ] Pledge API returning malformed responses
- [ ] Database connection failures
- [ ] Authentication bypass detected

### Rollback Verification
- [ ] Services healthy after rollback
- [ ] Error rates returned to baseline
- [ ] No data corruption
- [ ] Users can access wallet

---

## Sign-Off

### Deployment Team
- Deployer: _____________________ Date: ________
- Reviewer: _____________________ Date: ________

### QA Team  
- Tester: ______________________ Date: ________
- QA Lead: ______________________ Date: ________

### On-Call Team
- On-Call: ______________________ Date: ________
- Escalation: ___________________ Date: ________

---

## Post-Deploy Notes

**Success Indicators**:
- ✅ No ReferenceError: advancedImportForm  
- ✅ No infinite /pledge redirects
- ✅ Canonical address never rotates
- ✅ All wallet flows functional
- ✅ User experience unaffected
- ✅ Zero new production bugs

**Known Limitations**:
- None

**Follow-up Actions**:
1. Monitor for 24h minimum
2. If stable: Proceed to PR #621 (State Machine Contract)
3. If issues: Debug and patch in new hotfix

---

## Reference Documents

- PR #619: https://github.com/Tsipchain/thronos-V3.6/pull/619
- Regression Tests: `tests/test_hotfix_622_production_mode_crash.py`
- Manual QA: `MANUAL_QA_CHECKLIST.md`
- Merge Readiness: `PR_MERGE_READINESS_REPORT.md`

---

**Session**: https://claude.ai/code/session_01NaqX5NN9yVWWWEFN7kiTce
