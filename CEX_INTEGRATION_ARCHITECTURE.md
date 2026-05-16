# CEX Integration Architecture for Pledge & Bridge Systems
**Critical Issue:** MEXC/Binance/Kraken deposit vs. withdrawal address mismatch

---

## THE PROBLEM

### Current Broken Flow:
```
MEXC Deposit (Unique per user):
  User A → MEXC_DEPOSIT_ADDRESS_A → Thronos Vault ✅ (Works - unique address)

MEXC Withdrawal (Shared Hot Wallet):
  User A → MEXC_HOT_WALLET_SHARED ← User B, User C, User D
              ↓
              Thronos Vault ❌ (Breaks - can't identify who sent)
```

### Impact:
- **Pledge System:** Can't verify "who" pledged because Hot Wallet is shared
- **Bridge System:** Can't track who initiated BTC→THR conversion
- **KYC/AML:** Violation - can't verify fund source matches identity
- **Security:** Attackers could spoof deposits via CEX

---

## SOLUTION ARCHITECTURE

### OPTION 1: FORCE PERSONAL WALLET (RECOMMENDED FOR PHASE 1) ✅

**Requirement:** Users must NOT send directly from CEX

**Implementation:**
```python
# File: pledge_submit.py
def validate_pledge_source(btc_address: str) -> bool:
    """
    Validate that pledge comes from personal wallet, not CEX
    """
    # Known CEX hot wallets (blocklist)
    CEX_HOTWALLETS = {
        "3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy",  # MEXC Hot Wallet (example)
        "1Feex....",  # Binance Hot Wallet (example)
        # ... maintain list
    }
    
    if btc_address in CEX_HOTWALLETS:
        return False, "Direct CEX pledges not allowed. Withdraw to personal wallet first."
    
    return True, "OK"
```

**UI Warning:**
```
⚠️ IMPORTANT: Do NOT send pledge from MEXC/Binance/Kraken directly
1. Withdraw BTC to personal wallet (MetaMask, Rabby, Ledger, etc.)
2. Wait for confirmation
3. Send from personal wallet to Thronos Vault
4. Submit pledge with your personal wallet address

Why? For KYC/AML compliance and security.
```

---

### OPTION 2: UNIQUE DEPOSIT ADDRESSES PER USER (PHASE 3)

**Advanced:** Each user gets temporary unique deposit address

**Architecture:**
```
User submits pledge request
    ↓
System generates: UNIQUE_DEPOSIT_ADDRESS_{USER_ID}_{TIMESTAMP}
    ↓
User sends BTC → UNIQUE_DEPOSIT_ADDRESS
    ↓
Watch for incoming transaction
    ↓
Confirm received → Map to user → Create pledge
    ↓
Smart contract auto-processes
```

**Implementation:**
```python
# File: pledge_address_generator.py (NEW)
def generate_unique_deposit_address(user_id: str, session_id: str) -> str:
    """
    Generate unique temporary deposit address for this pledge session
    
    Uses BIP32 HD wallet derivation:
    m/44'/0'/0'/{user_id}/{session_id}
    """
    # Derive from master key
    child_key = master_key.derive_child(user_id).derive_child(session_id)
    address = child_key.address()
    
    # Store mapping
    store_deposit_mapping({
        "address": address,
        "user_id": user_id,
        "session_id": session_id,
        "created_at": now(),
        "expires_at": now() + 24h  # 24 hour window
    })
    
    return address

# Watch for deposits to unique addresses
def watch_unique_deposits():
    """Run every 5 minutes - check for deposits to any unique address"""
    for mapping in get_active_deposit_mappings():
        txns = get_btc_txns(mapping['address'])
        for tx in txns:
            if tx.is_confirmed():
                user = get_user(mapping['user_id'])
                create_pledge_auto(user, tx.amount)
                mark_mapping_used(mapping['address'])
```

---

### OPTION 3: SIGNATURE/PAYLOAD VERIFICATION (PHASE 4)

**Most Secure:** User signs transaction with their identity

**How it works:**
```
1. User initiates pledge request
2. System generates: PAYLOAD = SHA256(user_id + amount + nonce + timestamp)
3. User must include PAYLOAD in transaction memo/data field
4. System verifies: "Only person with user_id could have created this payload"
5. CEX sender doesn't matter - payload proves identity

For XRP/Stellar/Cosmos (memo-enabled):
  MEMO = PAYLOAD + KYC_ID_HASH
  
For BTC (OP_RETURN):
  OP_RETURN data = PAYLOAD
```

---

## PHASED ROLLOUT

| Phase | Timeline | Approach | Status |
|-------|----------|----------|--------|
| 1 | Now - May 31 | Option 1: Force personal wallet | 🔨 IMPLEMENT NOW |
| 2 | June 1-15 | Option 2: Unique deposit addresses | ⏳ QUEUE |
| 3 | June 15-30 | Option 3: Signature verification | 📋 PLAN |
| 4 | July+ | Full CEX integration API | 🚀 FUTURE |

---

## IMPLEMENTATION FOR PHASE 1 (DO NOW)

### Files to Create:

**1. cex_validator.py** (NEW - 150 lines)
```python
"""
CEX Deposit Validator
Prevents direct CEX deposits, enforces personal wallet requirement
"""

class CEXValidator:
    # Known CEX hot wallet addresses (maintained list)
    KNOWN_CEX_WALLETS = {
        # MEXC
        "3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy": "MEXC Hot Wallet",
        # Binance
        "1Feex...": "Binance Hot Wallet",
        # Kraken
        "1KYiKJfHx...": "Kraken Hot Wallet",
    }
    
    def is_cex_address(self, btc_address: str) -> bool:
        """Check if address is known CEX hot wallet"""
        return btc_address in self.KNOWN_CEX_WALLETS
    
    def validate_pledge_source(self, btc_address: str, pledge_data: dict) -> tuple:
        """
        Validate that pledge comes from personal wallet
        
        Returns: (is_valid: bool, message: str)
        """
        if self.is_cex_address(btc_address):
            return False, (
                "❌ Direct CEX pledges not allowed for security & KYC compliance. "
                "Please withdraw to personal wallet (MetaMask, Ledger, etc.) first."
            )
        
        # Additional checks
        if not self._is_legitimate_address(btc_address):
            return False, "❌ Invalid address format"
        
        return True, "✅ Address validated"
```

**2. Update pledge_submit.py**
```python
# Add CEX validation before processing
from cex_validator import CEXValidator

validator = CEXValidator()
is_valid, msg = validator.validate_pledge_source(btc_address)

if not is_valid:
    return jsonify(
        status="rejected",
        reason="cex_direct_not_allowed",
        message=msg,
        suggestion="Withdraw to personal wallet and retry"
    ), 403
```

**3. Update pledge.html UI**
```html
<div class="warning-banner" style="background: #ff6b6b; padding: 15px; margin: 10px 0;">
  <h3>⚠️ IMPORTANT: Do NOT Use Exchange</h3>
  <p>Direct pledges from MEXC/Binance/Kraken are NOT allowed.</p>
  <ol>
    <li>Login to MEXC/Binance</li>
    <li>Click "Withdraw" or "Send"</li>
    <li>Send BTC to your personal wallet address</li>
    <li>Wait for confirmation (5-30 min)</li>
    <li>From personal wallet, complete this pledge</li>
  </ol>
  <p><strong>Why?</strong> Exchanges use shared accounts. We can't verify KYC that way.</p>
</div>
```

---

## BRIDGE SYSTEM CHANGES (Phase 2)

Same validation for bridge transactions:

```python
# File: bridge_coordinator.py
from cex_validator import CEXValidator

def initiate_bridge(btc_source_address: str, amount: float):
    """BTC → THR bridge"""
    validator = CEXValidator()
    is_valid, msg = validator.validate_pledge_source(btc_source_address)
    
    if not is_valid:
        return error_response(403, msg)
    
    # Proceed with bridge
    ...
```

---

## FUTURE: FULL CEX API INTEGRATION (Phase 4)

```
Thronos ←→ MEXC API
         ↓
Queries: "User@thronos.org has KYC?"
        "User@thronos.org withdrew $X on date Y?"
         ↓
MEXC confirms: "Yes, verified user"
         ↓
Thronos auto-processes pledge
```

This requires:
- MEXC API partnership/credentials
- Stellar Federation (user@thronos.org addresses)
- Webhook callbacks from MEXC

---

## CHECKLIST FOR PHASE 1

- [ ] Create cex_validator.py
- [ ] Update pledge_submit.py with validation
- [ ] Update pledge.html with warning banner
- [ ] Add CEX wallet addresses to blocklist (maintain list)
- [ ] Test with MEXC/Binance test wallets
- [ ] Update API documentation (warn against CEX)
- [ ] Email all users: "Do NOT use CEX directly"
- [ ] Monitor for violations, update blocklist

---

## TESTING

```python
# test_cex_validation.py
def test_cex_wallet_rejection():
    """CEX wallets should be rejected"""
    validator = CEXValidator()
    
    # MEXC hot wallet should fail
    result, msg = validator.validate_pledge_source("3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy")
    assert result == False
    assert "CEX" in msg
    
    # Personal wallet should pass
    result, msg = validator.validate_pledge_source("1A1z7agoat91d7c4b5d5c2c7f1h6b1k8m2")
    assert result == True
```

---

## SUMMARY

| Aspect | Solution |
|--------|----------|
| **Phase 1** | Block known CEX wallets + UI warning |
| **Phase 2** | Unique temporary deposit addresses |
| **Phase 3** | Signature/payload verification |
| **Phase 4** | Direct CEX API integration |
| **Security** | Prevents spoofing, ensures KYC/AML |
| **UX** | Clear instructions, warnings |

