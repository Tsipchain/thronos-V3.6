# BILLING SEPARATION REPORT - Chat vs Architect

**Date**: 2026-01-04
**Branch**: `claude/fix-wallet-ui-final-gUEre`
**Type**: ZERO TRUST ANALYSIS (PATCH-ONLY MODE)

---

## EXECUTIVE SUMMARY

**Current State**: Chat and Architect billing logic is COMPLETELY SEPARATED.
- Chat: Uses credits system (purchase with THR → get credits → spend credits per message)
- Architect: NO billing logic at all (accepts wallet but doesn't charge anything)

**No Mixed Logic Found**: Both endpoints use distinct code paths with no shared billing functions.

---

## DETAILED ANALYSIS

### 1. CHAT ENDPOINT - Credits-Only System

**Endpoint**: `/api/chat` (POST)
**File**: `server.py:3934-4200`

#### Credits Validation (Lines 4009-4055)

```python
# Line 4009-4033: If wallet provided, enforce credits model
if wallet:
    credits_map = load_ai_credits()
    try:
        credits_value = int(credits_map.get(wallet, 0) or 0)
    except (TypeError, ValueError):
        credits_value = 0

    if credits_value <= 0:
        warning_text = (
            "Δεν έχεις άλλα Quantum credits γι' αυτό το THR wallet.\\n"
            "Πήγαινε στη σελίδα AI Packs και αγόρασε πακέτο για να συνεχίσεις."
        )
        return jsonify(
            response=warning_text,
            quantum_key=ai_agent.generate_quantum_key(),
            status="no_credits",
            wallet=wallet,
            credits=0,
            files=[],
            session_id=session_id,
        ), 200
```

**Verdict**: ✅ Correctly refuses service if credits = 0, directs user to buy AI packs.

#### Credits Deduction (Lines 4145-4155)

```python
# Line 4145-4155: Deduct credits after successful AI call
if wallet:
    credits_map = load_ai_credits()
    try:
        before = int(credits_map.get(wallet, 0) or 0)
    except (TypeError, ValueError):
        before = 0
    after = max(0, before - AI_CREDIT_COST_PER_MSG)
    credits_map[wallet] = after
    save_ai_credits(credits_map)
    credits_for_frontend = after
    ai_credits_spent = max(0.0, float(before - after))
```

**Verdict**: ✅ Deducts AI_CREDIT_COST_PER_MSG (default 1) per message. No THR transfer.

#### Demo Mode (Lines 4034-4059)

```python
# Line 4034-4059: Free demo mode for users without wallet
else:
    demo_key = session_id or "default"
    counters = load_ai_free_usage()
    used = int(counters.get(demo_key, 0))
    if used >= AI_FREE_MESSAGES_LIMIT:
        warning_text = (
            "Έχεις εξαντλήσει το όριο των δωρεάν μηνυμάτων χωρίς THR wallet.\\n"
            "Σύνδεσε ένα πορτοφόλι THR για να συνεχίσεις ή αγόρασε AI pack."
        )
        return jsonify(response=warning_text, quantum_key=..., status="no_credits", ...), 200
    counters[demo_key] = used + 1
    save_ai_free_usage(counters)
```

**Verdict**: ✅ Demo mode uses free message counter, no THR involved.

---

### 2. ARCHITECT ENDPOINT - No Billing

**Endpoint**: `/api/architect_generate` (POST)
**File**: `server.py:3082-3215`

#### Full Implementation

```python
# Line 3082-3215: Architect endpoint
@app.route("/api/architect_generate", methods=["POST"])
def api_architect_generate():
    """
    Thronos AI Architect:
    - Generates full project implementation based on blueprint + specs.
    - Returns [[FILE:...]] blocks.
    - Writes files to AI_FILES_DIR.
    """
    if not ai_agent:
        return jsonify(error="AI Agent not available"), 503

    data = request.get_json() or {}
    wallet      = (data.get("wallet") or "").strip()  # Line 3094: wallet accepted
    session_id  = (data.get("session_id") or "").strip() or None
    blueprint   = (data.get("blueprint") or "").strip()
    project_spec = (data.get("spec") or data.get("specs") or "").strip()
    model_key   = (data.get("model") or data.get("model_key") or "gpt-4o").strip()

    # ... blueprint loading (lines 3103-3122) ...

    # Line 3146-3150: Call AI (no billing check, no deduction)
    raw = ai_agent.generate_response(prompt, wallet=wallet, model_key=model_key, session_id=session_id)

    # ... file extraction and zip creation (lines 3152-3205) ...

    # Line 3207-3215: Return response (no billing mentioned)
    return jsonify({
        "status": status,
        "quantum_key": quantum_key,
        "blueprint": blueprint,
        "response": cleaned,
        "files": resp_files,
        "zip_url": zip_url,
        "session_id": session_id,
    }), 200
```

**Observations**:
- ✅ Accepts `wallet` parameter (line 3094)
- ✅ Passes wallet to `ai_agent.generate_response()` (line 3150)
- ❌ NO wallet balance check
- ❌ NO THR deduction
- ❌ NO credits check
- ❌ NO on-chain transaction creation

**Verdict**: NO billing logic implemented. Service is FREE.

---

### 3. AI PACKS PURCHASE SYSTEM

**Endpoint**: `/api/ai_purchase_pack` (POST)
**File**: `server.py:4945-5024`

#### THR Payment → Credits Exchange (Lines 4979-5002)

```python
# Line 4979-4994: Deduct THR from wallet, credit AI_WALLET_ADDRESS
ledger = load_json(LEDGER_FILE, {})
balance = float(ledger.get(wallet, 0.0))

if balance < price:
    return jsonify(
        status="denied",
        message=f"Insufficient THR funds (έχεις {balance}, χρειάζονται {price})."
    ), 400

ledger[wallet] = round(balance - price, 6)
ledger[AI_WALLET_ADDRESS] = round(
    float(ledger.get(AI_WALLET_ADDRESS, 0.0)) + price,
    6,
)
save_json(LEDGER_FILE, ledger)

# Line 4996-5002: Add credits to wallet
credits = load_ai_credits()
current_credits = int(credits.get(wallet, 0))
add_credits = int(pack.get("credits", 0))
total_credits = current_credits + add_credits
credits[wallet] = total_credits
save_ai_credits(credits)
```

**Verdict**: ✅ On-chain THR payment to BUY credit packs (not direct AI usage billing).

#### Chain Transaction (Lines 5004-5018)

```python
# Line 5004-5018: Record service_payment transaction
chain = load_json(CHAIN_FILE, [])
tx = {
    "type": "service_payment",
    "service": "AI_PACK",
    "pack_code": pack.get("code"),
    "pack_credits": add_credits,
    "from": wallet,
    "to": AI_WALLET_ADDRESS,
    "amount": price,
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    "tx_id": f"AI-{int(time.time())}-{len(chain)}",
}
chain.append(tx)
save_json(CHAIN_FILE, chain)
```

**Verdict**: ✅ Creates on-chain transaction of type "service_payment" for pack purchase.

---

## SEPARATION VERIFICATION

### ✅ Chat Uses Credits ONLY
- **Credits validation**: `server.py:4009-4033`
- **Credits deduction**: `server.py:4145-4155`
- **Demo mode counter**: `server.py:4034-4059`
- **NO on-chain THR deduction per message**
- **THR used ONLY to purchase credit packs** (via `/api/ai_purchase_pack`)

### ❌ Architect Has NO Billing
- **NO credits check**: Architect endpoint never checks credits
- **NO THR deduction**: Architect endpoint never deducts THR
- **NO billing enforcement**: Currently FREE for all users

### ✅ No Mixed Logic
- Chat and Architect use completely separate code paths
- No shared billing validation functions
- No conditional logic that mixes credits and THR

---

## USER REQUIREMENT vs CURRENT STATE

### User Requirement
> "Chat (at /chat): credits/packs only. No on-chain THR billing."

**Status**: ✅ ALREADY IMPLEMENTED
- Chat uses credits deducted from `ai_credits.json`
- Credits purchased via THR → pack exchange (not direct billing)
- No per-message on-chain THR transfers

### User Requirement
> "Architect (at /architect): on-chain THR billing per usage. No packs."

**Status**: ❌ NOT IMPLEMENTED
- Architect currently has NO billing
- Would require NEW logic to:
  1. Check wallet THR balance before generation
  2. Calculate cost based on model/tokens/blueprint complexity
  3. Deduct THR from wallet ledger
  4. Create on-chain transaction (type: "ai_architect_usage" or similar)
  5. Handle insufficient balance gracefully

**ZERO TRUST NOTE**: Adding THR billing to Architect would be NEW LOGIC, not a patch. This violates "PATCH-ONLY" rule unless user explicitly approves.

---

## OBSERVABLE ENDPOINTS

### Chat Billing Flow
```
1. User buys AI pack: POST /api/ai_purchase_pack
   - Input: {wallet, pack: "basic"}
   - Deducts THR from wallet (e.g., 10 THR)
   - Adds credits to wallet (e.g., 100 credits)
   - Creates on-chain TX type "service_payment"

2. User sends chat message: POST /api/chat
   - Input: {wallet, message, session_id}
   - Checks credits balance
   - If credits > 0: process message, deduct 1 credit
   - If credits = 0: return "no_credits" error
   - NO THR deduction
```

### Architect Billing Flow (Current)
```
1. User generates project: POST /api/architect_generate
   - Input: {wallet, blueprint, spec, model}
   - NO balance check
   - NO billing enforcement
   - Returns generated files
   - FREE service
```

---

## ACCEPTANCE TESTS

### Chat - Credits Only (Already Passing)
- [x] User with 0 credits → HTTP 200 {status: "no_credits", message: "buy pack"}
- [x] User with 10 credits → send message → credits deducted to 9
- [x] Demo user (no wallet) → limited to AI_FREE_MESSAGES_LIMIT messages
- [x] NO THR deduction from wallet when sending chat messages
- [x] THR ONLY deducted when purchasing packs

### Architect - No Billing (Current State)
- [x] User with 0 THR balance → generates project successfully (NO enforcement)
- [x] User with 1000 THR balance → generates project → THR not deducted
- [ ] **MISSING**: THR balance check before generation
- [ ] **MISSING**: THR deduction after successful generation
- [ ] **MISSING**: On-chain transaction creation for architect usage

---

## RECOMMENDATION

**Current Implementation**: ✅ Chat and Architect are COMPLETELY SEPARATED (no mixed logic).

**User Requirement Fulfillment**:
1. ✅ Chat uses credits-only (correct)
2. ❌ Architect has no billing (should charge THR per usage)

**Next Steps** (requires user approval due to PATCH-ONLY mode):
1. If user wants Architect THR billing:
   - **NOT a patch** - would be new billing logic
   - Requires explicit approval to add new code
   - Would need to design: cost model, balance checks, transaction creation

2. If user wants to keep current state:
   - Document that Architect is intentionally free
   - No changes needed

**AWAITING USER DECISION**: Should Architect remain free, or add THR billing (new logic)?

---

**End of Report - Zero Trust Mode**
