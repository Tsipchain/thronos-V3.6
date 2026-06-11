# Mining V1 - Next Phase Design

**Status**: DESIGN ONLY (No implementation yet)  
**Target**: Pledge-native miner kit + canonical signing  
**Constraints**: Zero changes to mining validation, block rules, or ledger

---

## Overview

Mining V1 extends Wallet V1 centralized signing to mining operations. Goals:

1. **Pledge-native kit**: Miner downloads kit after pledge, contains canonical address + signing material
2. **Worker format**: `<canonical_v1_address>.<worker_name>` (e.g., `THRXXX...ABC.worker-1`)
3. **Payouts**: Mining rewards go to canonical_v1_address (not legacy)
4. **Pool economics**: Fee splits (pool fee / miner reward / AI reward / burn)

---

## Architecture

### Pledge Flow → Miner Kit

```
User pledges (legacy or V1)
  ↓
Backend assigns canonical_v1_address
  ↓
Return: "Download Miner Kit" link
  ↓
Kit contains:
  - canonical_v1_address
  - public_key (for signature verification)
  - worker_name suggestion
  - pool_url, pool_fee_pct
```

### Miner Submission Flow

```
Miner submits share:
  share_data = {
    worker: "<canonical_v1_address>.worker-1",
    nonce: "...",
    difficulty: "...",
    timestamp: "...",
    canonical_json: "{...}"
  }
  signature = sign(canonical_json, private_key)
  ↓
Backend verify_mining_share():
  1. Extract canonical_v1_address from worker name
  2. Verify signature matches public_key
  3. Check canonical_json integrity
  4. Check nonce/timestamp/difficulty
  5. If valid: credit miner reward to canonical_v1_address
  6. If invalid: reject (no consensus impact)
```

### Reward Distribution (Per Share)

```
Total Reward = BASE_MINING_REWARD (e.g., 1 THR per valid share)

Split:
  - pool_fee = total * pool_fee_pct (e.g., 2%)
  - miner_reward = total * (1 - pool_fee_pct - ai_fee_pct - burn_pct)
  - ai_reward = total * ai_fee_pct (e.g., 1%)
  - burned = total * burn_pct (e.g., 0.5%)

Example (pool_fee=2%, ai_fee=1%, burn=0.5%):
  total = 1 THR
  pool_fee = 0.02 THR
  miner = 0.965 THR
  ai = 0.01 THR
  burn = 0.005 THR
```

---

## Kit Design

### Miner Kit File Contents

```json
{
  "version": "mining-v1-2026-06",
  "pledge_tx": "TXID...",
  "canonical_v1_address": "THR683318ACF083723B3EDFE6C0A30AD62670F00353",
  "pool_url": "stratum+tcp://pool.thronos.io:3334",
  "pool_fee_pct": 2.0,
  "suggested_worker_name": "my-miner-1",
  "public_key": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798",
  "start_difficulty": 1000,
  "reward_split": {
    "miner_pct": 96.5,
    "pool_pct": 2.0,
    "ai_pct": 1.0,
    "burn_pct": 0.5
  },
  "docs": "See https://thronos.io/mining/setup"
}
```

### Private Key Handling

**Option 1: Ephemeral** (Recommended for security)
- Private key NOT in kit file
- Miner generates locally on first run
- Derived from miner's password (Argon2)
- Public key sent to backend for whitelist

**Option 2: Kit-embedded** (Simpler UX)
- Private key encrypted in kit file
- Requires password to decrypt
- More convenient but requires careful key management

**Recommendation**: Option 1 (ephemeral) for production

---

## Backend Changes (Minimal)

### New Endpoint: `/api/mining/v1/verify_share`

```python
@app.route("/api/mining/v1/verify_share", methods=["POST"])
def verify_mining_share():
    data = request.get_json() or {}
    
    # Extract worker address
    worker = data.get("worker", "")  # "THRXXX...ABC.worker-1"
    canonical_addr = worker.split(".")[0] if "." in worker else ""
    
    if not canonical_addr or not canonical_addr.startswith("THR"):
        return jsonify(ok=False, error="invalid_worker_format"), 400
    
    # Verify signature
    signed_share = data.get("signed_share", {})
    public_key = data.get("public_key", "")
    signature = data.get("signature", "")
    
    if not verify_mining_signature(signed_share, signature, public_key):
        return jsonify(ok=False, error="invalid_signature"), 400
    
    # Validate share data
    nonce = signed_share.get("nonce")
    difficulty = signed_share.get("difficulty")
    
    if not validate_mining_difficulty(nonce, difficulty):
        return jsonify(ok=False, error="invalid_difficulty"), 400
    
    # Credit miner (idempotent by nonce)
    reward = calculate_mining_reward()
    credit_miner_reward(canonical_addr, reward, nonce)
    
    return jsonify(ok=True, reward=reward), 200
```

### Whitelist Endpoint: `/api/mining/v1/register_public_key`

```python
@app.route("/api/mining/v1/register_public_key", methods=["POST"])
def register_public_key():
    # Called by miner after generating local key
    data = request.get_json() or {}
    canonical_addr = data.get("canonical_v1_address", "")
    public_key = data.get("public_key", "")
    pledge_tx = data.get("pledge_tx", "")
    
    # Verify pledge exists
    if not verify_pledge_exists(canonical_addr, pledge_tx):
        return jsonify(ok=False, error="pledge_not_found"), 404
    
    # Store public key for future verifications
    store_miner_public_key(canonical_addr, public_key)
    
    return jsonify(ok=True, status="key_registered"), 200
```

---

## Security Considerations

### Signature Verification

```
canonicalized_share = canonical_json(signed_share)
  = '{"canonical_json":"...","difficulty":"...","nonce":"...","timestamp":"...","worker":"..."}'
  
signature must be valid ECDSA-Secp256k1 over SHA256(canonicalized_share)
```

### Nonce Replay Protection

```
shares[nonce] tracked in Redis/ledger
If nonce seen before → reject (idempotent)
If nonce new → accept and store
```

### Difficulty Validation

```
share_hash = SHA256(nonce + block_data)
required_leading_zeros = difficulty_bits
if count_leading_zeros(share_hash) >= required_leading_zeros:
  accept share
else:
  reject (too easy, not valid work)
```

### Rate Limiting

```
Per canonical_v1_address:
  max_shares_per_minute = POOL_RATE_LIMIT (e.g., 100)
  if exceeded: reject share, no credit
  (prevents spam/DoS)
```

---

## UI/UX Flow

### Download Miner Kit (After Pledge)

```
User pledges (existing flow)
  ↓
Backend: "Pledge successful!"
  ↓
Show: "Download Miner Kit" button
  ↓
Kit file: pledge_123456_miner.json
  ↓
User: run setup script with kit file
  ↓
Script: generates local keys, registers public key
  ↓
Script: connects to pool, starts mining
```

### Miner Status Dashboard

```
/mining/status

Shows:
  - canonical_v1_address
  - shares submitted (last 24h)
  - rewards earned (last 24h)
  - pool fee paid
  - current difficulty
  - workers active
```

---

## Implementation Roadmap

### Phase 1: Kit Gating (Week 1)

- [x] Wallet V1 basic signing (done in PR-A/B/C/D)
- [ ] Pledge backend: assign canonical_v1_address
- [ ] Kit generation endpoint
- [ ] Kit file format (JSON)
- [ ] Basic docs

### Phase 2: Signature Verification (Week 2)

- [ ] verify_mining_share() endpoint
- [ ] ECDSA signature validation
- [ ] Nonce replay protection
- [ ] Difficulty validation

### Phase 3: Reward Distribution (Week 3)

- [ ] Miner reward credit (to canonical_v1_address)
- [ ] Pool fee split
- [ ] AI reward allocation
- [ ] Burn tracking

### Phase 4: Monitoring & UI (Week 4)

- [ ] Miner status dashboard
- [ ] Reward history
- [ ] Rate limiting
- [ ] Alerts (if share rate drops)

---

## Testing Strategy

### Unit Tests

```python
# Test kit generation
test_mining_kit_generation()
test_kit_contains_all_fields()

# Test signature verification
test_valid_mining_share_accepted()
test_invalid_signature_rejected()
test_malformed_share_rejected()

# Test difficulty validation
test_valid_difficulty_accepted()
test_invalid_difficulty_rejected()

# Test nonce replay
test_duplicate_nonce_rejected()
test_new_nonce_accepted()

# Test reward calculation
test_reward_split_calculation()
test_canonical_address_credit()
```

### E2E Tests

```python
# Full flow
test_pledge_to_first_share()
test_multiple_workers_same_address()
test_reward_accumulation()
test_pool_fee_deduction()
```

### Performance Tests

```python
# Load testing
test_1000_shares_per_second()
test_concurrent_miners()
test_public_key_lookup_latency()
```

---

## Known Constraints

✅ **No changes to**:
- Block validation rules
- Mining difficulty algorithm (Thronos-specific)
- Ledger state machine
- Consensus mechanism
- Reward halving schedule
- Pool consensus

⚠️ **Changes only to**:
- Authentication path (Wallet V1 signing)
- Miner registration flow
- Share verification (add signature check)
- Reward crediting (same destination, just canonical address)

---

## Rollback Plan

If Mining V1 fails:

1. Keep legacy mining endpoint active
2. Miners can switch back to legacy auth_secret
3. No consensus impact (new auth is additional layer, not replacement)
4. Revert canonical_v1_address assignment (goes back to legacy address)

---

## Success Metrics

After implementation:

- [ ] Pledged users can download miner kit
- [ ] Kit contains valid canonical address + public key
- [ ] Miners can submit signed shares
- [ ] Rewards credited to canonical_v1_address within 1 block
- [ ] Share rate: 1000+ shares/sec without degradation
- [ ] Rate limiting prevents spam
- [ ] Pool fee split correct
- [ ] No consensus changes (0 block validation changes)

---

## Next Steps

1. **Implement Phase 1**: Kit gating + generation
2. **Review security model** with team
3. **Testnet deployment**: Full flow with real miners
4. **Performance tuning**: 1000+ shares/sec baseline
5. **Mainnet deployment**: Gradual rollout (opt-in for miners)

---

**Document Status**: DESIGN PHASE (No implementation)  
**Ready for**: Team review + security audit  
**Approval Required**: Before Phase 1 starts  
**Estimated Effort**: 3-4 weeks (4 phases)
