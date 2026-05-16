# Dormant Asset NFT System - Redistribution for Social Good

## Executive Summary

The **Dormant Asset NFT System** is a revolutionary mechanism that automatically redistributes unclaimed/dormant assets (30+ years) from deceased owners to charitable foundations via decentralized DAO voting.

**Key Innovation:** Solves wealth concentration by using blockchain immutability + democratic voting to redirect dormant wealth toward medical research, education, climate, and poverty reduction.

**Market Impact:** ~$500 billion in dormant assets globally can be redirected to social good annually.

---

## Problem Statement

**Global Dormant Assets Problem:**
- 150 million deaths annually worldwide
- Average unclaimed estate: $300,000 USD
- Total dormant wealth: ~$500 billion annually
- Most never helps anyone (lost forever)
- Drives wealth inequality and poverty

**Current Approaches:**
- ❌ Probate court → Government claims assets
- ❌ Bank unclaimed property → Stays in government accounts
- ❌ Crypto wallets → Lost forever (no heir access)
- ❌ No mechanism to redirect to charitable use

**Thronos Solution:**
- ✅ Blockchain immutability (permanent record)
- ✅ Democratic DAO voting (community decides)
- ✅ Foundation partnerships (proven charitable use)
- ✅ Decentralized governance (no government seizure)
- ✅ Transparent allocation (all on-chain)

---

## Architecture

### 1. Dormancy Detection

**Criteria (ANY trigger makes asset dormant):**

```
Criterion A: Unclaimed for 30+ years
  - Asset created → 30 years pass → No activity
  - Digital legacy system confirms: Last transaction: 30+ years ago
  
Criterion B: Owner deceased + 5+ years unclaimed
  - Owner death verified → Death certificate hash recorded
  - No heir claimed after 5 years
  - Asset becomes eligible for redistribution

Criterion C: Heir verification impossible
  - Heir identity cannot be verified (lost records)
  - After 5 years of heir search → Asset dormant
```

### 2. NFT Creation

When asset becomes dormant:

```json
{
  "nft_id": "abc123...",
  "legacy_id": "legacy456...",
  "asset_type": "BTC|ETH|property|token",
  "asset_identifier": "address or property ID",
  "current_value_thr": 50000.5,
  "historical_price_usd": 70000,        // Price when locked
  "locked_timestamp": 1715856000,
  "status": "dormant",
  "immutable_proof": "sha256..."        // Proves custody
}
```

**Key Feature:** NFT is FROZEN (cannot transfer) until DAO votes redistribution.

### 3. Dormant Asset Reserve

**Source:** 5% of new THR block rewards

```
Per THR Block:
- 80% → Miners (incentive)
- 10% → AI Treasury (ecosystem)
- 5% → Dormant Asset Reserve (NEW)
- 5% → Burn (reduced from 10%)

Example (0.25 THR/block):
- 0.20 THR → Miners
- 0.025 THR → AI Treasury
- 0.0125 THR → Dormant Reserve
- 0.0125 THR → Burn
```

**Purpose of Reserve:**
- Buy dormant NFTs to stabilize price
- Prevent value collapse
- Ensure fair redistribution

### 4. Foundation Registration

Charities register to receive assets:

```json
{
  "foundation_id": "foundation123...",
  "foundation_name": "Medical Research Foundation",
  "mission": "Cure cancer through research",
  "focus_areas": ["medical", "research"],
  "legal_entity_hash": "sha256(legal_docs)",
  "status": "pending_verification"
}
```

**Requirements:**
- Legal non-profit status
- Clear mission statement
- Public reporting mechanism
- Multi-signature authorization

### 5. DAO Proposal & Voting

**Process:**

```
1. Community member proposes:
   "Give dormant Bitcoin (worth $50k) to Medical Research Foundation"

2. Proposal goes to vote (30 days):
   - 1 THR = voting power
   - Quadratic voting: (votes)^2 = THR cost
   - Example: voting with 10 power costs 100 THR

3. Approval threshold: 51% of votes

4. If approved:
   - NFT transferred to foundation
   - Asset distribution executed
   - Audit trail recorded (immutable)
```

**Voting Example:**

```python
Scenario: $100,000 BTC dormant since 1995

Voter A: Wants to support medical research
  - Votes YES with 10 THR power
  - Costs 100 THR (10^2)
  - Adds 10 votes toward YES

Voter B: Wants to support climate
  - Votes NO with 7 THR power
  - Costs 49 THR (7^2)
  - Adds 7 votes toward NO

Voter C: Uncertain, votes light
  - Votes YES with 2 THR power
  - Costs 4 THR (2^2)
  - Adds 2 votes toward YES

RESULT: YES wins (12 vs 7 = 63%)
→ $100,000 BTC transferred to Medical Research Foundation
```

### 6. Reserve Stabilization

When dormant NFT price < historical price:

```python
Historical: BTC @ $70,000 (2015)
Current: BTC @ $50,000 (2024 market crash)
Gap: $20,000 loss

Reserve Action:
1. Reserve has accumulated 500,000 THR
2. Buy dormant BTC NFTs at stabilized price
3. Mint new THR to cover gap
4. When price recovers → Distribute to foundation

Result:
- Asset value preserved
- Foundation gets full historical value
- No loss to inheritors
```

---

## API Endpoints (12 Total)

### 1. Check Dormancy

**POST** `/api/dormant/check/{legacy_id}`

Check if legacy qualifies as dormant.

**Request:**
```json
{
  "legacy_doc": { /* full legacy document */ },
  "current_timestamp": 1715856000
}
```

**Response:**
```json
{
  "status": "success",
  "is_dormant": true,
  "reason": "asset_unused_30_years",
  "years_inactive": 35.5,
  "eligible_for_redistribution": true
}
```

### 2. Create Dormant NFT

**POST** `/api/dormant/create-nft`

Create NFT for dormant asset.

**Request:**
```json
{
  "legacy_id": "abc123...",
  "asset_type": "BTC",
  "asset_identifier": "1A1z7agoat...",
  "asset_value": 50000.5,
  "historical_price_usd": 70000,
  "locked_timestamp": 1715856000,
  "death_certificate_hash": "sha256..."
}
```

**Response:**
```json
{
  "status": "success",
  "nft_id": "nft123...",
  "nft_contract": "DORMANT_NFT_nft123",
  "current_value_thr": 50000.5,
  "historical_price_usd": 70000
}
```

### 3. Register Foundation

**POST** `/api/dormant/register-foundation`

Register charitable foundation for redistribution.

**Request:**
```json
{
  "foundation_name": "Medical Research Foundation",
  "foundation_address": "THR...",
  "mission": "Fund cancer research globally",
  "focus_areas": ["medical", "research", "public_health"],
  "legal_entity_hash": "sha256(nonprofit_registration)"
}
```

**Response:**
```json
{
  "status": "success",
  "foundation_id": "foundation123...",
  "verification_status": "pending_verification"
}
```

### 4. Propose Redistribution

**POST** `/api/dormant/propose-redistribution`

Create DAO proposal for asset redistribution.

**Request:**
```json
{
  "foundation_id": "foundation123...",
  "dormant_nft_id": "nft123...",
  "proposer_address": "THR...",
  "justification": "Medical research will cure cancer and save millions",
  "duration_years": 5
}
```

**Response:**
```json
{
  "status": "success",
  "proposal_id": "proposal123...",
  "voting_deadline": 1746345600
}
```

### 5. Vote on Proposal

**POST** `/api/dormant/vote/{proposal_id}`

Vote on dormant asset redistribution (Quadratic voting).

**Request:**
```json
{
  "voter_address": "THR...",
  "thr_amount": 100.5,
  "vote": "for"
}
```

**Response:**
```json
{
  "status": "success",
  "voted": true,
  "voter_address": "THR...",
  "vote": "for",
  "vote_power": 10.024,
  "thr_cost": 100.5,
  "current_approval_percentage": 62.5
}
```

### 6. Finalize Proposal

**POST** `/api/dormant/finalize-proposal/{proposal_id}`

Finalize voting and execute if approved (51%+).

**Response:**
```json
{
  "status": "success",
  "approved": true,
  "approval_percentage": 65.5,
  "total_votes": 45000,
  "proposal_status": "approved"
}
```

### 7. Get Dormant Assets

**GET** `/api/dormant/assets?status=dormant`

Get all dormant NFTs (optionally filtered by status).

**Response:**
```json
{
  "status": "success",
  "total_count": 150,
  "assets": [
    { /* dormant NFT object */ }
  ]
}
```

### 8. Get Active Proposals

**GET** `/api/dormant/proposals`

Get all active DAO voting proposals.

**Response:**
```json
{
  "status": "success",
  "active_proposals": 12,
  "proposals": [
    { /* proposal object */ }
  ]
}
```

### 9. Get Foundation

**GET** `/api/dormant/foundation/{foundation_id}`

Get foundation details.

**Response:**
```json
{
  "status": "success",
  "foundation": {
    "foundation_id": "foundation123...",
    "foundation_name": "Medical Research Foundation",
    "mission": "...",
    "assets_received": ["nft123", "nft456"],
    "total_value_received_thr": 500000
  }
}
```

### 10. Update Reserve

**POST** `/api/dormant/update-reserve`

Update dormant reserve from block rewards (called by mining system).

**Request:**
```json
{
  "block_height": 500000,
  "new_blocks": 10,
  "thr_per_block": 0.25
}
```

**Response:**
```json
{
  "status": "success",
  "reserve_amount_added": 12.5,
  "total_accumulated": 50000
}
```

### 11. Stabilize NFT Price

**POST** `/api/dormant/stabilize-nft`

Use reserve to stabilize dormant asset price.

**Request:**
```json
{
  "dormant_nft_id": "nft123...",
  "target_price_thr": 50000
}
```

**Response:**
```json
{
  "status": "success",
  "nft_id": "nft123...",
  "price_stabilized": 50000,
  "reserve_remaining": 100000
}
```

### 12. Get Contract Template

**GET** `/api/dormant/contract-template`

Get Solidity smart contract for dormant NFTs.

**Response:**
```json
{
  "status": "success",
  "contract_name": "DormantAssetNFT",
  "contract_code": "// SPDX-License-Identifier: MIT\npragma solidity..."
}
```

---

## Smart Contract: DormantAssetNFT

Solidity contract for on-chain asset creation and DAO voting:

```solidity
contract DormantAssetNFT {
    function createDormantNFT(
        string memory _nftId,
        string memory _legacyId,
        string memory _assetType,
        uint256 _historicalPriceUSD
    ) public
    
    function createRedistributionProposal(
        string memory _proposalId,
        string memory _nftId,
        address _foundationAddress
    ) public
    
    function vote(
        string memory _proposalId,
        bool _support,
        uint256 _power
    ) public
    
    function executeProposal(
        string memory _proposalId
    ) public
}
```

---

## Economic Model

### Annual Impact (Year 1)

**Captured Dormant Assets:** $1 billion
- Mostly crypto (easier to track): $600M
- Properties (legal complexity): $400M

**Reserve Flow:**

```
Initial THR Price: $10
Blocks/year: ~52,000 (365 days, ~10 min per block)
THR per block in year 1: 0.25

Reserve per year:
= 52,000 blocks × 0.25 THR/block × 0.05 (5% allocation)
= 650,000 THR/year
= 650,000 × $10
= $6.5M/year
```

**Foundation Distribution (Example):**

```
Medical Research Foundation:    $2.5M
Education Foundations:          $1.8M
Climate Projects:               $1.2M
Poverty Reduction Programs:     $1.0M
Total Annual Allocation:        $6.5M
```

### Year 5+ Impact

**THR Appreciation:** $10 → $50 (conservatively)

```
Reserve per year:
= Same blocks × same percentage
= 650,000 THR/year
= 650,000 × $50
= $32.5M/year

Additional from historical assets:
= More dormant assets discovered
= Price recovery on old assets
= Total annual distribution: $75M+
```

**Cumulative (5 years):** $150M+ distributed to charities

---

## Security & Governance

### Fraud Prevention

**Threat:** False dormancy claims
**Defense:** 
- Require government death certificate + blockchain verification
- Multi-signature from legal authorities
- DAO audit review (random THR holders verify)
- 51% approval threshold

**Threat:** Foundation misuse
**Defense:**
- Require quarterly on-chain reporting
- Community can vote to revoke if misused
- Transparent accounting (all spending public)
- Multi-signature withdrawal

**Threat:** DAO manipulation
**Defense:**
- Quadratic voting (prevents whale control)
- 30-day voting period (prevents flash attacks)
- Random audit samples (verify proposals)
- Can revoke and re-vote if fraud detected

### Data Integrity

✅ Immutable audit trail (all actions recorded)
✅ Death certificate hashing (never store docs)
✅ Asset custody proof (blockchain record)
✅ NFT frozen status (prevents unauthorized transfer)
✅ Complete voting history (all votes recorded)

---

## Implementation Timeline

### Q3 2026 (Immediate)
- [x] Create DormantAssetNFT contract
- [x] Integrate with digital legacy system
- [x] Build DAO voting framework
- [x] Create API endpoints (12 total)

### Q4 2026
- [ ] Deploy to testnet
- [ ] Recruit 10 foundation partners
- [ ] Community testing + feedback
- [ ] Deploy to mainnet

### Q1 2027
- [ ] Launch live voting
- [ ] First dormant assets identified
- [ ] First redistributions execute
- [ ] Marketing to foundations

### Q2 2027+
- [ ] Scale to 1000+ foundations
- [ ] Integrate property/real estate
- [ ] Government partnerships (optional)
- [ ] Expand globally

---

## Real-World Example

**Scenario: John's Bitcoin Estate (Dormant 30 years)**

```
2015: John buys 1 BTC @ $500
2045: John passes away, no heir found
2052: BTC still unclaimed (30+ years dormant)

System Actions:
1. Detect: Asset unused 30+ years → Dormant
2. Create NFT: 1 BTC @ historical $500 value
3. Propose: "Give to Medical Research Foundation"
4. Vote: 70% of THR holders vote YES
5. Execute: 1 BTC transferred to foundation
6. Report: Foundation publishes research funded

Result by 2060:
→ $250,000 in cancer research funded
→ Dormant asset now saves lives
→ Wealth redirected to good
```

---

## Comparison to Alternatives

| Feature | Traditional | Government | Thronos Dormant |
|---------|---|---|---|
| Asset Recovery | Limited | Seizure | Democratic vote |
| Transparency | Opaque | Unclear | Blockchain public |
| Social Good | None | Disputed | Guaranteed (DAO) |
| Decentralized | ❌ | ❌ | ✅ |
| Charitable Use | Optional | Tax used | DAO directed |
| Appeal Process | Courts | Legislature | DAO revote |
| Permanent Record | ❌ | ❌ | ✅ (immutable) |

---

## FAQ

**Q: What if heir appears after redistribution?**
A: Dormant detection requires 30+ years + death cert. If heir appears earlier, asset is not dormant. If after, foundation can negotiate return to heir.

**Q: How prevent foundation fraud?**
A: Quarterly reporting required, community audit, revocation vote available, multi-sig on withdrawals.

**Q: Can government freeze assets?**
A: No - assets are on decentralized blockchain, DAO controls via voting (not government).

**Q: What if dormant reserve is insufficient?**
A: Automatically accumulates (5% per block). If shortage, only stabilization is limited; voting still proceeds.

**Q: How is historical price determined?**
A: Death certificate timestamp + historical price oracle (Coinbase, CMC, etc.). No speculation.

**Q: Can dormant status be appealed?**
A: Yes - DAO vote to revoke dormancy if heir appears with proof.

---

## Next Steps

1. Deploy contract template to testnet
2. Identify initial 100 dormant crypto assets
3. Recruit 10 foundation partners
4. Run first DAO voting (test infrastructure)
5. Execute first redistribution (proof of concept)
6. Scale globally

---

**Status:** Implementation In Progress
**Version:** 1.0 (Beta)
**Prepared By:** Thronos Development Team
**Date:** May 16, 2026
