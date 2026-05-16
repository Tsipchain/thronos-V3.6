# THRONOS BRIDGE & PLEDGE ECOSYSTEM - IMPLEMENTATION PLAN
**Timeline:** May 16 - June 15, 2026 (Phase 2-4)  
**Goal:** Autonomous, bidirectional, low-cost cross-chain transfers

---

## PHASE 1: IMMEDIATE FIXES (TODAY - May 16)

### 1.1 Pledge System Repair ⚡ CRITICAL
**Problem:** BTC confirmed → NOT converting to THR  
**Root Cause:** No user mapping in pledge_chain.json

**Fix:**
```
File: /btc_pledge_watcher.py
- Add default pledge_chain location: /data/pledge_chain.json
- Create file if missing
- Auto-sync from /static/pledge_chain.json on startup
```

**Testing:**
- Manually call `/api/btc_pledge` with correct user mapping
- Verify THR appears in wallet within 5 minutes

### 1.2 Bridge Coordinator Audit
**Files to review:**
- `bridge_coordinator.py` (550 lines) - multi-chain bridge logic
- `btc_bridge_withdrawal.py` - BTC withdrawal processing
- `btc_bridge_out.py` - outbound BTC operations

**Check for:**
- ✓ Confirmation counting (BTC requires 12)
- ✓ Fee calculation (0.25% standard, 0.5% volatile)
- ✓ Liquidity pool balance
- ✓ Error handling on failed conversions

---

## PHASE 2: BRIDGE AUTOMATION (May 17-24)

### 2.1 Create Bridge Watcher (analogous to BTC Pledge Watcher)
**File:** `bridge_monitor.py` (NEW)

```python
def watch_bridge_transactions():
    """
    Monitor bridge status every 5 minutes:
    1. Check all pending bridge transactions
    2. Verify confirmation counts
    3. Auto-process when ready
    4. Retry on failure (exponential backoff)
    """
    # Strategy: Queue-based, fire-and-forget
    # Never block on slow chains
```

**Supported Blockchains:**
- Bitcoin (BTC) - 12 confirmations
- Ethereum (ETH) - 30 confirmations
- Solana (SOL) - 30 confirmations
- XRP Ledger - 1 confirmation
- Polkadot (DOT) - 15 confirmations
- Cosmos (ATOM) - 1 confirmation

### 2.2 Bi-Directional Bridge Endpoints
**NEW Endpoints:**

```
POST /api/bridge/btc-to-thr      ← 0.1 BTC → ~3,333 THR (after fees)
POST /api/bridge/thr-to-btc      ← 3,333 THR → 0.099 BTC (after fees)
GET  /api/bridge/status          ← Check pending transfers
GET  /api/bridge/rates           ← Current exchange rates
```

### 2.3 Auto-Processing Queue
**Architecture:**
```
Incoming TX → Confirmation Watcher → Fee Calc → Liquidity Check → 
Execute → Broadcast → Update Ledger → Webhook notify user
```

**Safety:**
- Never execute if liquidity < 105% of amount
- Timeout: 7 days max per transaction
- Exponential backoff on failures (5s, 10s, 30s, 1m, 5m, 30m)

---

## PHASE 3: STELLAR INTEGRATION (May 25-31)

### 3.1 Stellar Payment Channel
**File:** `stellar_bridge.py` (NEW - 400 lines)

**Problem it solves:**
- BTC network fees too high for small transfers
- Solution: Use Stellar network as low-cost layer

**How it works:**
```
User wants to send 0.001 BTC (~$50) to friend:
1. BTC Network: $2-5 fee (4-10% of amount) ❌ EXPENSIVE
2. Stellar Network: $0.00001 fee (~$0) ✅ CHEAP

Flow:
BTC (0.001) → Bridge → Convert to USDC on Stellar → 
Send via Stellar (fee: $0.00001) → Convert back to BTC → 
Recipient gets 0.001 BTC with only $0.00001 fee
```

**Stellar Features Needed:**
- Payment channels for instant settlement
- Federation for address resolution (bob@thronos.org)
- Anchors for BTC/THR conversions
- Liquidity pool integration

### 3.2 Stellar Anchor Setup
**File:** `/stellar/anchor_server.py` (NEW)

```
Configure:
- Asset: THR-token (issued on Stellar)
- Asset: USDC (for bridge liquidity)
- Deposit: Accept BTC → issue THR
- Withdrawal: Accept THR → send BTC
```

### 3.3 Federation Protocol
**Endpoint:** `/.well-known/stellar.toml`

```
Enables addresses like:
- user@api.thronoschain.org
- user@ro.api.thronoschain.org  (testnet)
- user@vault.thronoschain.org   (treasury)
```

---

## PHASE 4: AUTONOMOUS NODES (June 1-15)

### 4.1 Node Autonomy Architecture
**Current State:**
- Master node: Processes everything (bottleneck)
- Replica nodes: Read-only (useless for bridge)

**Target State:**
```
Master Node (api.thronoschain.org)
├── Process core transactions
├── Maintain chain state
├── Validate blocks

Bridge Node (bridge.thronoschain.org) [NEW]
├── Monitor all bridge transactions
├── Auto-execute when conditions met
├── Maintain liquidity pools

Stellar Node (stellar.thronoschain.org) [NEW]
├── Run Stellar validator
├── Process Stellar payments
├── Manage anchor conversions

Replica Nodes (ro.api, etc.)
├── Read-only copies (for load balancing)
└── Mirror state from master
```

### 4.2 Node Permissions
**Each node has independent authority:**

```
Bridge Node:
- Can access bridge_coordinator endpoints
- Can call /api/bridge/execute
- Cannot touch ledger/chain (read-only)
- Broadcasts execution to all nodes

Stellar Node:
- Can issue/burn THR-token
- Can process Stellar transactions
- Can manage anchor conversions
- Cannot touch mainnet chain

Replica Nodes:
- Read-only access to all data
- Can serve /api/* queries
- Cannot write anything
```

### 4.3 Cross-Node Communication
**Protocol:** Gossip + Event Streaming

```
Node1 (Master): "New block 123"
    ↓ (broadcast to all)
Node2 (Bridge): Checks if any bridge txs affected
Node3 (Stellar): Checks if any Stellar txs affected
Node4 (Replica): Updates local copy
    ↓ All verify hash
All → Consensus reached
```

**Implementation:**
- Use existing gossip layer (if present)
- Add event topics: "block", "bridge", "stellar", "pledge"
- Async processing (no blocking)

---

## PHASE 5: TESTNET DEPLOYMENT (June 1-15)

### 5.1 ro.api becomes TESTNET
**Environment:**
```
NODE_ROLE=testnet
TESTNET_MODE=1
CHAIN_FILE=/data/testnet/chain.json
STELLAR_NETWORK=testnet
BTC_NETWORK=testnet
```

**Features:**
- Instant blocks (no PoW)
- Free faucet: `/api/testnet/mint` (get 1000 THR)
- Stellar testnet integration
- Bridge test mode (no real BTC movement)

### 5.2 Integration Testing
```
Test Suite (test_bridge_stellar.py):

✓ BTC → THR conversion
✓ THR → BTC conversion
✓ Stellar payment processing
✓ Low-cost transfer via Stellar
✓ Bridge failure recovery
✓ Node autonomy (bridge executes without master)
✓ Stellar federation (address resolution)
✓ Multi-hop transfers (BTC → Stellar → ETH)
```

---

## FILES TO CREATE/MODIFY

### NEW FILES (4)
- `stellar_bridge.py` (400 lines)
- `bridge_monitor.py` (350 lines)
- `stellar/anchor_server.py` (500 lines)
- `test_bridge_stellar.py` (600 lines)

### MODIFIED FILES (5)
- `btc_pledge_watcher.py` - add file creation logic
- `bridge_coordinator.py` - add auto-execution
- `server.py` - add new endpoints + scheduler jobs
- `gunicorn_config.py` - increase timeout for bridge ops
- `.env.example` - add Stellar config vars

### DELETED/DEPRECATED (0)
- Nothing deleted - backward compatible

---

## TIMELINE

| Date | Phase | Deliverable |
|------|-------|-------------|
| May 16 | 1.1 | Pledge system fixed ✅ |
| May 17-24 | 2.0 | Bridge automation working |
| May 25-31 | 3.0 | Stellar integration complete |
| Jun 1-15 | 4.0 | Autonomous nodes + testnet |
| Aug 15 | Live | Mainnet activation |

---

## SUCCESS CRITERIA

- ✅ Friend's BTC converts to THR within 5 minutes
- ✅ BTC↔THR bridge works bidirectionally
- ✅ Small transfers (<0.01 BTC) use Stellar layer (fee: $0.00001)
- ✅ Bridge operations fully autonomous (no manual intervention)
- ✅ Nodes can operate independently with consensus
- ✅ Stellar federation enabled (user@thronos.org addresses)
- ✅ Testnet allows developers to test everything
- ✅ Zero data loss, zero transaction failures (with retry)

---

## RISKS & MITIGATIONS

| Risk | Mitigation |
|------|-----------|
| Stellar token security | Use Thronos as issuer only; anchor ensures reserves |
| Bridge liquidity shortage | Maintain 110% collateral; refuse if insufficient |
| Node consensus failure | Gossip protocol + simple majority; fallback to master |
| Fee spam (Stellar) | Rate limiting on /api/bridge endpoints |
| Cross-chain atomicity | Use timelocks; expire incomplete transactions after 7 days |

---

## SUCCESS INDICATORS (Go/No-Go)

### Go Criteria
- [ ] Pledge: 0.00041192 BTC → ~13.73 THR (within 5 min)
- [ ] Bridge: THR → 0.000391 BTC (within 10 min, after fees)
- [ ] Stellar: Can send 0.001 BTC via Stellar for $0 fee
- [ ] Autonomous: Bridge executes without master node interaction
- [ ] Testnet: Developers can test all 4 features on ro.api

### No-Go Criteria (Stop & Replan)
- Any wallet balance loss
- Any confirmation count mismatch
- Any node consensus disagreement
- Stellar anchor cannot guarantee reserves

---

**STATUS:** Ready to implement  
**APPROVAL NEEDED:** User confirmation

