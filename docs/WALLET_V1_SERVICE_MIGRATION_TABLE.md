# Wallet V1 Service Migration Inventory

## Services & Endpoints Requiring V1 Signing

### Core Financial Services

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Swap | `/api/swap/execute` | V1 custom | V1 unified | ✅ **DONE** | - | #614 | Uses unified signing contract |
| Pools | `/api/v1/pools/add` | V1 custom | V1 unified | ⏳ **QUEUE** | 1 day | #615 | Pool math untouched |
| Pools | `/api/v1/pools/remove` | V1 custom | V1 unified | ⏳ **QUEUE** | 1 day | #615 | Pool math untouched |
| Pools | `/api/v1/pools/create` | V1 custom | V1 unified | ⏳ **QUEUE** | 1 day | #615 | Pool math untouched |
| Send | `/api/send_thr` | Legacy auth_secret | V1 unified | ⏳ **PHASE 2** | 2 days | #616 | Largest surface area |

---

### Creator Economy

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Music Tips | `/api/wallet/tip` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #617 | REST API endpoint |
| Creator Rewards | `/api/wallet/payout` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #617 | Batch payments |
| NFT Marketplace | `/api/nft/buy` | Legacy | V1 unified | ⏳ **PHASE 2** | 2 days | #621 | Complex payload |
| NFT Sell | `/api/nft/sell` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #621 | Listing + signature |

---

### L2E Platform

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Claim Rewards | `/api/l2e/claim_rewards` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #618 | High frequency |
| Stake THR | `/api/l2e/stake` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #618 | Amount validation |
| Unstake THR | `/api/l2e/unstake` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #618 | Re-auth for early unstake |
| Swap Rewards | `/api/l2e/swap_rewards` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #618 | Compound claim |

---

### University Tenant

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Assign Grades (Payment) | `/api/tenant/assign_grade` | Legacy | V1 unified | ⏳ **PHASE 2** | 2 days | #619 | Attestation signing |
| Student Payment | `/api/tenant/pay_student` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #619 | Batch support |
| Curriculum Update | `/api/tenant/update_curriculum` | Admin token | Admin token | ✅ **SKIP** | - | - | No wallet needed |
| Degree Issuance | `/api/tenant/issue_degree` | Admin token | Admin token | ✅ **SKIP** | - | - | Issuer-only, not wallet |

---

### Bridge & Cross-Chain

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Bridge Deposit | `/api/bridge/deposit` | Legacy | V1 unified | ⏳ **PHASE 2** | 2 days | #620 | High risk (re-auth) |
| Bridge Withdraw | `/api/bridge/withdraw` | Legacy | V1 unified | ⏳ **PHASE 2** | 2 days | #620 | Cross-chain verification |
| Atomic Swap | `/api/atomic_swap/initiate` | Legacy | V1 unified | ⏳ **PHASE 3** | 3 days | #622 | Complex state machine |

---

### AI & Computation

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Purchase Credits | `/api/ai/buy_credits` | Legacy | V1 unified | ⏳ **PHASE 2** | 1 day | #623 | Straightforward |
| Compute Request | `/api/ai/submit_compute` | Legacy | V1 unified | ⏳ **PHASE 2** | 2 days | #623 | Payload includes code/data |
| Model Fine-tune | `/api/ai/fine_tune` | Legacy | V1 unified | ⏳ **PHASE 3** | 3 days | #624 | Training cost estimation |

---

### IoT & Devices

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Device Register | `/api/iot/register_device` | Legacy | V1 unified | ⏳ **PHASE 3** | 1 day | #625 | Device ownership proof |
| Sensor Data Submit | `/api/iot/submit_sensor_data` | API key | V1 unified | ⏳ **PHASE 3** | 2 days | #625 | Frequent, lightweight payload |
| Device Control | `/api/iot/control_device` | API key | V1 unified | ⏳ **PHASE 3** | 1 day | #625 | Real-time, may need priority |

---

### Gaming & Rewards

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| Game Deposit | `/api/game/deposit` | Legacy | V1 unified | ⏳ **PHASE 3** | 1 day | #626 | Escrow-backed |
| Game Withdraw | `/api/game/withdraw` | Legacy | V1 unified | ⏳ **PHASE 3** | 1 day | #626 | Escrow release |
| Achievement Reward | `/api/game/reward` | Legacy | V1 unified | ⏳ **PHASE 3** | 1 day | #626 | Server-initiated, but user signs |

---

### Misc / Experimental

| Service | Endpoint | Current Auth | Target Auth | Status | Est. Effort | PR # | Notes |
|---------|----------|--------------|-------------|--------|-------------|------|-------|
| DAO Proposal Vote | `/api/dao/vote` | Legacy | V1 unified | ⏳ **PHASE 3** | 1 day | #627 | Governance |
| DAO Treasury Spend | `/api/dao/spend` | Multi-sig | Multi-sig | ✅ **SKIP** | - | - | Not single-user |
| Data Marketplace Buy | `/api/data/buy_listing` | Legacy | V1 unified | ⏳ **PHASE 3** | 2 days | #628 | Data rights transfer |
| Feedback Bounty | `/api/feedback/submit_claim` | Legacy | V1 unified | ⏳ **PHASE 3** | 1 day | #629 | Micro-rewards |

---

## Migration Phases

### Phase 0: Immediate (Week 1-2) - PR #614

- ✅ Swap signing unified
- ✅ 36 regression tests
- ✅ Modal state machine fixed
- ✅ Recovery kit primary
- ✅ Session TTL verified

**Deploy**: Staging → Production

---

### Phase 1 (Week 3-4) - PR #615

**Scope**: Pool operations

- `/api/v1/pools/add` → V1 unified
- `/api/v1/pools/remove` → V1 unified
- `/api/v1/pools/create` → V1 unified

**Effort**: ~3 days  
**Risk**: LOW (pools math untouched, only signing format changed)  
**Tests**: 15+ tests for pool signing patterns

---

### Phase 2 (Week 5-8) - PRs #616-#629 (Batch 1)

**Scope**: High-frequency, straightforward endpoints

Priority order:
1. **#616**: Send TXN (`/api/send_thr`) - 2 days
2. **#617**: Music tips + creator rewards - 2 days
3. **#618**: L2E claims + staking - 2 days
4. **#619**: University tenant actions - 2 days
5. **#620**: Bridge operations - 2 days
6. **#621**: NFT buy/sell - 2 days
7. **#623**: AI credits - 1 day

**Total Effort**: ~15 days (3 weeks with testing)  
**Risk**: MEDIUM (high surface area, but straightforward payloads)  
**Deploy**: Rolling batch (one per week) with E2E test between each

---

### Phase 3 (Week 9-12) - PRs #622-#629 (Batch 2)

**Scope**: Complex state machines, experimental services

- Atomic swaps (#622)
- Model fine-tune (#624)
- IoT device control (#625)
- Gaming (#626)
- DAO governance (#627)
- Data marketplace (#628)
- Feedback bounty (#629)

**Effort**: ~15 days  
**Risk**: HIGH (complex payloads, state dependencies)  
**Deploy**: Careful testing per service

---

## Summary Statistics

| Metric | Count | Notes |
|--------|-------|-------|
| **Total endpoints** | 42 | Core + experimental |
| **Already migrated** | 1 | Swap (#614) |
| **Queue for Phase 1** | 3 | Pools |
| **Queue for Phase 2** | 16 | High-frequency, straightforward |
| **Queue for Phase 3** | 19 | Complex, experimental |
| **Skip (no wallet needed)** | 3 | Curriculum, degree, multi-sig |

---

## Dependency Graph

```
PR #614 (Swap)
    ↓
PR #615 (Pools) ← Depends on #614 (unified contract)
    ↓
PR #616 (Send) ← Depends on #615 (proven pattern)
    ↓
PR #617-#620 (Parallel: Tips, L2E, University, Bridge)
    ↓
PR #621-#629 (Parallel: NFT, AI, IoT, Gaming, DAO, Data, Feedback)
```

---

## Risk-Reduced Deployment

To minimize production impact:

1. **Feature flag**: `WALLET_V1_UNIFIED_SIGNING_ENABLED` (default false for Phase 1)
2. **Canary**: Deploy Phase 1 to 5% users first (1 week)
3. **Monitoring**: Track signature errors, no 500s, session TTL OK
4. **Rollback**: If issues, disable flag (instant revert to legacy auth)
5. **Approval**: Manual sign-off per phase before full rollout

---

## Testing Requirements

Each PR must include:

```python
# tests/test_wallet_v1_<service>_signing.py

def test_canonical_payload():
    """Verify payload shape matches backend"""
    
def test_valid_signature():
    """Verify valid signature is accepted"""
    
def test_invalid_signature_returns_400():
    """Verify 400 error (not 500)"""
    
def test_high_risk_action_requires_reauth():
    """If applicable: bridge > $1000, etc"""
    
def test_no_legacy_fallback_when_v1_exists():
    """Explicit error, no silent fallback"""
```

---

**Total Migration Effort**: 8-10 weeks (all phases)  
**Production Rollout**: 12 weeks (including validation)  
**Go-Live Target**: Q3 2026

