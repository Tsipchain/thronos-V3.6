# Wallet V1 Passkey/WebAuthn Roadmap

## Vision

Enable biometric (fingerprint, FaceID) and passkey-based wallet unlocking on mobile, while maintaining PIN as web fallback.

## Phase 1: Foundation (Mobile UX) - Q3 2026

### 1.1 WebAuthn Integration

**Library**: `@simplewebauthn/browser` + `@simplewebauthn/server`

**Backend Registration** (`server.py`):
```python
@app.route('/api/wallet/v1/webauthn/register/begin', methods=['POST'])
def webauthn_register_begin():
    """
    Start passkey registration for wallet V1.
    Client: canonical address, user_name (from pledge)
    Server: generate attestation challenge, store in session
    """
    address = request.json.get('canonical_v1_address')
    user_id = hashlib.sha256(address.encode()).hexdigest()[:32]
    
    challenge = os.urandom(32)
    session['webauthn_challenge'] = challenge
    session['webauthn_address'] = address
    
    return jsonify({
        ok: True,
        rp: {'name': 'Tsipchain', 'id': 'tsipchain.com'},
        user: {
            id: user_id,
            name: address,
            displayName: address[:10] + '...'
        },
        challenge: challenge.hex(),
        timeout: 60000,
        attestation: 'direct'
    })

@app.route('/api/wallet/v1/webauthn/register/complete', methods=['POST'])
def webauthn_register_complete():
    """
    Complete passkey registration.
    Client: attestationObject, clientDataJSON
    Server: verify, store credential public key
    """
    credential = request.json.get('credential')
    address = session.get('webauthn_address')
    
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=session['webauthn_challenge'],
            expected_rp_id='tsipchain.com',
            expected_origin='https://tsipchain.com'
        )
        
        # Store credential public key
        store_webauthn_credential(
            address=address,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=0
        )
        
        return jsonify(ok=True, message='Passkey registered')
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
```

### 1.2 Frontend Unlock Flow (Mobile)

**New File**: `static/wallet_v1_passkey_unlock.js`

```javascript
/**
 * Mobile-first passkey unlock
 * Tries: Passkey → Fallback to PIN
 */
async function unlockWalletWithPasskey() {
    const addr = walletSession.getAddress();
    if (!addr) {
        showError('No canonical address');
        return;
    }
    
    try {
        // Step 1: Get challenge from server
        const challengeResp = await fetch('/api/wallet/v1/webauthn/auth/begin', {
            method: 'POST',
            body: JSON.stringify({canonical_v1_address: addr})
        });
        const challenge = await challengeResp.json();
        
        // Step 2: Request assertion from authenticator (fingerprint/FaceID)
        const assertion = await navigator.credentials.get({
            publicKey: {
                challenge: Uint8Array.from(challenge.challenge, c => c.charCodeAt(0)),
                timeout: 60000,
                rpId: 'tsipchain.com',
                userVerification: 'preferred'
            }
        });
        
        if (!assertion) {
            throw new Error('User cancelled or not available');
        }
        
        // Step 3: Send assertion to server
        const verifyResp = await fetch('/api/wallet/v1/webauthn/auth/complete', {
            method: 'POST',
            body: JSON.stringify({
                canonical_v1_address: addr,
                assertionObject: assertion
            })
        });
        
        const result = await verifyResp.json();
        if (result.ok) {
            // Passkey unlock successful
            walletSession.setBound(true);
            walletSession.setPasskeyUsed(true);
            window.walletV1Events.emit('wallet:unlocked', {address: addr, method: 'passkey'});
            showSuccess('Unlocked with passkey');
            // Session TTL still applies (15 min same as PIN)
        } else {
            throw new Error(result.error);
        }
    } catch (err) {
        console.warn('Passkey unlock failed, falling back to PIN:', err.message);
        // Fallback to PIN
        promptPinUnlock();
    }
}
```

### 1.3 Session TTL Policy (Mobile)

**Current**: 15 min for PIN unlock

**Proposed**: 
- **Passkey unlock**: 30 min (higher trust: biometric bound to device)
- **PIN unlock**: 15 min (lower trust: PIN can be shared)
- **High-risk actions** (bridge deposit > $1000): Require re-auth regardless of TTL

```javascript
// wallet_session.js
const SESSION_TTL = {
    PIN: 15 * 60 * 1000,        // 15 min
    PASSKEY: 30 * 60 * 1000,    // 30 min
    WEBAUTHN_TOUCHED: 5 * 60 * 1000  // 5 min (just proved identity)
};

function getSessionTTL() {
    const unlockMethod = walletSession.getUnlockMethod?.();
    return SESSION_TTL[unlockMethod] || SESSION_TTL.PIN;
}
```

---

## Phase 2: Risk-Based Re-Auth (Q4 2026)

### 2.1 High-Risk Action Detection

```javascript
function isHighRiskAction(action, payload) {
    // Bridge deposits > $1000
    if (action === 'bridge_deposit' && payload.amount > 1000) {
        return true;
    }
    
    // NFT bulk buy > 10 items
    if (action === 'nft_bulk_buy' && payload.items.length > 10) {
        return true;
    }
    
    // L2E early unstake
    if (action === 'l2e_unstake_early') {
        return true;
    }
    
    return false;
}

async function performActionWithReAuth(action, payload) {
    if (isHighRiskAction(action, payload)) {
        const sessionAge = Date.now() - walletSession.getUnlockedAt?.();
        const minAge = 5 * 60 * 1000;  // 5 min minimum freshness
        
        if (sessionAge > minAge) {
            // Require re-auth (either passkey or PIN)
            const unlocked = await promptReAuth();
            if (!unlocked) return;  // User cancelled
        }
    }
    
    // Proceed with action
    return walletV1BuildSignedRequest(action, payload);
}
```

### 2.2 Re-Auth UI

**Mobile**: "Touch fingerprint to confirm [bridge deposit of $1500]"  
**Web**: "Enter PIN to confirm"

---

## Phase 3: Cross-Device Recovery (2027+)

### 3.1 Problem

User installs app on new phone: Passkeys are device-bound, can't transfer.

### 3.2 Solution: Recovery Kit + Passkey Binding

When user registers passkey:
```
1. Store encrypted passkey backup in Recovery Kit
2. If new device: Import Recovery Kit → unlock with PIN → re-register passkey
3. Old device: Optionally revoke old passkey to prevent multi-device attacks
```

**Not implemented yet**, but architecture supports it.

---

## UX Wireframes

### Unlock Screen (Mobile)

```
╔════════════════════════════╗
║  Unlock Wallet V1          ║
╠════════════════════════════╣
║                            ║
║   [Unlock with Passkey]   ║ ← Primary (if registered)
║   or                       ║
║   [Unlock with PIN]        ║ ← Fallback
║                            ║
║   [Don't have passkey?]    ║ ← Link to register
║                            ║
╚════════════════════════════╝
```

### Passkey Registration

```
╔════════════════════════════╗
║  Register Fingerprint      ║
╠════════════════════════════╣
║                            ║
║  📱 Place your finger on   ║
║      the scanner           ║
║                            ║
║  [Cancel] [Already done]   ║
║                            ║
╚════════════════════════════╝
```

---

## Implementation Checklist

### Phase 1 (Q3 2026)

- [ ] Add `@simplewebauthn` dependencies
- [ ] Implement registration endpoints (begin/complete)
- [ ] Implement authentication endpoints (begin/complete)
- [ ] Frontend: Passkey unlock UI
- [ ] Fallback to PIN if passkey unavailable
- [ ] Tests: Registration, auth, fallback flows
- [ ] Mobile: Test on iOS (WebAuthn via Touch ID) and Android (Biometric)
- [ ] Session TTL: Passkey gets 30 min vs PIN 15 min

### Phase 2 (Q4 2026)

- [ ] High-risk action detection
- [ ] Re-auth UI for high-risk actions
- [ ] Tests: High-risk re-auth flows
- [ ] Logging: Track unlock method for audit

### Phase 3 (2027+)

- [ ] Recovery Kit passkey backup encryption
- [ ] Multi-device passkey revocation
- [ ] Cross-device unlock flow

---

## Risks & Mitigations

| Risk | Mitigation | Priority |
|------|-----------|----------|
| User loses biometric (e.g., phone reset) | Recovery Kit as fallback | High |
| Passkey theft (stolen phone) | Device-level encryption (OS handles) | High |
| Attestation spoofing | Use server-side attestation verification | High |
| Mobile platform fragmentation | Test on iOS/Android, fallback to PIN | Medium |
| UX confusion (which unlock method) | Clear labeling + tooltips | Low |

---

## Browser/Platform Support

| Platform | WebAuthn | Status | Notes |
|----------|----------|--------|-------|
| iOS 13.3+ | ✅ | Supported | Touch ID, Face ID |
| Android 7+ | ✅ | Supported | Biometric API |
| Chrome/Edge | ✅ | Supported | Desktop passkey sync (future) |
| Safari | ✅ | Supported | iOS/macOS |
| Firefox | ✅ | Supported | Desktop only |

---

## Performance Impact

- **Registration**: ~2-3 seconds (one-time)
- **Unlock**: ~1-2 seconds (user touches biometric)
- **Fallback to PIN**: < 100ms

---

**Timeline**: 9 months (Phases 1-3)  
**Risk Level**: MEDIUM (new dependency, requires careful attestation verification)  
**MVP (Phase 1)**: Go-live Q3 2026

