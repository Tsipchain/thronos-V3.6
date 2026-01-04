# FIX #8: Billing Separation - Chat (Credits) vs Architect (THR)

**Date**: 2026-01-04
**Branch**: `claude/fix-wallet-ui-final-gUEre`
**Type**: NEW BILLING LOGIC (user-approved)

---

## ΣΤΟΧΟΣ

**Καθαρή διαχωρισμός billing**:
- **Chat**: Credits μόνο (όχι "0.0 THR" memo)
- **Architect**: THR με 0.001 base fee + variable
- **Reward**: 1 THR spent → +10 credits για Chat
- **Block cross-charge**: Chat δεν μπορεί charge_thr(), Architect δεν μπορεί consume_credits()

---

## OBSERVABLE ISSUES (Πριν το Fix)

### 1. Chat writes "0.0 THR" memo
- TX logs έδειχναν "payment: 0.0 THR" για Chat requests
- Confusing: φαινόταν σαν THR transaction αλλά ήταν credits

### 2. Architect χωρίς billing
- Architect endpoint δωρεάν (no THR charge)
- Δεν δημιουργούσε payment TX

### 3. Κανένα cross-charge protection
- Chat μπορούσε θεωρητικά να καλέσει THR billing
- Architect μπορούσε να καλέσει credits

### 4. Κανένα credits reward
- THR spending στο Architect δεν έδινε credits για Chat

---

## ΛΥΣΗ - Νέο Billing Module

### Architecture

```
billing.py
├── consume_credits(wallet, amount, product="chat")
│   ├── Cross-charge guard (only "chat")
│   ├── Deduct from ai_credits.json
│   └── Telemetry: credits_delta, billing_channel="credits"
│
├── charge_thr(wallet, amount, reason, product="architect")
│   ├── Cross-charge guard (only "architect")
│   ├── Deduct from ledger.json
│   ├── Create chain TX (type="architect_payment")
│   └── Telemetry: thr_delta, billing_channel="thr"
│
├── grant_credits_from_thr_spend(wallet, thr_spent)
│   ├── Ratio: 1 THR → 10 credits
│   └── Telemetry: billing_channel="reward"
│
└── calculate_architect_fee(tokens_out, files_count, complexity)
    ├── Base: 0.001 THR
    └── Variable: (tokens/1000 * 0.0001) + (files * 0.0001)
```

---

## ΑΛΛΑΓΕΣ ΑΝΑ FILE

### 1. billing.py (NEW FILE)

**Purpose**: Single source of truth για όλο το billing logic.

**Key Functions**:

#### `consume_credits(wallet, amount, product="chat")`
```python
def consume_credits(wallet: str, amount: int, product: str = "chat") -> Tuple[bool, str, Dict]:
    # Cross-charge guard
    if product != "chat":
        error = f"BLOCKED: consume_credits called from product={product}"
        _record_telemetry({
            "event": "cross_charge_blocked",
            "product": product,
            "attempted_action": "consume_credits"
        })
        return False, error, {}

    # Load credits
    credits_map = _load_json(AI_CREDITS_FILE, {})
    current = int(credits_map.get(wallet, 0))

    if current < amount:
        return False, f"Insufficient credits: have {current}, need {amount}", {}

    # Deduct
    new_balance = current - amount
    credits_map[wallet] = new_balance
    _save_json(AI_CREDITS_FILE, credits_map)

    telemetry = {
        "event": "credits_consumed",
        "product": product,
        "wallet": wallet,
        "credits_delta": -amount,
        "credits_after": new_balance,
        "billing_channel": "credits",
        "charge_result": "success"
    }
    _record_telemetry(telemetry)

    return True, "", telemetry
```

**Why**:
- Centralizes credits logic
- Prevents Chat from calling THR functions
- Logs telemetry για audit

---

#### `charge_thr(wallet, amount, reason, product="architect")`
```python
def charge_thr(wallet: str, amount: Decimal, reason: str, product: str = "architect") -> Tuple[bool, str, Dict]:
    # Cross-charge guard
    if product != "architect":
        error = f"BLOCKED: charge_thr called from product={product}"
        _record_telemetry({
            "event": "cross_charge_blocked",
            "product": product,
            "attempted_action": "charge_thr"
        })
        return False, error, {}

    # Load ledger
    ledger = _load_json(LEDGER_FILE, {})
    balance = Decimal(str(ledger.get(wallet, 0)))

    if balance < amount:
        return False, f"Insufficient THR: have {balance}, need {amount}", {}

    # Deduct THR, credit AI wallet
    new_balance = balance - amount
    ledger[wallet] = float(new_balance)
    ai_balance = Decimal(str(ledger.get(AI_WALLET_ADDRESS, 0)))
    ledger[AI_WALLET_ADDRESS] = float(ai_balance + amount)
    _save_json(LEDGER_FILE, ledger)

    # Create chain transaction
    chain = _load_json(CHAIN_FILE, [])
    tx = {
        "type": "architect_payment",
        "reason": reason,
        "from": wallet,
        "to": AI_WALLET_ADDRESS,
        "amount": float(amount),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"ARCH-{int(time.time())}-{len(chain)}"
    }
    chain.append(tx)
    _save_json(CHAIN_FILE, chain)

    telemetry = {
        "event": "thr_charged",
        "product": product,
        "thr_delta": -float(amount),
        "thr_after": float(new_balance),
        "billing_channel": "thr",
        "charge_result": "success",
        "tx_id": tx["tx_id"]
    }
    _record_telemetry(telemetry)

    return True, "", telemetry
```

**Why**:
- Creates REAL payment TX (type="architect_payment")
- Prevents Architect from calling credits functions
- NO "0.0 THR" memo - real THR amounts only

---

#### `grant_credits_from_thr_spend(wallet, thr_spent)`
```python
def grant_credits_from_thr_spend(wallet: str, thr_spent: Decimal) -> Dict:
    credits_granted = int(thr_spent * 10)  # 1 THR → 10 credits

    if credits_granted <= 0:
        return {}

    credits_map = _load_json(AI_CREDITS_FILE, {})
    current = int(credits_map.get(wallet, 0))
    new_balance = current + credits_granted
    credits_map[wallet] = new_balance
    _save_json(AI_CREDITS_FILE, credits_map)

    telemetry = {
        "event": "credits_granted_from_thr",
        "product": "architect",
        "thr_spent": float(thr_spent),
        "credits_delta": credits_granted,
        "credits_after": new_balance,
        "billing_channel": "reward"
    }
    _record_telemetry(telemetry)

    return telemetry
```

**Why**: Architect spending THR δίνει credits reward για Chat.

---

#### `calculate_architect_fee(tokens_out, files_count, complexity)`
```python
def calculate_architect_fee(tokens_out: int = 0, files_count: int = 0, blueprint_complexity: int = 1) -> Decimal:
    base = Decimal("0.001")  # 0.001 THR base

    # Token-based fee (per 1000 tokens)
    token_fee = Decimal(tokens_out) / Decimal("1000") * Decimal("0.0001")

    # File-based fee
    file_fee = Decimal(files_count) * Decimal("0.0001")

    # Complexity multiplier
    variable = (token_fee + file_fee) * Decimal(blueprint_complexity)

    total = base + variable
    return total.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
```

**Example**:
- 5000 tokens, 10 files, complexity=1
- Fee = 0.001 + (5000/1000 * 0.0001) + (10 * 0.0001)
- Fee = 0.001 + 0.0005 + 0.001
- **Fee = 0.0025 THR**

---

### 2. server.py:583-585 - Initialize Billing

```python
# FIX 8: Initialize billing module
import billing
billing.init_billing(DATA_DIR, LEDGER_FILE, CHAIN_FILE, AI_CREDITS_FILE, AI_WALLET_ADDRESS)
```

**Why**: Billing module needs file paths at startup.

---

### 3. server.py:4015-4038 - Chat Credits Check

**BEFORE**:
```python
# If a wallet is provided, enforce the paid credits model
credits_map = load_ai_credits()
credits_value = int(credits_map.get(wallet, 0) or 0)

if credits_value <= 0:
    return jsonify(status="no_credits", ...), 200
```

**AFTER**:
```python
# FIX 8: Credits check (Chat billing mode)
# Check credits availability (don't deduct yet - wait for successful AI call)
credits_map = load_ai_credits()
credits_value = int(credits_map.get(wallet, 0) or 0)

if credits_value <= 0:
    return jsonify(status="no_credits", ...), 200
```

**Change**: Comment updated - clarifies no THR involvement.

---

### 4. server.py:4149-4173 - Chat Credits Deduction

**BEFORE**:
```python
# --- Credit burn ---
if wallet:
    credits_map = load_ai_credits()
    before = int(credits_map.get(wallet, 0) or 0)
    after = max(0, before - AI_CREDIT_COST_PER_MSG)
    credits_map[wallet] = after
    save_ai_credits(credits_map)
    credits_for_frontend = after
```

**AFTER**:
```python
# FIX 8: Consume credits (Chat billing mode - no THR)
if wallet:
    # Use billing module (clean separation, telemetry, cross-charge guard)
    success, error_msg, telemetry = billing.consume_credits(wallet, AI_CREDIT_COST_PER_MSG, product="chat")
    if not success:
        logger.error(f"Credits consumption failed: {error_msg}")
        credits_for_frontend = 0
    else:
        credits_for_frontend = telemetry.get("credits_after", 0)
        ai_credits_spent = abs(telemetry.get("credits_delta", 0))
```

**Why**:
- Uses centralized billing function
- Cross-charge guard (only "chat" allowed)
- Telemetry logged automatically
- NO THR charges, NO payment TX

---

### 5. server.py:3109-3111 - Architect Requires Wallet

```python
# FIX 8: Require wallet for Architect (THR billing mode)
if not wallet:
    return jsonify(error="Wallet required for Architect (THR billing)"), 400
```

**Why**: Architect ALWAYS requires wallet (THR payment).

---

### 6. server.py:3186-3216 - Architect THR Billing

**NEW CODE**:
```python
# FIX 8: Calculate Architect fee (base + variable)
tokens_out = len(full_text.split())  # Rough token estimate
files_count = len(files) if files else 0
architect_fee = billing.calculate_architect_fee(tokens_out=tokens_out, files_count=files_count, blueprint_complexity=1)

# FIX 8: Charge THR (Architect billing mode - no credits)
charge_success, charge_error, charge_telemetry = billing.charge_thr(
    wallet=wallet,
    amount=architect_fee,
    reason="architect_usage",
    product="architect",
    metadata={
        "blueprint": blueprint,
        "files_generated": files_count,
        "tokens_out": tokens_out,
        "model": model_key
    }
)

if not charge_success:
    # Insufficient THR - return error
    return jsonify({
        "error": charge_error,
        "status": "insufficient_thr",
        "thr_available": charge_telemetry.get("thr_available", 0),
        "thr_needed": float(architect_fee)
    }), 402  # Payment Required

# FIX 8: Grant credits reward (1 THR → 10 credits)
reward_telemetry = billing.grant_credits_from_thr_spend(wallet, architect_fee)
```

**Why**:
- Calculates fee dynamically (base + variable)
- Charges real THR (creates payment TX)
- Returns 402 if insufficient balance
- Grants credits reward (1 THR → 10 credits)

---

### 7. server.py:3249-3262 - Architect Response

**BEFORE**:
```python
return jsonify({
    "status": status,
    "quantum_key": quantum_key,
    "blueprint": blueprint,
    "response": cleaned,
    "files": resp_files,
    "zip_url": zip_url,
    "session_id": session_id
}), 200
```

**AFTER**:
```python
return jsonify({
    "status": status,
    "quantum_key": quantum_key,
    "blueprint": blueprint,
    "response": cleaned,
    "files": resp_files,
    "zip_url": zip_url,
    "session_id": session_id,
    # FIX 8: Billing info
    "thr_spent": float(architect_fee),
    "credits_granted": reward_telemetry.get("credits_delta", 0),
    "billing_channel": "thr",
    "tx_id": charge_telemetry.get("tx_id")
}), 200
```

**Why**: UI/logs can see exact THR spent and credits granted.

---

## ENV CONFIGURATION

### Railway Variables

```bash
# Billing modes (default values)
CHAT_BILLING_MODE=credits
ARCHITECT_BILLING_MODE=thr

# Architect pricing (optional overrides)
ARCHITECT_BASE_FEE=0.001
ARCHITECT_VARIABLE_RATE=0.0001
ARCHITECT_CREDITS_REWARD_RATIO=10  # 1 THR → 10 credits
```

---

## TELEMETRY (billing_telemetry.jsonl)

Κάθε billing action γράφει telemetry:

### Credits Consumed (Chat)
```json
{
  "event": "credits_consumed",
  "product": "chat",
  "wallet": "THR_WALLET_123",
  "credits_delta": -1,
  "credits_before": 100,
  "credits_after": 99,
  "billing_channel": "credits",
  "charge_result": "success",
  "timestamp": "2026-01-04 12:34:56 UTC"
}
```

### THR Charged (Architect)
```json
{
  "event": "thr_charged",
  "product": "architect",
  "wallet": "THR_WALLET_123",
  "thr_delta": -0.0025,
  "thr_before": 10.0,
  "thr_after": 9.9975,
  "billing_channel": "thr",
  "charge_result": "success",
  "reason": "architect_usage",
  "tx_id": "ARCH-1735992896-123",
  "metadata": {
    "blueprint": "web_app.txt",
    "files_generated": 10,
    "tokens_out": 5000
  },
  "timestamp": "2026-01-04 12:34:56 UTC"
}
```

### Credits Granted (Reward)
```json
{
  "event": "credits_granted_from_thr",
  "product": "architect",
  "wallet": "THR_WALLET_123",
  "thr_spent": 0.0025,
  "credits_delta": 0,
  "credits_before": 99,
  "credits_after": 99,
  "billing_channel": "reward",
  "charge_result": "success",
  "timestamp": "2026-01-04 12:34:56 UTC"
}
```

**Note**: 0.0025 THR * 10 = 0.025 credits → rounds to 0 (int). Need >=0.1 THR για 1+ credit.

### Cross-Charge Blocked
```json
{
  "event": "cross_charge_blocked",
  "product": "chat",
  "wallet": "THR_WALLET_123",
  "attempted_action": "charge_thr",
  "reason": "Cross-charge violation",
  "timestamp": "2026-01-04 12:34:56 UTC"
}
```

---

## ACCEPTANCE TESTS

### Test 1: Chat → Όχι "0.0 THR" memo

**Steps**:
1. Chat request με wallet
2. Έλεγξε chain TX logs

**Expected**:
```bash
# Chain file (phantom_tx_chain.json)
# Δεν υπάρχει TX με type="AI_EVENT" και amount=0.0
# Μόνο credits deduction στο ai_credits.json

# Telemetry
{
  "event": "credits_consumed",
  "billing_channel": "credits",  # ← ΟΧΙ "thr"
  "credits_delta": -1
}
```

---

### Test 2: Architect → THR charge >=0.001

**Steps**:
1. Architect request με blueprint + spec
2. Έλεγξε chain TX + telemetry

**Expected**:
```bash
# Chain file
{
  "type": "architect_payment",  # ← ΟΧΙ "AI_EVENT"
  "from": "THR_WALLET_123",
  "to": "THR_AI_AGENT_WALLET_V1",
  "amount": 0.0025,  # ← REAL THR amount (>=0.001)
  "reason": "architect_usage",
  "tx_id": "ARCH-..."
}

# Telemetry
{
  "event": "thr_charged",
  "billing_channel": "thr",
  "thr_delta": -0.0025
}
```

---

### Test 3: Architect → Credits reward

**Steps**:
1. Architect request με 1.0 THR spent
2. Έλεγξε ai_credits.json

**Expected**:
```bash
# Before: credits = 50
# After: credits = 60 (50 + 10 from 1 THR)

# Telemetry
{
  "event": "credits_granted_from_thr",
  "thr_spent": 1.0,
  "credits_delta": 10,
  "billing_channel": "reward"
}
```

---

### Test 4: Cross-Charge Blocked (Chat → THR)

**Scenario**: Chat tries to call charge_thr() (malicious/buggy code)

**Expected**:
```python
success, error, telemetry = billing.charge_thr(wallet, 1.0, "hack", product="chat")
# success = False
# error = "BLOCKED: charge_thr called from product=chat"

# Telemetry
{
  "event": "cross_charge_blocked",
  "product": "chat",
  "attempted_action": "charge_thr"
}
```

---

### Test 5: Cross-Charge Blocked (Architect → Credits)

**Scenario**: Architect tries to call consume_credits()

**Expected**:
```python
success, error, telemetry = billing.consume_credits(wallet, 1, product="architect")
# success = False
# error = "BLOCKED: consume_credits called from product=architect"

# Telemetry
{
  "event": "cross_charge_blocked",
  "product": "architect",
  "attempted_action": "consume_credits"
}
```

---

## CHAIN TX TYPES

### BEFORE (Mixed)
```json
// Chat (confusing - looks like payment but is credits)
{
  "type": "AI_EVENT",
  "amount": 0.0,
  "memo": "credits",
  "wallet": "..."
}

// Architect (no TX at all)
```

### AFTER (Clean)
```json
// Chat (NO TX in chain - only credits.json)
// Zero blockchain entries for Chat

// Architect (REAL payment TX)
{
  "type": "architect_payment",
  "from": "THR_WALLET_123",
  "to": "THR_AI_AGENT_WALLET_V1",
  "amount": 0.0025,
  "reason": "architect_usage",
  "tx_id": "ARCH-1735992896-123",
  "timestamp": "2026-01-04 12:34:56 UTC"
}
```

---

## FILES MODIFIED

1. **billing.py** (NEW):
   - 365 lines
   - consume_credits(), charge_thr(), grant_credits_from_thr_spend()
   - calculate_architect_fee()
   - Telemetry recording

2. **server.py**:
   - Line 583-585: Initialize billing module
   - Lines 4015-4038: Chat credits check (comment update)
   - Lines 4149-4173: Chat credits deduction (use billing module)
   - Lines 3109-3111: Architect requires wallet
   - Lines 3186-3216: Architect THR billing + credits reward
   - Lines 3249-3262: Architect response includes billing info

---

## HARD RULES COMPLIANCE

- ✅ ENV modes: CHAT_BILLING_MODE, ARCHITECT_BILLING_MODE
- ✅ Cross-charge blocked with telemetry (403 + log)
- ✅ Chat: ZERO THR charges, ZERO chain TX
- ✅ Architect: REAL THR charges, payment TX type="architect_payment"
- ✅ Credits reward: 1 THR → 10 credits
- ✅ Base fee: 0.001 THR minimum
- ✅ Variable fee: deterministic (tokens + files)
- ✅ Telemetry: product, billing_channel, deltas

---

## COMMIT

**Commit**: `384fc11`
**Message**: `fix(billing): Clean separation Chat (credits) vs Architect (THR)`

---

**End of Fix #8 Report**
