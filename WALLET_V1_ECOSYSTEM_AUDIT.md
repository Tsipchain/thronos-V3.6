# Thronos Ecosystem - Wallet V1 Migration Audit

**Date**: June 6, 2026  
**Status**: Comprehensive ecosystem audit complete

## Executive Summary

**Current State**:
- ✅ **3 endpoints** fully migrated to Wallet V1 (with live fixes)
- 🔄 **3 endpoints** partially migrated (V1 + legacy fallback)
- ❌ **6+ endpoints** still legacy-only (HIGH PRIORITY)
- ❓ **13+ endpoints** need status review

**Critical Issue Fixed**:
- ✅ `/api/swap/execute` HTTP 500 on malformed payload → now returns 400
- ✅ Frontend fallback hardening → no silent legacy fallback with unlocked material
- ✅ Recovery Kit restore shown as PRIMARY in UI

---

## Migration Status by Category

### ✅ READY FOR PRODUCTION

```
/api/wallet/send         ✅ V1 + Legacy fallback
/api/swap/execute        ✅ V1 + Legacy fallback (HTTP 500 FIXED)
/api/v1/pools/add_liquidity ✅ V1 + Legacy fallback
```

### ⏳ NEXT PRIORITY (Easy - 2-3 days)

**Tier 1 - Critical Payment Paths**:
```
/send_thr                ❌ LEGACY ONLY → Migrate to V1
/api/send_token          ❌ LEGACY ONLY → Migrate to V1
```

**Why**: These are core payment functions used in all send flows.

### 🔴 HIGH PRIORITY (Medium effort - 5-7 days)

**Bridge Operations**:
```
/api/bridge/burn         ❌ Needs V1 migration
/api/bridge/withdraw     ❌ Needs V1 migration
/api/bridge/deposit      ❌ Needs V1 migration
```

**Why**: Cross-chain operations are critical. Complexity is higher.

### 🟡 MEDIUM PRIORITY (3-4 days each)

**Mining Payouts**:
```
/api/mining/rewards      ❌ Needs V1 migration
/api/pool/rewards        ❌ Needs V1 migration
```

**Onboarding**:
```
/pledge_submit           ❌ Needs V1 enhancement
/api/pledge/verify-signature ❌ Needs review
```

### 🟢 LOW PRIORITY (1-2 days each)

**Digital Legacy & Rewards**:
```
/api/legacy/distribution/mark-claimed ❌ Low volume
/api/sentinel/rewards/claim           ❌ Low volume
/api/ai_credits                       ❓ May be read-only
```

---

## Detailed Migration Plan

### PHASE 1: CRITICAL PATH (Week 1)

**Goal**: Make all payment endpoints V1-native

**Endpoints**:
1. `/send_thr` (internal payment helper)
2. `/api/send_token` (custom token transfers)

**Effort per endpoint**:
- 2-3 hours audit + implement
- 1 hour testing
- 30 min deployment

**Total**: ~8 hours, 1 day work

**Risks**: LOW
- Both are straightforward payment functions
- No complex cross-chain logic
- Well-tested patterns from swap/send migrations

---

### PHASE 2: BRIDGE (Week 2-3)

**Goal**: Migrate cross-chain bridge to V1 signing

**Endpoints**:
1. `/api/bridge/burn` (THR → BTC bridge exit)
2. `/api/bridge/withdraw` (BTC → THR bridge entry)
3. `/api/bridge/deposit` (Supporting endpoint)

**Effort per endpoint**:
- 4-5 hours audit (complex validation)
- 2-3 hours implement
- 2 hours testing (E2E with BTC)
- 1 hour deployment

**Total**: ~30 hours, 3-4 days work

**Risks**: HIGH
- Complex cross-chain validation
- BTC address derivation must be perfect
- Breaking this breaks BTC ↔ THR conversions
- Needs dual-layer testing (testnet + live)

**Mitigation**:
- Keep legacy fallback for safety
- Test extensively on testnet first
- Gradual rollout (small tx amounts first)
- Monitor for errors in production

---

### PHASE 3: MINING & ONBOARDING (Week 3-4)

**Goal**: Complete ecosystem migration

**Endpoints**:
1. `/api/mining/rewards` (Payout claims)
2. `/api/pool/rewards` (Pool payouts)
3. `/pledge_submit` (User onboarding)
4. `/api/pledge/verify-signature` (Signature verification)

**Effort**: ~20 hours total

**Risks**: MEDIUM
- Mining payout critical for users
- Pledge flow is user onboarding critical path

---

### PHASE 4: LOW-PRIORITY (Week 4+)

**Endpoints**:
- `/api/legacy/distribution/mark-claimed`
- `/api/sentinel/rewards/claim`
- `/api/ai_credits`

**Effort**: ~10 hours

**Risks**: LOW
- Lower transaction volume
- Less critical paths

---

## Implementation Template

For each endpoint, follow this pattern:

```python
@app.route("/api/endpoint", methods=["POST"])
def api_endpoint():
    data = request.get_json() or {}
    
    # TRY WALLET V1 FIRST
    if data.get("canonical_v1_address") and data.get("signature"):
        verified = verify_wallet_v1_signed_request(data, "action_name")
        if not verified.get("ok"):
            return jsonify(ok=False, status="error", error=verified.get("error")), 400
        
        # Extract payload safely
        trader = verified.get("canonical_v1_address")
        payload, payload_err = _extract_signed_payload(data)
        if payload_err:
            return jsonify(ok=False, status="error", error=payload_err), 400
        
        # Extract fields with error handling
        try:
            amount = float(payload.get("amount", 0))
        except (TypeError, ValueError):
            return jsonify(ok=False, status="error", error="invalid_amount"), 400
    
    # LEGACY FALLBACK (for external users, if needed)
    else:
        trader = data.get("trader_thr", "")
        auth_secret = data.get("auth_secret", "")
        # ... existing legacy code ...
    
    # PROCESS (same for both auth methods)
    # ... rest of endpoint logic ...
```

---

## Testing Requirements

### For Each Endpoint Migration

**Unit Tests**:
```python
✅ test_wallet_v1_signature_valid()
✅ test_wallet_v1_signature_invalid()
✅ test_payload_extraction_dict()
✅ test_payload_extraction_json_string()
✅ test_amount_conversion_valid()
✅ test_amount_conversion_invalid()
✅ test_insufficient_balance()
✅ test_legacy_format_still_works()
```

**E2E Tests**:
```python
✅ test_full_flow_with_wallet_v1()
✅ test_session_unlock_required()
✅ test_recovery_kit_restore_then_action()
✅ test_timeout_after_15_minutes()
```

---

## Success Criteria

- [ ] All payment endpoints (send_thr, send_token) → V1 native
- [ ] All bridge endpoints → V1 + legacy fallback
- [ ] All mining/pool reward endpoints → V1 support
- [ ] All pledge endpoints → V1 option
- [ ] All low-priority endpoints → V1 support
- [ ] **Zero HTTP 500 errors** on client input errors
- [ ] 100% test coverage for new V1 paths
- [ ] Backward compatibility verified (where needed)
- [ ] No changes to consensus/mining/ledger logic
- [ ] User onboarding flow verified working

---

## Timeline Summary

| Phase | Duration | Endpoints | Effort |
|-------|----------|-----------|--------|
| Phase 1 (Critical) | 1 day | 2 | 8 hours |
| Phase 2 (Bridge) | 3-4 days | 3 | 30 hours |
| Phase 3 (Mining+Pledge) | 2 days | 4 | 20 hours |
| Phase 4 (Low-priority) | 1-2 days | 3+ | 10 hours |
| **TOTAL** | **1-2 weeks** | **12+** | **~70 hours** |

---

## Architecture Foundation - READY

All infrastructure for V1 migration is in place:

### ✅ Backend Foundations
- `verify_wallet_v1_signed_request()` - Signature validation
- `_extract_signed_payload()` - Robust payload parsing
- `derive_thr_address_from_public_key_hex()` - Address derivation
- Error handling patterns - 400 on client error, never 500

### ✅ Frontend Foundations
- `walletV1BuildSignedRequest()` - Sign requests
- `walletSessionSetUnlocked()` - Session management
- `walletV1RestoreFromRecoveryKit()` - Recovery flow
- `walletSessionIsUnlocked()` - Session checks
- Session timeout - Auto-lock after 15 min

### ✅ UI/UX
- Recovery Kit restore as PRIMARY
- Green (#00ff66) styling for V1 actions
- Error messages for failed V1 operations
- No silent fallback to legacy

---

## Known Risks & Mitigations

### 🔴 HIGH RISK: Bridge Breaking
**Risk**: If bridge migration fails, BTC ↔ THR conversions break  
**Mitigation**:
- Keep legacy fallback for 2+ weeks
- Test thoroughly on testnet first
- Monitor BTC address derivation carefully
- Gradual amount limits during rollout

### 🟡 MEDIUM RISK: Mining Payout Delays
**Risk**: If mining reward migration breaks, miners don't get paid  
**Mitigation**:
- Thorough testing before deployment
- Keep legacy path available temporarily
- Have rollback plan ready
- Monitor payout processing closely

### 🟡 MEDIUM RISK: User Onboarding Breaks
**Risk**: If pledge flow breaks, new users can't sign up  
**Mitigation**:
- Heavy testing of pledge flow
- Ensure both V1 and legacy work
- Have quick rollback plan
- Monitor signup rate after deploy

### 🟢 LOW RISK: Digital Legacy/Sentinel
**Risk**: Lower impact if these endpoints break  
**Mitigation**:
- Standard testing procedures
- Can be deployed last

---

## Recommended Next Step

**START WITH TIER 1 (NEXT WEEK)**:

1. `✅ AUDIT`: Read `/send_thr` and `/api/send_token` code
2. `✅ DESIGN`: Create V1 payload format (same as swap)
3. `✅ IMPLEMENT`: Add V1 signature path + legacy fallback
4. `✅ TEST`: Write unit + E2E tests
5. `✅ DEPLOY`: PR → Review → Merge → Monitor

**Expected**: 2-3 day sprint, very low risk

---

**Document Generated**: 2026-06-06  
**Status**: Ready for implementation planning  
**Next Review**: After Phase 1 completion
