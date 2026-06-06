# Wallet V1 Phase 2: Payment Endpoint Migration Guide

**Phase**: 2 - Critical Payment Path  
**Target Endpoints**: `/send_thr`, `/api/send_token`  
**Effort**: 2-3 days, low risk  
**Status**: Ready to implement

---

## Overview

This guide shows how to migrate additional endpoints to Wallet V1 signed transactions, following the pattern established in Phase 1 (/api/swap/execute).

## Phase 1 Reference Implementation

The swap endpoint (`/api/swap/execute`) is your reference for all migrations. Key pattern:

```python
def api_swap_execute():
    try:
        data = request.get_json() or {}
        # Extract fields from request
        ...
    except Exception as exc:
        return jsonify(status="error", message=str(exc)), 500

    try:
        # WALLET V1 OR LEGACY AUTH
        auth_ok, auth_error, verified_trader = verify_swap_wallet_v1_or_legacy(
            data, 
            SWAP_EXPECTED_ACTION
        )
        
        if not auth_ok:
            # Return 400 with error code
            return jsonify(
                ok=False, 
                status="error", 
                error=auth_error.get("error")
            ), 400
        
        trader = verified_trader
        
        # REST OF ENDPOINT LOGIC
        # (same for both V1 and legacy - no diverging paths)
        ...
        
    except Exception as exc:
        return jsonify(status="error", message=str(exc)), 500
```

---

## Implementation Pattern

### Step 1: Create Verification Function (if needed)

For simple endpoints like `/send_thr` and `/api/send_token`, you can reuse `verify_swap_wallet_v1_or_legacy` or create a similar one:

```python
def verify_send_wallet_v1_or_legacy(payload, expected_action="send"):
    """Verify send auth before any state mutation."""
    # Extract trader from payload
    trader_raw = (payload.get("trader_thr") or payload.get("from") or "").strip()
    signed_tx_raw = payload.get("signed_tx")
    
    if signed_tx_raw:
        # V1 signed transaction path
        signed_tx = signed_tx_raw if isinstance(signed_tx_raw, dict) else {}
        
        if not signed_tx.get("signature"):
            return False, {"error": "missing_signature"}, None
        
        # Verify action type matches expected
        signed_action = signed_tx.get("action") or signed_tx.get("type")
        if signed_action != expected_action:
            return False, {"error": "action_mismatch", "expected": expected_action}, None
        
        # Verify sender matches
        signed_from = signed_tx.get("from", "").strip()
        if not signed_from:
            return False, {"error": "missing_from"}, None
        
        # Normalize and compare
        if trader_raw and trader_raw.upper() != signed_from.upper():
            return False, {"error": "address_mismatch"}, None
        
        trader = signed_from
        
        # Verify signature (mock for now, implement actual verification)
        valid_sig = verify_signed_transaction(signed_tx)  # Function to implement
        if not valid_sig:
            return False, {"error": "invalid_signature"}, None
        
        return True, {}, trader
    
    # Legacy fallback
    if not trader_raw:
        return False, {"error": "missing_trader"}, None
    
    trader = trader_raw
    auth_secret = payload.get("auth_secret", "")
    passphrase = payload.get("passphrase", "")
    
    ok, _, error_key = validate_effective_auth(trader, auth_secret, passphrase)
    if not ok:
        return False, {"error": error_key or "invalid_auth"}, trader
    
    return True, {}, trader
```

### Step 2: Modify Endpoint

For `/api/send_token`:

```python
@app.route("/api/send_token", methods=["POST"])
def api_send_token():
    try:
        data = request.get_json() or {}
        
        # Parse request fields
        token = (data.get("token") or "").upper().strip()
        amount = float(data.get("amount", 0))
        to_addr = (data.get("to") or "").strip()
        
    except (TypeError, ValueError):
        return jsonify(ok=False, status="error", error="invalid_amount"), 400
    except Exception as exc:
        return jsonify(status="error", message=str(exc)), 500
    
    try:
        # Validate inputs
        if not token or amount <= 0:
            return jsonify(ok=False, status="error", error="invalid_token_amount"), 400
        if not to_addr:
            return jsonify(ok=False, status="error", error="missing_recipient"), 400
        
        # WALLET V1 OR LEGACY AUTH
        auth_ok, auth_error, verified_trader = verify_send_wallet_v1_or_legacy(
            data, 
            "send_token"
        )
        
        if not auth_ok:
            error_code = auth_error.get("error", "invalid_auth")
            return jsonify(ok=False, status="error", error=error_code), 400
        
        trader = verified_trader
        
        # REST OF ENDPOINT LOGIC - UNCHANGED
        # Perform token transfer, update balances, etc.
        # (no V1-specific logic needed here)
        ...
        
    except Exception as exc:
        return jsonify(status="error", message=str(exc)), 500
```

---

## Testing Template

For each endpoint migration, create a test file like:

```python
# tests/test_send_token_v1.py
import pytest
from server import verify_send_wallet_v1_or_legacy

class TestSendTokenAuth:
    """Test Wallet V1 auth for /api/send_token."""
    
    def test_valid_signed_send(self):
        """Verify valid signed send is accepted."""
        data = {
            "to": "THR" + "B" * 40,
            "token": "USDC",
            "amount": 100,
            "signed_tx": {
                "from": "THR" + "A" * 40,
                "action": "send_token",
                "to": "THR" + "B" * 40,
                "token": "USDC",
                "amount": 100,
                "signature": "mock_sig",
            }
        }
        
        with unittest.mock.patch('server.verify_signed_transaction', return_value=True):
            auth_ok, error, trader = verify_send_wallet_v1_or_legacy(data, "send_token")
            assert auth_ok
            assert trader == "THR" + "A" * 40
    
    def test_missing_signature_rejected(self):
        """Verify missing signature is rejected."""
        data = {
            "to": "THR" + "B" * 40,
            "token": "USDC",
            "signed_tx": {
                "from": "THR" + "A" * 40,
                "action": "send_token",
                # Missing signature
            }
        }
        
        auth_ok, error, trader = verify_send_wallet_v1_or_legacy(data, "send_token")
        assert not auth_ok
        assert error["error"] == "missing_signature"
    
    def test_legacy_fallback_works(self):
        """Verify legacy auth_secret fallback."""
        data = {
            "trader_thr": "THR" + "A" * 40,
            "auth_secret": "secret123",
            "to": "THR" + "B" * 40,
            "token": "USDC",
            "amount": 100,
        }
        
        with unittest.mock.patch('server.validate_effective_auth', return_value=(True, None, None)):
            auth_ok, error, trader = verify_send_wallet_v1_or_legacy(data, "send_token")
            assert auth_ok
            assert trader == "THR" + "A" * 40
```

---

## Checklist for Phase 2

### Implementation
- [ ] Create `verify_send_wallet_v1_or_legacy()` function
- [ ] Update `/send_thr` endpoint to use new verification
- [ ] Update `/api/send_token` endpoint to use new verification
- [ ] Ensure error codes returned consistently (missing_signature, address_mismatch, etc.)
- [ ] Return 400 for auth errors, not 500

### Testing
- [ ] Valid signed transactions accepted
- [ ] Trader address extracted correctly
- [ ] Missing signatures rejected
- [ ] Address mismatches detected
- [ ] Legacy fallback works
- [ ] Clear error codes returned
- [ ] Malformed requests return 400, not 500

### Integration
- [ ] Works with existing recovery kit flow
- [ ] Session timeout still enforced
- [ ] No changes to consensus/mining logic
- [ ] Backward compatible with legacy clients

### Documentation
- [ ] Update endpoint docs
- [ ] Add examples for signed requests
- [ ] Document error codes
- [ ] Create migration note in changelog

---

## Common Pitfalls to Avoid

1. **Diverging Code Paths**: Don't have different logic for V1 vs legacy. Extract once, use same path.
2. **Returning 500 for User Errors**: Invalid amounts, missing fields → 400, not 500.
3. **Silent Fallback**: Don't fall back to legacy if V1 auth was attempted. Show error instead.
4. **Signature Validation Skipped**: Always verify signatures, don't trust client-side checks.
5. **No Error Codes**: Return specific error codes (missing_signature, address_mismatch, etc.)

---

## Performance Considerations

- Signature verification is CPU-intensive (ECDSA)
- Cache signature verification results? NO - verify every time
- Don't parallelize signature checks across unrelated requests
- Mining endpoints: optional auth (don't require signatures for speed)

---

## Rollback Plan

If Phase 2 causes issues:

1. The endpoints still have `auth_secret` fallback
2. Just remove the V1 verification block, keep legacy path
3. No data loss - signatures are in signed_tx field, easily removed
4. Can redeploy legacy version in <5 min

---

## Resources

- **Reference Implementation**: /api/swap/execute in server.py
- **Test Patterns**: tests/test_wallet_v1_migration.py
- **Schema**: WALLET_V1_CHAIN_AUTH_STANDARD.md
- **Architecture**: NATIVE_WALLET_SPEC.md

---

**Ready to Start**: Yes ✅  
**Difficulty**: Low  
**Risk**: Low  
**Effort**: 2-3 days  

Good luck with Phase 2!
