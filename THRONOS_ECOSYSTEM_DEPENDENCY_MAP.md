# ThronosChain Ecosystem Dependency Map

**Document Version**: 1.0  
**Generated**: 2026-05-29  
**Scope**: Main branch + PR #526 implications  
**Purpose**: Visual and textual mapping of subsystem interdependencies, data flows, and mutation chains

---

## Executive Summary

ThronosChain operates as an **interconnected ecosystem** of 12 major subsystems sharing a common JSON-based state store. This document maps:

1. **Data dependencies** — Which subsystems read/write which files
2. **Mutation chains** — How changes in one subsystem ripple to others
3. **Critical paths** — The highest-risk transaction flows
4. **PR #526 impact** — How Wallet V1 migration integrates with existing subsystems

---

## Part 1: Subsystem Overview & Core Interdependencies

### Subsystem Hierarchy (by coupling)
┌─────────────────────────────────────────────────────────────────┐
│ CORE LEDGER SYSTEM │
│ (ledger.json center) │
└─────────────────────────────────────────────────────────────────┘
▲
┌──────────────────┼──────────────────┐
│ │ │
┌────▼─────┐ ┌─────▼──────┐ ┌─────▼──────┐
│ MINING │ │ WALLET │ │ MUSIC │
│ (THR Gen) │ │ (Transfer)│ │ (Royalty) │
└──────────┘ └────────────┘ └────────────┘
│ │ │
│ ┌───┼───┐ │
│ │ │ │ │
┌────▼────┐ ┌──────▼───┼───▼────┐ ┌─────▼──────┐
│ POOLS │ │ TOKENS │ │ L2E │
│ (Swap) │ │ (Creation, Mint) │ │ (Courses) │
└─────────┘ └──────────────────┘ └────────────┘
│ │ │
└──────────────────┼──────────────────┘
│
┌────────▼────────┐
│ WALLET V1 │ ← PR #526 NEW
│ MIGRATION │
└─────────────────┘

### Data Store Centralization
**All subsystems converge on 6 core JSON files:**
┌──────────────────────────────────────────┐
│ LEDGER.JSON (Master) │
│ Address → Balance (all subsystems use) │
├──────────────────────────────────────────┤
│ Mining: writes to ledger (THR creation) │
│ Wallet: reads/writes (transfers) │
│ Music: reads/writes (tips) │
│ Pools: reads/writes (swaps) │
│ Fiat: writes (deposits) │
│ L2E: reads (rewards) │
│ Migration: reads (consolidation) │
└──────────────────────────────────────────┘

---
## Part 2: Critical Data Flows
### Flow 1: Mining → Ledger → Distribution
Mining Submission
│
▼
POST /api/mining/submit {difficulty, nonce, block_data}
│
├─→ Validate PoW
├─→ Load ledger.json
├─→ Calculate mining reward (e.g., 10 THR)
├─→ Update ledger:
│ - mining_wallet += 10 THR
│ - BURN_ADDRESS += fee_burned
│
├─→ Save atomically
│
▼
Block Distributed to Network
│
├─→ Broadcast to peers (async)
│
├─→ Music subsystem: Artist royalty from block rewards
├─→ L2E subsystem: Course incentives distributed
└─→ Wallet subsystem: User balance available

Risk: PoW validation bypass → inflation
Safeguard: Difficulty verification, nonce uniqueness
Mutation: ledger.json, chain.json

### Flow 2: User Transfer (Wallet → Ledger → Other)
User Initiates Transfer
│
▼
POST /api/wallet/send {from, to, amount, signature}
│
├─→ Verify wallet signature (requires wallet_v1_migration module)
├─→ Load ledger.json
├─→ Check balance: sender.balance ≥ amount + fee
│
├─→ Update ledger:
│ - ledger[sender] -= (amount + fee)
│ - ledger[recipient] += amount
│ - ledger[BURN_ADDRESS] += fee
│
├─→ Record transaction in chain.json
├─→ Save both files atomically
│
▼
Transfer Finalized
│
├─→ Music subsystem: If recipient is artist, trigger tip tracking
├─→ Bridge subsystem: If cross-chain, trigger bridge event
└─→ Wallet V1: If migration address, log in migration events

Risk: Signature bypass → theft; insufficient balance check → negative balance
Safeguard: wallet_v1_migration signature verification, balance validation
Mutation: ledger.json, chain.json
Dependencies: wallet_v1_migration module (critical for legacy wallets)

### Flow 3: Liquidity Pool Swap (Pools → Ledger → Token Prices)
User Initiates Swap
│
▼
POST /api/v1/pools/swap {pool_id, token_in, amount_in, min_out}
│
├─→ Load pools.json
├─→ Find pool with (token_in, token_out)
├─→ Calculate swap amount (x*y = k formula)
│ ├─→ new_reserve_in = old + amount_in
│ └─→ amount_out = old_reserve_out - (k / new_reserve_in)
│
├─→ Check: amount_out ≥ min_out (slippage check)
├─→ Load ledger.json
├─→ Check balance: user.balance ≥ amount_in
│
├─→ Update ledger:
│ - user -= amount_in (send tokens to pool)
│ - user += amount_out (receive swapped tokens)
│
├─→ Update pools.json:
│ - pool.reserve_in += amount_in
│ - pool.reserve_out -= amount_out
│
├─→ Save both atomically
│
▼
Swap Finalized
│
├─→ Price feeds updated (token prices adjust)
├─→ Music subsystem: Royalties recalculated if denominated in swapped token
└─→ AI subsystem: Credit conversions affected

Risk: Impermanent loss; sandwich attack; slippage tolerance
Safeguard: Atomic update of both files, min_out check
Mutation: pools.json, ledger.json
Dependencies: Token price feeds

### Flow 4: Music Tip (Wallet → Ledger → Royalty)
User Sends Tip to Artist
│
▼
POST /api/music/tip {track_id, artist_address, amount}
│
├─→ Load ledger.json
├─→ Check user balance ≥ amount
│
├─→ Update ledger:
│ - user -= amount (send THR)
│ - artist += amount (receive THR)
│
├─→ Record tip in music session log
├─→ Save ledger.json
│
▼
Tip Finalized
│
├─→ Music subsystem: Track royalty totals updated
├─→ Dashboard subsystem: Artist earnings displayed
└─→ Wallet subsystem: Artist balance available for spending

Risk: Negative balance if user already spent; phantom tips
Safeguard: Balance check before tip
Mutation: ledger.json
Dependencies: Music session tracking

### Flow 5: L2E Course Reward Claim (Courses → L2E Ledger)
Student Completes Course
│
├─→ POST /api/v1/courses/<course_id>/complete
│
├─→ Verify course progress
├─→ Verify quiz completion
│
▼
Student Claims Reward
│
▼
POST /api/v1/courses/<course_id>/claim_reward
│
├─→ Load l2e_ledger.json
├─→ Calculate reward amount (e.g., 5 L2E tokens)
├─→ Check if reward already claimed
│
├─→ Update l2e_ledger:
│ - student.l2e_balance += reward_amount
│
├─→ Record claim in ledger
├─→ Save l2e_ledger.json
│
▼
Reward Finalized
│
├─→ L2E subsystem: Student can now convert L2E → THR via swap
└─→ Wallet subsystem: Eventually transferred to user's wallet

Risk: Double-claim if state not checked; reward inflation
Safeguard: Claim idempotency check
Mutation: l2e_ledger.json
Dependencies: Course completion tracking

### Flow 6: WALLET V1 MIGRATION - LP Share Consolidation (NEW - PR #526)
User Has Split V1 Wallets
│
├─→ Old legacy address: migrated to first_v1_wallet + current_v1_wallet
├─→ first_v1_wallet: has 50 shares in pool X
├─→ current_v1_wallet: has 0 shares in pool X
│
▼
Diagnostics Query
│
▼
GET /api/v1/wallet/v1-split-diagnostics?old_address=legacy&current_v1_address=current
│
├─→ Load ledger.json (balance check)
├─→ Load pools.json (LP position check)
├─→ Query tx_feed() for wallet_v1_migration events
│
├─→ Detect all first_v1_wallets from migration events
├─→ List their balances and LP positions
│
▼
Response Returned (Diagnostic Only)
│
└─→ User/admin sees migration recommendation

Risk: LOW (read-only)
Dependencies: tx_feed, ledger.json, pools.json
Mutation: NONE

### Flow 7: LP MIGRATION - Share Ownership Transfer (NEW - PR #526)
Admin Reviews Diagnostics
│
├─→ Sees: old_address has 100 shares across 3 pools
├─→ Sees: current_v1_address has 0 shares
│
▼
Admin Initiates Migration (Dry-Run First)
│
▼
POST /api/v1/wallet/liquidity-provider-migration
{
"old_address": "THRold...",
"new_v1_address": "THRnew...",
"dry_run": true,
"X-Admin-Secret": "..."
}
│
├─→ require_admin() check (verify admin auth)
├─→ CORE_MINER_WALLET_DO_NOT_BIND check
├─→ Load pools.json
│
├─→ Find all pools where old_address ∈ providers
├─→ Calculate: affected_pools = 3, total_shares = 100
│
├─→ Build proposal (dry-run output only)
│
▼
Dry-Run Response
{
"ok": true,
"dry_run": true,
"mutation_performed": false,
"affected_pools": [
{"pool_id": "pool_1", "user_shares": 50.0},
{"pool_id": "pool_2", "user_shares": 30.0},
{"pool_id": "pool_3", "user_shares": 20.0}
],
"proposal": "Migrate 100 shares to new_v1_address across 3 pools"
}
│
├─→ Admin reviews
├─→ Admin re-submits with dry_run=false (requires re-auth)
│
▼
Real Mutation Execution
│
├─→ require_admin() check again
├─→ Load pools.json again (fresh read)
│
├─→ For each affected pool:
│ ├─→ providers[new_v1_address] += providers[old_address]
│ ├─→ delete providers[old_address]
│ └─→ pool["providers"] = updated_providers
│
├─→ save_pools(pools) ← ATOMIC WRITE
│
▼
Mutation Finalized
{
"ok": true,
"dry_run": false,
"mutation_performed": true,
"status": "migrated",
"affected_pools": [...],
"total_pools_affected": 3
}
│
├─→ Swap subsystem: Liquidity positions now tied to new_v1_address
├─→ Wallet subsystem: LP earnings accrue to new_v1_address
└─→ Audit: Migration event logged in chain.json

Risk: CRITICAL (mutates pools.json)
Safeguard: Admin-gated, dry-run default, CORE wallet protected, atomic write
Mutation: pools.json ONLY (ledger unaffected)
Dependencies: admin_auth, core wallet check
Rollback: Manual restore from backup

---
## Part 3: Subsystem-by-Subsystem Dependency Matrix
### 3.1 Wallet Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | ledger.json |
| **Secondary Files** | chain.json (transaction history), pledge_chain.json (pledge records) |
| **Read Operations** | `GET /api/balance/<addr>`, `GET /api/wallet/history` |
| **Write Operations** | `POST /api/wallet/send`, `POST /api/wallet/activate` |
| **Dependencies** | wallet_v1_migration module (signature verification) |
| **Inverse Dependencies** | Mining (creates THR → ledger), Fiat Gateway (deposits → ledger), Music (tips → ledger) |
| **Mutation Risk** | CRITICAL (send endpoint has no amount cap) |
| **Safeguards** | Signature verification, balance check |
**Data Flow**:
User Input → Signature Verify (wallet_v1_migration)
→ Load ledger.json
→ Check balance
→ Update ledger atomically
→ Broadcast to peers

---
### 3.2 Mining Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | ledger.json (reward distribution), chain.json (block history) |
| **Read Operations** | `GET /api/mining/info`, `GET /api/mining/status` |
| **Write Operations** | `POST /api/mining/submit` (creates new THR) |
| **Dependencies** | None (standalone genesis) |
| **Inverse Dependencies** | Wallet (balance), Music (artist royalties), L2E (educational incentives) |
| **Mutation Risk** | CRITICAL (creates new supply) |
| **Safeguards** | PoW verification, difficulty check, nonce uniqueness |
**Inflation Model**:
Block reward = Base reward (e.g., 10 THR)
- Halving schedule applied
+ Transaction fees collected
- Percentage burned (fee_burned)
= Net new THR to miner wallet

---
### 3.3 Music Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | ledger.json (tip/royalty distribution) |
| **Secondary Files** | Session logs (GPS, play tracking) |
| **Read Operations** | `GET /api/music/tracks`, `GET /api/music/artist/<addr>` |
| **Write Operations** | `POST /api/music/tip`, `POST /api/music/play/<track_id>` |
| **Dependencies** | Wallet (user balance check), Session tracking |
| **Inverse Dependencies** | Wallet (artist earnings), Dashboard (royalty reporting) |
| **Mutation Risk** | MEDIUM (tips modify ledger; GPS tracking optional) |
| **Safeguards** | Balance check before tip, session logging for audit |
**Royalty Flow**:
Artist Uploads Track
→ Track ID assigned
→ Earnings reservoir created in session log

User Plays Track
→ Play event logged (timestamp, GPS, duration)
→ Royalty calculated (e.g., $0.01/stream)

User Tips Artist
→ Balance check: user.balance ≥ tip_amount
→ Ledger update: user -= tip, artist += tip
→ Tip event logged with track_id

Artist Collects Earnings
→ Sum of plays * rate + tips
→ Withdrawn to artist's wallet

---
### 3.4 Liquidity Pools & Swap Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | pools.json (reserve state), ledger.json (user balances) |
| **Read Operations** | `GET /api/v1/pools`, `GET /api/swap/quote` |
| **Write Operations** | `POST /api/v1/pools/swap`, `POST /api/v1/pools/add_liquidity`, `POST /api/v1/pools/remove_liquidity` |
| **Dependencies** | Token subsystem (token symbols), Wallet (user balance) |
| **Inverse Dependencies** | Price feeds, Swap quotes, Bridge (wrapped assets) |
| **Mutation Risk** | CRITICAL (impacts price discovery) |
| **Safeguards** | Slippage check (min_out), atomic ledger+pool updates |
**Swap Mechanics**:
Constant Product Formula: x * y = k

Pool State Before:
reserve_a = 1000 THR
reserve_b = 500 TOKENX
k = 500,000

User Swaps 10 THR for TOKENX:
new_reserve_a = 1000 + 10 = 1010
amount_out = 500 - (500,000 / 1010) = 500 - 495.05 = 4.95
new_reserve_b = 500 - 4.95 = 495.05

Check: 1010 * 495.05 = 500,000.5 ✓ (k verified)
Check: 4.95 ≥ min_out? (slippage check)

Update:
pool.reserve_a = 1010
pool.reserve_b = 495.05
user.balance[THR] -= 10
user.balance[TOKENX] += 4.95

---
### 3.5 Token Management Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | Token registry (in-memory or file) |
| **Secondary File** | ledger.json (token balances per holder) |
| **Read Operations** | `GET /api/tokens`, `GET /api/tokens/<symbol>/holders` |
| **Write Operations** | `POST /api/tokens/create`, `POST /api/tokens/<symbol>/mint`, `POST /api/tokens/<symbol>/burn` |
| **Dependencies** | None (standalone) |
| **Inverse Dependencies** | Swap (token pairs), Bridge (wrapped tokens) |
| **Mutation Risk** | HIGH (supply creation without bounds) |
| **Safeguards** | Admin gating on mint/burn, symbol validation |
**Token Creation Flow**:
POST /api/tokens/create {symbol, name, initial_supply, owner}
→ Create token registry entry
→ Allocate initial_supply to owner in ledger
→ Enable swapping if paired with another token

POST /api/tokens/THR/mint {amount, recipient}
→ Add amount to recipient's balance
→ Increase total_supply in token metadata
→ (DANGER: Can inflate supply if not controlled)

POST /api/tokens/THR/burn {amount, burner}
→ Subtract amount from burner's balance
→ Decrease total_supply
→ Send to BURN_ADDRESS for permanent removal

---
### 3.6 L2E Courses Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | l2e_ledger.json (student credit balances) |
| **Secondary File** | ai_credits_ledger.json (AI service credits) |
| **Read Operations** | `GET /api/v1/courses`, `GET /api/v1/l2e/balance/<addr>` |
| **Write Operations** | `POST /api/v1/courses/<course_id>/claim_reward`, `POST /api/v1/courses/<course_id>/enroll` |
| **Dependencies** | Course content management, AI interaction tracking |
| **Inverse Dependencies** | Wallet (eventual THR conversion), Swap (L2E→THR token pair) |
| **Mutation Risk** | MEDIUM (double-claim risk) |
| **Safeguards** | Claim idempotency check, course completion proof |
**L2E Earning Flow**:
Student Enrolls in Course
→ enrollment_record created
→ course_id + student_address tracked

Student Completes Lessons
→ progress_record updated
→ lesson_completion_events logged

Student Completes Quiz
→ quiz_response validated against answer_key
→ score calculated

Student Claims Reward (if eligible)
→ Check: course_progress == 100%
→ Check: quiz_score >= passing_threshold
→ Check: not already claimed (idempotency)

→ Update l2e_ledger:
student.l2e_balance += reward_amount (e.g., 5 L2E)

→ Log claim event
→ Return confirmation

Student Converts L2E → THR (via Swap)
→ Use /api/v1/pools/swap endpoint
→ Trade L2E for THR in liquidity pool
→ L2E removed from circulation
→ THR added to student wallet

---
### 3.7 Bridge & Cross-Chain Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | wbtc_ledger.json (wrapped Bitcoin state) |
| **Secondary File** | chain.json (bridge events) |
| **Read Operations** | `GET /api/bridge/data`, `GET /api/bridge/history/<addr>` |
| **Write Operations** | `POST /api/bridge/deposit`, `POST /api/bridge/burn`, `POST /api/bridge/withdraw` |
| **Dependencies** | External blockchain watchers (Bitcoin), external API calls |
| **Inverse Dependencies** | Swap (WBTC token pair), Wallet (user balances) |
| **Mutation Risk** | HIGH (external dependency risk) |
| **Safeguards** | External confirmation timeout, nonce tracking |
**Bridge Flow**:
User Deposits Bitcoin
→ POST /api/bridge/deposit {btc_address, amount}
→ Bridge creates deposit address
→ User sends BTC to deposit address
→ Watcher polls Bitcoin blockchain
→ Confirmation event received (6+ blocks)
→ WBTC minted to user's THR address in wbtc_ledger
→ User can swap WBTC for THR

User Burns WBTC
→ POST /api/bridge/burn {amount}
→ Update wbtc_ledger: user.wbtc -= amount
→ Create burn event in chain.json
→ Bridge monitors for burn confirmation
→ Release equivalent BTC to user's Bitcoin address

Risk: Orphaned burns if Bitcoin transaction fails
Safeguard: Confirmation polling, timeout handling

---
### 3.8 AI Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | ai_credits_ledger.json (credit balances) |
| **Secondary File** | ai_interaction_ledger.db (interaction history) |
| **Read Operations** | `GET /api/ai_credits`, `GET /api/ai/interactions` |
| **Write Operations** | `POST /api/ai/chat`, `POST /api/ai_purchase_pack` |
| **Dependencies** | LLM providers (Anthropic, OpenAI, Gemini), model registry |
| **Inverse Dependencies** | Wallet (credit purchases), Music (composer AI tools) |
| **Mutation Risk** | MEDIUM (credit deduction race condition) |
| **Safeguards** | Per-model token limits, rate limiting |
**AI Credit Flow**:
User Purchases AI Credits
→ POST /api/ai_purchase_pack {quantity, payment_method}
→ Process payment (Stripe, etc.)
→ Update ai_credits_ledger: user.credits += quantity
→ Log purchase in ledger

User Sends Chat Message
→ POST /api/ai/chat {session_id, message, model}
→ Deduct estimated tokens from user.credits
→ Call LLM provider (API request)
→ Receive response
→ Settle actual tokens used (adjust credit ledger)
→ Log interaction in ai_interaction_ledger.db

User Runs Out of Credits
→ POST /api/ai/chat fails with insufficient_credits
→ User must purchase more credits

---
### 3.9 IoT & Smart Devices Subsystem
| Aspect | Details |
|--------|---------|
| **Primary File** | device_registry.json (device metadata), readings.jsonl (sensor logs) |
| **Secondary File** | ledger.json (device rewards) |
| **Read Operations** | `GET /api/iot/readings`, `GET /api/iot/parking` |
| **Write Operations** | `POST /api/iot/register_device`, `POST /api/iot/push_reading` |
| **Dependencies** | GPS tracking, device authentication |
| **Inverse Dependencies** | Mining (heat rewards), Wallet (payouts) |
| **Mutation Risk** | LOW (primarily logging) |
| **Safeguards** | Device signature verification, timestamp validation |
---
### 3.10 Wallet V1 Migration Subsystem (NEW - PR #526)
| Aspect | Details |
|--------|---------|
| **Primary File** | ledger.json, pools.json (reads) |
| **Companion Module** | wallet_v1_migration.py (migration map) |
| **Read Operations** | `GET /api/v1/wallet/v1-split-diagnostics`, `GET /api/v1/wallet/thr-reconciliation` |
| **Write Operations** | `POST /api/v1/wallet/liquidity-provider-migration` (pools.json), `POST /api/v1/wallet/thr-reconciliation/repair` (ledger.json) |
| **Dependencies** | wallet_v1_migration module (migration proof), tx_feed() (migration events) |
| **Inverse Dependencies** | Wallet (legacy wallets), Swap (LP positions), Mining (miner consolidation) |
| **Mutation Risk** | CRITICAL (LP migration mutates pools.json) |
| **Safeguards** | Admin gating, dry-run default, CORE wallet check, migration proof requirement |
**Integration Points**:
Diagnostics Query
Reads: ledger.json (balances)
pools.json (LP positions)
tx_feed() (migration events)
Writes: NONE (read-only)
Risk: LOW
LP Migration (Dry-Run)
Reads: pools.json, admin_auth
Writes: NONE (proposal only)
Risk: LOW
LP Migration (Real Execution)
Reads: pools.json (fresh)
Writes: pools.json (share ownership transfer)
Mutation: Atomic (all-or-nothing)
Risk: CRITICAL
Consolidation Proposal
Reads: ledger.json, tx_feed() (migration proof)
Writes: NONE (proposal only)
Risk: HIGH (proposal without fund movement)
---
## Part 4: Critical Interaction Patterns
### Pattern 1: Balance Consistency Under Concurrent Operations
**Problem**: What happens if two swaps try to use the same user's balance simultaneously?
**Current Protection**:
```python
# In POST /api/v1/pools/swap:
ledger = load_json(LEDGER_FILE, {})  # Read at time T
if ledger[user] < amount_in:  # Check at time T
    return error
# At time T+Δ, another request might have already spent the balance
ledger[user] -= amount_in  # Write at time T+Δ might violate balance
# Atomic write minimizes window, but doesn't prevent the race
save_json(LEDGER_FILE, ledger)
Risk Level: MEDIUM (rare in practice, mitigated by single-threaded GIL)
Recommended Fix: Database transaction (ACID) or locking mechanism

Pattern 2: Pool Share Atomicity Under LP Migration
Problem: What if LP migration fails halfway through updating multiple pools?

# Current approach (PR #526):
pools = load_pools()
for pool in pools:
    if old_address in pool["providers"]:
        # Move shares
        pool["providers"][new_address] = ...
        del pool["providers"][old_address]

# If save fails after 2/3 pools updated → corrupted state
save_pools(pools)
Risk Level: MEDIUM (atomic write minimizes risk, but not zero)
Recommended Fix:

Write to temporary file
Verify atomic_write_json() uses fsync()
Pre-flight validation (test all pools before mutation)
Pattern 3: Cross-File Consistency (Ledger + Pools)
Problem: Swap updates both ledger.json and pools.json. What if one write succeeds and the other fails?

Ledger:     user.THR -= 10       (succeeds)
Pools:      pool.reserve += 10   (fails)
Result:     User loses 10 THR; pool unchanged (lost funds)
Risk Level: HIGH (not atomic across files)
Safeguard: atomic_write_json() helps, but doesn't span files
Recommended Fix: Single-file ledger with nested structure:

{
  "balances": {...},
  "pools": [...],
  "metadata": {...}
}
Pattern 4: PR #526 LP Migration Safety Under Concurrent Pool Operations
Scenario:

User swaps in pool X (updates reserves)
Admin migrates LP ownership for pool X simultaneously
Current Protection:

# LP Migration: Fresh load of pools.json
pools = load_pools()
for pool in pools:
    if old_address in pool["providers"]:
        pool["providers"][new_address] = ...
        del pool["providers"][old_address]
save_pools(pools)

# Swap: Separate fresh load
pools = load_pools()
# Update reserves
save_pools(pools)
Race Condition:

Admin reads pools at T1, starts migration
User reads pools at T1, performs swap
Admin writes pools at T2 (migration changes lost, swap preserved)
User writes pools at T2 (swap changes lost, admin migration lost)
Risk Level: MEDIUM
Real Safeguard: atomic_write_json() + quick operation time
Recommended Fix: Migration during scheduled maintenance window (e.g., after each block)

Part 5: Data Dependency Integrity Checklist
Pre-Merge for PR #526
not done
Verify save_pools() uses atomic_write_json() internally
not done
Confirm tx_feed() returns migration events in insertion order
not done
Test LP migration with 10+ concurrent swap operations (stress test)
not done
Verify dry-run doesn't mutate pools.json
not done
Confirm CORE_MINER_WALLET_DO_NOT_BIND check blocks all three endpoints
not done
Test idempotency: re-running migration with same params produces same result
not done
Verify pools.json backup exists before real migrations are allowed
not done
Test rollback: restore pools.json from backup and verify state consistency
Post-Merge Monitoring
not done
Track migration execution times (should be <100ms)
not done
Monitor pools.json file size growth (should be constant)
not done
Alert on migration failures (admin notification)
not done
Periodic audit: verify sum of all provider shares matches expected total
Part 6: Future Integration Points (Roadmap)
Q3 2026: Automated Consolidation
When: Wallet V1 consolidation period ends
Goal: Auto-consolidate split wallets without admin intervention
Risk: Must not mutate ledger without proof
Action:
  1. Scheduled job queries all split_v1_wallets
  2. For each wallet with migration proof
  3. Execute consolidation (requires manual fund transfer, not ledger)
  4. Update migration map in wallet_v1_migration.py
Q4 2026: Cross-Ledger Transactions
Goal: Single transaction spanning ledger.json + pools.json atomically
Approach:
  1. Migrate to single JSON file (ledger v2)
  2. Wrap pools and balances in unified structure
  3. Implement ACID semantics via SQLite backend
  4. Phase out JSON ledger
2027: Subsystem Separation
Goal: Extract mining, music, L2E into microservices
Approach:
  1. Define subsystem APIs (gRPC/REST)
  2. Implement ledger as shared external service
  3. Deploy mining as independent service
  4. Reduce monolith to <10k lines
Appendix A: Glossary
Term	Definition	Example
Ledger	Master source of truth for THR balances	ledger.json
Mutation	Write operation that modifies state	Swap, transfer, tip
Dry-Run	Non-destructive simulation of a mutation	LP migration with dry_run=true
Atomic Write	All-or-nothing file operation	save_json() with fsync
Provider Shares	LP stake in a liquidity pool	50 shares in pool X
Migration Proof	Evidence of legitimate wallet V1 migration	wallet_v1_migration tx event
Idempotent	Operation can be repeated safely	Re-running migration = no-op
Appendix B: Monitoring & Alerting Rules
Critical Alerts:

ledger.json grows > 100MB (unlimited balance accounts?)
Swap fails to update pools.json (race condition?)
LP migration fails mid-execution (rollback needed?)
tx_feed() returns duplicate migration events (replay?)
CORE_MINER_WALLET balance decreases (CRITICAL: core wallet touched!)
Health Checks:

Pool reserves satisfy x*y=k invariant
Total ledger balance is positive and bounded
No negative balances exist
Provider shares sum matches expected total per pool
End of Ecosystem Dependency Map