# Mining V1 Prep - Hooks & Eligibility Framework

This document outlines the hooks and eligibility framework for Mining V1, without implementing full mining logic yet.

## Current State (Wallet V1 Ready)

- ✅ Centralized signing with canonical_v1_address
- ✅ Public key validation and normalization
- ✅ Binding support (signer address ≠ canonical wallet)
- ✅ Session management (15 min unlock duration)
- ✅ Recovery Kit restore
- ✅ Digital Legacy integration

## Mining V1 Hooks (Ready for Implementation)

### 1. Miner Kit Availability

**Endpoint: `/api/mining/kit/status`**
```python
@app.route("/api/mining/kit/status", methods=["GET"])
def api_mining_kit_status():
    """
    Check if user is eligible for Miner Kit.
    
    Eligibility criteria:
    - Wallet V1 activated (canonical_v1_address exists)
    - Pledge confirmed (legacy → V1 migration complete)
    - No restrictions (account not frozen/banned)
    
    Returns:
    {
        "eligible": true,
        "canonical_v1_address": "THR...",
        "miner_kit_available": true,
        "kit_download_url": "...",
        "worker_format": "<canonical_v1_address>.<worker_name>",
        "config": {
            "pool_host": "stratum.thronoschain.org",
            "pool_port": 3333,
            "difficulty": 4
        }
    }
    """
```

### 2. Worker Registration

**Format: `<canonical_v1_address>.<worker_name>`**

Examples:
- `THR1234567890ABCDEF.worker1`
- `THR1234567890ABCDEF.rig_main`
- `THR1234567890ABCDEF.test` (testnet)

**Optional: Referral Code**
- Format: `<canonical_v1_address>.<worker>@<referrer_canonical>`
- Referrer gets % of mining rewards

### 3. Pool Payout Rules

**Always to canonical address**
- Even if mining with bound signer
- Binding validates permission to operate
- Payout can't be redirected to different address

**Signature Requirements for Claims**
- If canonical_v1_address has active binding:
  - Mining share claim must be signed by bound signer
  - Payout authorization requires canonical address signing
- If no binding:
  - Any claim by canonical owner accepted

### 4. Signed Mining Messages

**Mine Share Submission (future)**
```javascript
{
    "canonical_v1_address": "THR...",
    "action": "mining/submit_share",
    "public_key": "...",
    "signature": "...",
    "payload": {
        "worker": "THR...<worker>",
        "nonce": 12345,
        "mix_hash": "0x...",
        "timestamp": "2026-06-05T...",
        "block_number": 999,
        "difficulty": 4
    }
}
```

**Payout Claim (future)**
```javascript
{
    "canonical_v1_address": "THR...",
    "action": "mining/claim_payout",
    "public_key": "...",
    "signature": "...",
    "payload": {
        "total_shares": 1000,
        "period": "2026-06-01T00:00Z/2026-06-05T00:00Z",
        "expected_payout": 125.5
    }
}
```

## Pledge-to-Mining Flow

```
1. User on /pledge → creates THR address
2. Confirm pledge → migration to Wallet V1
3. Create signing key → canonical_v1_address + bound signer
4. Download Recovery Kit
5. Next page: "Setup Miner" button
   ↓
6. GET /api/mining/kit/status
   → Check eligible
   → Show "Download Miner Kit" button
   → Provide pool config & worker format
7. User downloads miner executable
   → Embeds canonical_v1_address
   → Prompts for worker name
   → Writes config.json
8. User starts miner
   → Connects to stratum pool
   → Submits shares with canonical_v1_address.<worker>
9. Pool credits shares to canonical address
10. User claims payout (signed by canonical or bound signer)
```

## Data Structure: Pledge-Verified Mining Status

**New field in pledge confirmation record:**
```python
{
    "legacy_address": "THR...",
    "canonical_v1_address": "THR...",
    "migration_status": "complete",
    "mining_eligible": true,
    "mining_started": false,  # First worker registered?
    "workers_registered": [],  # List of registered workers
    "current_binding": {
        "canonical_v1_address": "THR...",
        "signer_address": "THR...",
        "public_key_hash": "sha256(...)",
        "active_until": "2026-12-31T23:59Z"
    }
}
```

## Implementation Checklist (Not Done Today)

- [ ] /api/mining/kit/status endpoint
- [ ] GET /api/mining/workers (list worker status)
- [ ] POST /api/mining/share (stratum share submission)
- [ ] POST /api/mining/payout/claim (claim mining rewards)
- [ ] Stratum pool integration
- [ ] Miner kit download package
- [ ] Worker registration form in UI
- [ ] Mining dashboard (earnings, shares, workers)
- [ ] Binding enforcement for mining claims
- [ ] Referral reward distribution

## Notes

- No changes to PoW consensus algorithm
- No changes to block mining rules
- Pure auth/signing layer on top of existing mining
- Pool integration can be external (not in Thronos core)
- Miner kit is standalone executable (auto-signs with local key)

## References

- Wallet V1 Core: PR #602
- Signed Requests: PR #606, #607, #608
- Session Management: PR #606 (updated)
- Digital Legacy: PR #604
