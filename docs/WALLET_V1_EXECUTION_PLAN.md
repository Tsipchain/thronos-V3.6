# Wallet V1 Unified Signing Contract - Execution Plan

## Overview

Consolidate all Wallet V1 signing flows (swap, pools, send, tips, bridge, AI, L2E, IoT, NFT) into **one unified contract**.

**Goal**: Eliminate payload shape chaos. Single entry point: `walletV1BuildSignedRequest(action, payload)`

## Phase 1: Frontend Unification (Week 1-2)

### 1.1 Unified Signing Contract

**File**: `static/wallet_v1_signing_contract.js` (NEW)

```javascript
/**
 * SINGLE ENTRY POINT for all V1 signing
 * 
 * @param {string} action - e.g., 'swap', 'add_liquidity', 'send_thr', 'tip_artist', 'bridge_deposit'
 * @param {object} payload - action-specific data
 * @returns {object} signed request or error
 * 
 * @throws {wallet_locked_reunlock_required} - encrypted key exists but not unlocked
 * @throws {recovery_kit_required} - no key at all
 * @throws {wallet_v1_signing_failed} - signing failed (no fallback)
 */
async function walletV1BuildSignedRequest(action, payload) {
    // 1. Check wallet state
    const state = walletSession.getWalletState?.();
    const addr = walletSession.getAddress?.();
    
    if (!addr) {
        throw {error: 'recovery_kit_required', detail: 'No canonical address'};
    }
    
    // 2. Check signing material
    if (!walletSession.isBound?.()) {
        // Has encrypted key but not unlocked
        throw {error: 'wallet_locked_reunlock_required', detail: 'Unlock required'};
    }
    
    // 3. Build canonical payload based on action
    const canonicalPayload = buildCanonicalPayload(action, payload, addr);
    
    // 4. Sign
    try {
        const {publicKey, signature, signatureFormat} = await walletSession.signCanonical(canonicalPayload);
        
        // 5. Return signed request (standard format)
        return {
            ok: true,
            canonical_v1_address: addr,
            signature: signature,
            public_key: publicKey,
            signature_format: signatureFormat,
            nonce: payload.nonce || generateNonce(),
            timestamp: Date.now(),
            action: action,
            payload: payload
        };
    } catch (err) {
        // NO FALLBACK - explicit error
        throw {error: 'wallet_v1_signing_failed', detail: err.message};
    }
}

/**
 * Build canonical JSON matching backend expectations
 */
function buildCanonicalPayload(action, payload, addr) {
    const base = {
        from: addr,
        nonce: payload.nonce || generateNonce(),
        timestamp: payload.timestamp || Math.floor(Date.now() / 1000)
    };
    
    switch(action) {
        case 'swap':
            return {
                ...base,
                action: 'swap',
                amount_in: payload.amountIn,
                token_in: payload.tokenIn,
                token_out: payload.tokenOut,
                type: 'swap',
                to: payload.poolAddress
            };
        case 'add_liquidity':
            return {
                ...base,
                action: 'add_liquidity',
                amount: payload.amount,
                token: payload.token,
                to: payload.poolId
            };
        // ... other actions
        default:
            throw new Error(`Unknown action: ${action}`);
    }
}

function generateNonce() {
    return Math.floor(Math.random() * 2**32).toString(16);
}
```

### 1.2 Event Bus (State Sync)

**File**: `static/wallet_v1_event_bus.js` (NEW)

```javascript
/**
 * Single event source for wallet state changes
 * All pages (swap, pools, music, etc.) subscribe to these
 */
class WalletV1EventBus {
    constructor() {
        this.listeners = {};
    }
    
    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
    }
    
    off(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
        }
    }
    
    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(cb => cb(data));
        }
    }
}

// Global instance
window.walletV1Events = new WalletV1EventBus();

// Events emitted:
// wallet:unlocked - {address, timestamp, sessionTTL}
// wallet:locked - {address, reason}
// wallet:session_expired - {address, requiresReunlock: true}
// wallet:recovery_required - {reason: 'missing_key' | 'mismatch'}
// wallet:state_changed - {state: '...', address, locked}
```

### 1.3 Update All Call Sites

**Swap (swap.html)**:
```javascript
async function doSwap() {
    try {
        const request = await walletV1BuildSignedRequest('swap', {
            amountIn: inputAmount,
            tokenIn: selectedToken,
            tokenOut: targetToken,
            poolAddress: pool.address,
            nonce: generateNonce()
        });
        
        const response = await fetch('/api/swap/execute', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(request)
        });
        
        if (!response.ok) {
            const error = await response.json();
            showError(`Swap failed: ${error.error}`);
            return;
        }
        
        const result = await response.json();
        showSuccess('Swap executed');
    } catch (err) {
        if (err.error === 'wallet_locked_reunlock_required') {
            promptPinUnlock();
        } else if (err.error === 'recovery_kit_required') {
            showRecoveryKit();
        } else {
            showError(`Signing failed: ${err.detail}`);
        }
    }
}
```

**Pools (pools.html)**: Similar pattern

**Send (send_thr endpoint)**: Similar pattern

**Music Tips**: Similar pattern

---

## Phase 2: Backend Unification (Week 2-3)

### 2.1 Unified Verification Function

**File**: `server.py` (existing, consolidate)

```python
def verify_wallet_v1_signed_request(request_data, expected_action):
    """
    SINGLE VERIFIER for all V1 signed requests
    
    Returns: {ok: bool, address: str, payload: dict, error: str}
    Raises: HTTPException(400, error_code) for all validation failures
    """
    
    # 1. Parse signed request
    if not request_data.get('canonical_v1_address'):
        return abort(400, {'error': 'missing_address'})
    
    addr = request_data['canonical_v1_address']
    signature = request_data.get('signature')
    public_key = request_data.get('public_key')
    signature_format = request_data.get('signature_format', 'DER')
    
    if not signature or not public_key:
        return abort(400, {'error': 'missing_signature'})
    
    # 2. Rebuild canonical JSON (same as frontend)
    payload = request_data.get('payload', {})
    canonical = build_canonical_payload(
        request_data['action'],
        payload,
        addr
    )
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    
    # 3. Verify signature
    try:
        verified = verify_ecdsa_secp256k1(
            message=canonical_json.encode(),
            signature=signature,
            public_key=public_key,
            signature_format=signature_format
        )
        if not verified:
            return abort(400, {'error': 'invalid_signature'})
    except Exception as e:
        return abort(400, {'error': 'signature_verification_failed', 'detail': str(e)})
    
    # 4. Verify action matches
    if request_data['action'] != expected_action:
        return abort(400, {'error': 'action_mismatch'})
    
    # 5. Return verified request
    return {
        'ok': True,
        'address': addr,
        'payload': payload,
        'signature': signature
    }
```

### 2.2 Update All Endpoints

**API Pattern**:
```python
@app.route("/api/swap/execute", methods=["POST"])
def api_swap_execute():
    data = request.get_json(silent=True) or {}
    
    # Use unified verifier
    verified = verify_wallet_v1_signed_request(data, 'swap')
    if not verified['ok']:
        return jsonify(ok=False, error=verified['error']), 400
    
    # Process swap with verified address + payload
    address = verified['address']
    payload = verified['payload']
    
    # ... execute swap logic
```

**Endpoints to Update**:
- /api/swap/execute ✅ (already done in PR #614)
- /api/v1/pools/add ⚠️ (needs unified signing)
- /api/v1/pools/remove ⚠️ (needs unified signing)
- /api/send_thr ⚠️ (phase 2)
- /api/wallet/tip ⚠️ (phase 2)
- /api/bridge/deposit ⚠️ (phase 2)

### 2.3 Backward Compat

**Policy**: 
- If NO V1 fields in request → allow legacy auth_secret (deprecated path)
- If V1 fields present → MUST have valid V1 signature (no fallback)

```python
def api_send_thr():
    data = request.get_json(silent=True) or {}
    
    # Check: V1 or legacy?
    if data.get('canonical_v1_address') or data.get('signature'):
        # V1 path (no fallback)
        verified = verify_wallet_v1_signed_request(data, 'send')
        # ... V1 execution
    else:
        # Legacy path (deprecated)
        auth_secret = data.get('auth_secret')
        # ... legacy execution (will be removed in v4)
```

---

## Phase 3: Service Integration (Week 3-4)

### Endpoints Requiring Unified Signing

| Service | Endpoint | Current Auth | V1 Target | Status | PR |
|---------|----------|--------------|-----------|--------|-----|
| Swap | /api/swap/execute | V1 | V1 unified | ✅ Done | #614 |
| Pools | /api/v1/pools/add | V1 custom | V1 unified | ⚠️ Queue | #615 |
| Pools | /api/v1/pools/remove | V1 custom | V1 unified | ⚠️ Queue | #615 |
| Send | /api/send_thr | Legacy | V1 unified | ⏳ Phase 2 | #616 |
| Music | /api/wallet/tip | Legacy | V1 unified | ⏳ Phase 2 | #617 |
| L2E | /api/l2e/claim_rewards | Legacy | V1 unified | ⏳ Phase 2 | #618 |
| University | /api/tenant/action | Legacy | V1 unified | ⏳ Phase 2 | #619 |
| Bridge | /api/bridge/deposit | Legacy | V1 unified | ⏳ Phase 2 | #620 |
| NFT | /api/nft/buy | Legacy | V1 unified | ⏳ Phase 2 | #621 |

---

## Testing Strategy

### Unit Tests (New)

```python
# tests/test_wallet_v1_unified_signing.py

def test_swap_canonical_payload():
    payload = buildCanonicalPayload('swap', {...}, 'THR...')
    assert 'action' in payload
    assert payload['action'] == 'swap'
    assert 'token_in' in payload

def test_verify_swap_signature():
    request = generate_valid_swap_request()
    result = verify_wallet_v1_signed_request(request, 'swap')
    assert result['ok'] == True

def test_invalid_signature_returns_400():
    request = generate_invalid_swap_request()
    with pytest.raises(HTTPException) as exc:
        verify_wallet_v1_signed_request(request, 'swap')
    assert exc.value.status_code == 400
```

### Integration Tests

- Fresh unlock → swap → pools → send (same TTL)
- Session expiry → next action requires PIN
- Wrong signature → 400 (no 500)
- Missing address → recovery kit required

---

## Risk Mitigation

| Risk | Mitigation | Priority |
|------|-----------|----------|
| Payload format mismatch | Unified build function, extensive tests | High |
| Signature verification false positives | Use standard secp256k1 lib, cross-verify with known test vectors | High |
| Legacy fallback security hole | Explicit "no fallback" rule in code + tests | High |
| Performance degradation | Profiling + optimize verify function if needed | Medium |
| Mobile wallet compat | Test on iOS/Android with recovery kit UX | Medium |

---

## Deployment Checklist

- [ ] Phase 1 PR #615: Swap + pools unification
- [ ] Phase 2 PR #616: Send + tips + L2E unification
- [ ] Phase 3 PR #617: Bridge + NFT + IoT unification
- [ ] Full e2e tests pass
- [ ] Manual QA on staging
- [ ] Deploy to production
- [ ] Monitor: no 500s, no silent fallbacks

---

## Files to Create/Modify

**New Files**:
- `static/wallet_v1_signing_contract.js`
- `static/wallet_v1_event_bus.js`
- `tests/test_wallet_v1_unified_signing.py`

**Modify**:
- `templates/swap.html` (use walletV1BuildSignedRequest)
- `templates/pools.html` (use walletV1BuildSignedRequest)
- `server.py` (consolidate verify functions)
- `static/wallet_session.js` (emit events on state change)

---

**Execution Timeline**: 3-4 weeks (Phases 1-3)  
**Risk Level**: LOW (unified contract is additive, no breaking changes)  
**Go-Live**: When Phase 1 PR #615 merged + tested

