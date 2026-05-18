# BTC Pledge System & Network Pool
**Phase 7.1: Bitcoin Pledge, Fees & Future Fiat Conversion**

---

## Overview

This document explains how the Bitcoin pledge system works for large mining farms participating in the Thronos heat recovery bridge, how fees flow into the network BTC pool, and the roadmap for fiat conversion via Ether.fi (and eventually a Thronos Visa card).

---

## Pledge & Fee Architecture

```
┌─────────────────────────────────────────────────────────────┐
│             BTC Mining Farm Lifecycle                       │
└─────────────────────────────────────────────────────────────┘

  1. Farm Registers                  → Status: REGISTERED
  2. Calculate Required Pledge       → 1% of monthly BTC est.
  3. Send BTC Pledge to Pool         → Multisig address
  4. Confirm Pledge on-chain         → Status: ACTIVE
  5. Start Heat Mining               → Submit proofs
  6. Per-proof Fee Collection        → 0.5% of mined BTC
  7. Receive THR Bonuses             → 5-40% based on tier

  ┌─────────────────────────────────────────────────────────┐
  │           Network BTC Pool (Multisig)                   │
  ├─────────────────────────────────────────────────────────┤
  │                                                         │
  │  Total Balance = Pledges + Fees - Payouts              │
  │                                                         │
  │  Allocation:                                            │
  │  ├─ 20% Reserve (cross-chain settlement)               │
  │  ├─ 50% Payouts (THR bonus settlements)                │
  │  └─ 30% Available for fiat conversion                  │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌─────────────────────────┐
              │   Ether.fi (Phase 7.2)  │
              │   • Convert BTC → USDC  │
              │   • USDC → Fiat wires   │
              │   • Direct EUR/USD off  │
              └─────────────────────────┘
                          │
                          ▼
              ┌─────────────────────────┐
              │ Thronos Visa (Phase 8)  │
              │   • Gated on user count │
              │   • Reserve-backed      │
              │   • Spend anywhere      │
              └─────────────────────────┘
```

---

## 1. BTC Pledge System

### Why Pledges?

Pledges serve three purposes:

1. **Skin in the game** — Farms commit BTC to demonstrate genuine participation
2. **Fraud collateral** — If farm is permanently banned, pledge can be seized
3. **Network treasury** — Pledges contribute to the pool that backs THR bonuses

### Pledge Calculation

```python
PLEDGE_RATIO = 0.01  # 1%

# Estimate monthly BTC earnings from hardware:
monthly_btc_estimate = (total_hashrate_th / 25.0) * 0.00004

# Required pledge:
pledge_btc = monthly_btc_estimate * PLEDGE_RATIO
```

### Example Calculations

| Farm Size | Hashrate | Monthly BTC Est. | Required Pledge |
|-----------|----------|------------------|-----------------|
| 10 × S21  | 2.5 PH/s | 0.0040 BTC       | 0.00004 BTC (~$2) |
| 100 × S21 | 25.2 PH/s | 0.0403 BTC      | 0.00040 BTC (~$16) |
| 500 × S21 | 126 PH/s | 0.2016 BTC       | 0.00201 BTC (~$80) |
| 1000 × S21 | 252 PH/s | 0.4032 BTC      | 0.00403 BTC (~$161) |

**Pledges are intentionally small** — they're a commitment signal, not a barrier to entry.

### Pledge Flow

```
1. GET /api/btc-mining/pledge/required/<btc_address>
   → Returns: { required_pledge_satoshis, pool_address }

2. Farm sends BTC transaction:
   - From: Farm's BTC address
   - To:   Network pool multisig
   - Amount: required_pledge_satoshis

3. POST /api/btc-mining/pledge/confirm
   {
     "btc_address": "1A1z...",
     "pledge_satoshis": 40000,
     "btc_tx_hash": "abc123..."
   }
   → Farm status becomes ACTIVE
   → Eligible for heat bonuses
```

---

## 2. Per-Proof Fee System

### Fee Structure

```python
HEAT_PROOF_FEE_RATIO = 0.005  # 0.5%

# When farm submits valid heat proof and confirms BTC mining:
fee_satoshis = btc_mined_satoshis * HEAT_PROOF_FEE_RATIO
```

### Why 0.5% Per Proof?

- **Sustainable revenue** for the network pool
- **Aligned incentives** — only successful mining triggers fees
- **Low burden** — 0.5% is well below typical pool fees (1-3%)
- **Predictable** — farms know exactly what to expect

### Example Fee Collection

```
Farm: 100 × Antminer S21
Daily BTC mined: 0.00134 BTC (134,000 satoshis)
Daily fee: 134,000 × 0.005 = 670 satoshis (~$0.27)
Monthly fee: ~20,100 satoshis (~$8)
Annual fee: ~241,200 satoshis (~$96)

Farm's daily revenue: $26 BTC + $34,560 THR heat bonuses
Fee as % of total revenue: 0.0008% (negligible)
```

---

## 3. Network BTC Pool Allocation

### Pool Composition

The pool is held in a multisig address controlled by:
- Thronos foundation (2 keys)
- Independent validators (3 keys)
- Threshold: 3-of-5 signatures required

### Funds Allocation

```
Total Pool Balance
├─ 20% Reserve (cross-chain settlement buffer)
│   └─ Used for: emergency liquidity, withdrawal requests
├─ 50% Payouts (active settlement pool)
│   └─ Used for: THR bonus payouts, farm withdrawal claims
└─ 30% Available for Conversion
    └─ Used for: fiat conversion via Ether.fi
```

### Pool Status Endpoint

```
GET /api/btc-mining/network-pool

Returns:
{
    "pool_address": "bc1qthronoschain...",
    "total_balance_btc": 0.5023,
    "total_pledged_satoshis": 4000000,
    "total_fees_collected_satoshis": 46230000,
    "total_payouts_satoshis": 16000000,
    "minimum_reserve_satoshis": 6846000,
    "available_for_payouts": 17115000,
    "available_for_conversion": 10269000,
    "last_updated": "2026-05-18T14:30:00Z",
    "roadmap": { ... }
}
```

---

## 4. Cross-Chain Settlement

### How THR Bonuses Get Paid Out

When a farm earns THR bonuses from heat recovery:

```
1. Farm submits heat proof
   → Validated → Bonus calculated (e.g., 460 THR)

2. THR address credited
   → On Thronos chain immediately

3. BTC pool tracks settlement
   → Allocates portion of pool for this settlement
   → If pool is low, settlements queue up

4. Bridge worker monitors pool
   → When pool > threshold, processes queued settlements
   → BTC equivalent moved between accounts
```

### Settlement Atomicity

To prevent double-spend or settlement failures:

- **Pre-allocation** — Bonus is reserved in pool before THR is minted
- **Confirmation requirement** — 6 BTC confirmations before final settlement
- **Reversal capability** — If THR mint fails, BTC pledge can be returned
- **Audit trail** — Every settlement logged with both chain TX hashes

---

## 5. Roadmap: Fiat Conversion via Ether.fi

### Why Ether.fi?

Ether.fi is a non-custodial liquid restaking platform that:
- Has direct fiat off-ramps (USDC, EUR, USD wire)
- Supports cross-chain transfers (BTC ↔ ETH ↔ USDC)
- Provides regulated banking partnerships
- Offers competitive conversion rates

### Conversion Flow (Future)

```
1. Network pool reaches threshold (e.g., 1 BTC available)
   → Triggers conversion job

2. Bridge worker initiates conversion:
   BTC → wBTC (Wrapped BTC on Ethereum)
   wBTC → USDC (Decentralized exchange swap)
   USDC → Bank transfer (via Ether.fi banking partner)

3. Fiat received in Thronos foundation account
   → Available for operations, reserves, treasury management

4. Conversion rates logged
   → Transparency for community
   → Slippage minimized via aggregated swaps
```

### Conversion Frequency

- **Initial Phase:** Manual conversion (weekly review)
- **Phase 7.1:** Semi-automated (monthly threshold-based)
- **Phase 7.2:** Fully automated (real-time threshold triggers)

### Conversion Rate Transparency

All conversions will be:
- Publicly logged on Thronos chain
- Auditable via Ether.fi receipts
- Slippage capped at 2% (configurable)
- Available via `/api/btc-mining/conversion-history` (future endpoint)

---

## 6. Future: Thronos Visa Card

### When This Becomes Viable

**Trigger Criteria** (all must be met):
- 10,000+ active wallets
- $50M+ in pool reserves
- Established banking partnership
- Regulatory approvals (BSA, KYC, AML)
- Card network certification (Visa/Mastercard)

### Card Architecture (Future)

```
Pool Reserve → Visa Card Issuer → Cardholder Account
                                      │
                                      ├─ Spend at any merchant
                                      ├─ ATM withdrawals
                                      └─ Online payments

Card Funding Mechanism:
1. User links THR wallet to card
2. Spend triggers THR → USD conversion
3. Conversion uses pool reserves (priced live)
4. Pool replenished from ongoing pledges/fees
```

### Why Wait?

- Card programs require minimum $5-10M in collateral
- BSA/AML compliance costs $100K-500K initially
- User volume must justify operational overhead
- Premature launch risks regulatory issues

### Current Status

**Phase 8: Future** — Not on current roadmap. Will be re-evaluated when:
- User base hits 10K active wallets
- Network revenue stabilizes
- Banking partnerships established
- Regulatory framework clear

---

## 7. Pledge Lifecycle - Full Example

### Day 0: Registration

```
Farm: "OceanPool #3"
Owner: BTC address bc1qabc...
Hardware: 200 × Antminer S21
Hashrate: 50.4 PH/s
Required pledge: 0.00080 BTC (~$32)
```

### Day 1: Pledge Sent

```
1. GET /api/btc-mining/pledge/required/bc1qabc...
   → Returns: pool_address = bc1qthronoschain_pool...
            required_pledge_satoshis = 80000

2. Farm sends 80,000 sats to pool_address
   → BTC TX: abc123def456...

3. POST /api/btc-mining/pledge/confirm
   → Confirms TX on-chain
   → Status: ACTIVE
```

### Day 1-30: Mining & Heat Proofs

```
Daily Operation:
- BTC mined: 0.00134 BTC/day = 134K satoshis
- Heat proofs: 1-2 per day
- Fee per proof: 670 satoshis (0.5%)

Total Month 1:
- BTC earned: 0.0403 BTC ($1,612)
- Fees paid: 20,100 satoshis ($8)
- Pool contribution: 100,100 satoshis (pledge + fees)
- THR bonuses received: 4,140 THR ($16,560)

Net Month 1 Revenue: $1,612 + $16,560 - $8 = $18,164
```

### Year 1: Pool Growth

```
Farm continues mining for 12 months:
- Total BTC mined: 0.4836 BTC (~$19,344)
- Total fees paid: 241,200 satoshis (~$96.50)
- Total pledge active: 80,000 sats (still locked)
- Total contribution to pool: 321,200 sats (~$128.50)

Farm's earnings:
- BTC: $19,344
- THR: $198,720 (heat bonuses)
- Total: $218,064
- Cost as % of revenue: 0.05%
```

---

## 8. Pool Operations Schedule

### Hourly Operations

- Monitor pool balance changes
- Process incoming pledges
- Update pool status endpoint

### Daily Operations

- Collect pending fees from active farms
- Process THR bonus settlements
- Update reputation scores
- Generate compliance reports

### Weekly Operations

- Reconcile pool with chain transactions
- Audit fee collection accuracy
- Review fraud patterns
- Adjust reserves if needed

### Monthly Operations

- Evaluate Ether.fi conversion thresholds
- Process fiat conversions (if triggered)
- Publish transparency report
- Review pool allocation percentages

### Quarterly Operations

- Major audit (third-party)
- Adjust fee/pledge ratios if needed
- Review regulatory compliance
- Strategic planning for Phase 7.2/8

---

## 9. Risk Mitigation

### Pool Risks

| Risk | Mitigation |
|------|-----------|
| Pool insolvency | Maintain 20% reserve; cap payouts |
| BTC volatility | Convert to USDC at threshold |
| Fraud claims | 3-strike ban; pledge seizure |
| Settlement delays | Pre-allocate before THR mint |
| Liquidity crunch | Use Stellar bridge for emergency |

### Farm Risks

| Risk | Mitigation |
|------|-----------|
| Pool can't pay out | Visible balances via API |
| Pledge loss | Only if 3+ fraud violations |
| THR price drop | BTC earnings unchanged |
| Operational failure | Reputation/insurance partnerships |

---

## 10. API Reference

### Pledge Management

```
GET /api/btc-mining/pledge/required/<btc_address>
→ Returns required pledge amount and pool address

POST /api/btc-mining/pledge/confirm
→ Confirms pledge transaction
```

### Fee Management

```
POST /api/btc-mining/fee/collect
→ Collects fee from farm's heat proof
```

### Pool Status

```
GET /api/btc-mining/network-pool
→ Full pool status with allocation breakdown
```

---

## Summary

The BTC pledge + network pool system creates a **sustainable cross-chain economic model**:

✅ **Pledges** demonstrate commitment without burdening farms  
✅ **Fees** generate sustainable revenue for the network  
✅ **Pool** backs THR bonuses with real BTC  
✅ **Ether.fi** enables future fiat conversion at scale  
✅ **Visa Card** is a future option, not a current dependency  

Mining stays profitable. Network builds reserves. Future fiat conversion happens at scale. All without coupling current operations to a future-state product.

---

**Created:** May 18, 2026  
**Status:** ✅ Implementation complete - ready for staging  
**Next:** Pool address generation, multisig key ceremony, Ether.fi partnership discussion
