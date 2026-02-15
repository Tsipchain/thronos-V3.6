# ThronosChain V3.6
Multi-Node Blockchain with AI, BTC Bridge, and Multi-Chain Wallet

## Overview
ThronosChain is a next-generation blockchain platform featuring:
- Multi-node architecture (master/replica setup)
- AI-powered services with multiple provider support
- BTC pledge/bridge functionality
- Non-custodial multi-chain wallet backend
- Proof-of-Work consensus with dynamic difficulty
- Smart contract support (EVM-compatible)
- DeFi features (tokens, pools, swaps)
- Learn-to-Earn (L2E) ecosystem

---

## Multi-Node Architecture (PR-182)

ThronosChain supports a distributed multi-node setup with clear role separation between Node 1 (master) and Node 2 (replica/worker).

### Node Roles

#### Node 1: Master Node
- **URL**: `thrchain.up.railway.app`
- **Role**: Main chain writer + public API
- **Capabilities**:
  - Writes to chain/ledger JSON files
  - Handles all public API requests
  - Processes transactions (submit_block, pledge, send, mining)
  - Runs chain maintenance schedulers (minting, mempool, aggregator)
  - Serves user-facing AI features

#### Node 2: Replica/Worker Node
- **URL**: `node-2.up.railway.app`
- **Role**: Replica with background workers
- **Capabilities**:
  - Read-only access to chain/ledger
  - Runs background workers/schedulers (BTC watcher, etc.)
  - Calls Node 1 APIs for write operations
  - Handles background AI tasks (worker mode)

### Environment Variables

Configure node roles using these environment variables:

```bash
# Node 1 (Master) Configuration
NODE_ROLE=master
READ_ONLY=0
IS_LEADER=1
SCHEDULER_ENABLED=1
THRONOS_AI_MODE=production

# Node 2 (Replica) Configuration
NODE_ROLE=replica
READ_ONLY=1
IS_LEADER=0
SCHEDULER_ENABLED=1
THRONOS_AI_MODE=worker

# Shared Configuration
MASTER_NODE_URL=https://thrchain.up.railway.app
ADMIN_SECRET=your_secure_secret_here
DATA_DIR=/app/data
```

### Variable Descriptions

| Variable | Values | Description |
|----------|--------|-------------|
| `NODE_ROLE` | `master`, `replica` | Determines node behavior |
| `READ_ONLY` | `0`, `1` | Enforces read-only mode for replicas |
| `IS_LEADER` | `0`, `1` | Leader flag for consensus |
| `SCHEDULER_ENABLED` | `0`, `1` | Enables/disables background schedulers |
| `THRONOS_AI_MODE` | `production`, `worker` | AI service mode |
| `MASTER_NODE_URL` | URL | Master node API endpoint |
| `ADMIN_SECRET` | String | Shared secret for cross-node API calls |

### AI Mode Semantics

- **`production`** (Node 1): Serves user-facing AI chat, billing, and interactive features
- **`worker`** (Node 2): Handles background AI tasks, queue workers, no direct user API

### Write Protection

Replica nodes are protected from accidentally writing to critical chain files:
- `ledger.json` - THR wallet balances
- `wbtc_ledger.json` - Wrapped BTC balances
- `phantom_tx_chain.json` - Transaction chain
- `pledge_chain.json` - Pledge contracts
- `mempool.json` - Pending transactions
- `last_block.json` - Latest block summary
- `tx_ledger.json` - Transaction log
- `voting.json` - Governance voting state
- `ai_agent_credentials.json` - AI wallet credentials

Any write attempt to these files from a replica node will raise a `PermissionError`.

**Startup Guards:**
- `ensure_ai_wallet()` - Skipped on replica nodes
- `initialize_voting()` - Skipped on replica nodes
- `prune_empty_sessions()` - Skipped on replica nodes

### Deployment on Railway

1. Create two Railway services:
   - Service 1: Master node
   - Service 2: Replica node

2. Set environment variables for each service as shown above

3. Mount persistent volumes at `/app/data` for both services

4. Node 2 will automatically send heartbeats to Node 1 for health monitoring

---

## BTC Pledge / Treasury / Hot Wallet (PR-183)

ThronosChain includes a robust BTC bridge system with clear separation of vault, hot wallet, and treasury addresses.

### BTC Environment Variables

```bash
# BTC Address Roles
BTC_PLEDGE_VAULT=1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ    # Where pledges land
BTC_HOT_WALLET=1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ       # Source for withdrawals
BTC_TREASURY=3KUGVJQ5tJWKY7GDVgwLjJ7EBzVWatD9nF         # Protocol fees destination

# Fee Configuration
BTC_NETWORK_FEE=0.0002                # BTC network tx fee
MIN_BTC_WITHDRAWAL=0.001              # Minimum withdrawal amount
MAX_BTC_WITHDRAWAL=0.5                # Maximum withdrawal amount
WITHDRAWAL_FEE_PERCENT=0.5            # Withdrawal fee (0.5%)

# Exchange Rate
THR_BTC_RATE=33333.33                 # THR per 1 BTC

# BTC RPC Configuration
BTC_RPC_URL=https://your-btc-node-rpc
BTC_RPC_USER=your_rpc_username
BTC_RPC_PASSWORD=your_rpc_password
```

### Address Semantics

| Address | Purpose | Usage |
|---------|---------|-------|
| `BTC_PLEDGE_VAULT` | Receives all BTC pledges | Users send BTC here to get THR |
| `BTC_HOT_WALLET` | Source for withdrawals | Bridge-out transactions withdraw from here |
| `BTC_TREASURY` | Protocol fees | Bridge fees are sent here |

### BTC Watcher Service

Node 2 runs a background watcher that:
1. Polls `BTC_RPC_URL` for incoming transactions to `BTC_PLEDGE_VAULT`
2. Resolves user identity (THR address) from BTC transaction
3. Calls Node 1 API (`/api/btc/pledge`) to:
   - Credit THR to user's wallet
   - Create on-chain pledge transaction
   - Activate wallet for KYC-verified users

#### Pledge Transaction Format

```json
{
  "type": "btc_pledge",
  "thr_address": "THR...",
  "btc_address": "1...",
  "btc_amount": 0.1,
  "thr_amount": 3333.33,
  "btc_txid": "abc123...",
  "kyc_verified": true,
  "whitelisted_admin": false,
  "timestamp": "2026-01-11 10:30:00 UTC",
  "status": "confirmed"
}
```

### Bridge-Out Fees

Withdrawal fees are calculated as:

```python
protocol_fee = btc_amount * (WITHDRAWAL_FEE_PERCENT / 100.0)
network_fee = BTC_NETWORK_FEE
total_fees = protocol_fee + network_fee
net_to_user = btc_amount - total_fees
```

Example for 0.1 BTC withdrawal:
- Gross amount: 0.1 BTC
- Protocol fee (0.5%): 0.0005 BTC
- Network fee: 0.0002 BTC
- Total fees: 0.0007 BTC
- Net to user: 0.0993 BTC

### API Endpoints

#### Create BTC Pledge (Internal - requires ADMIN_SECRET)
```bash
POST /api/btc/pledge
Content-Type: application/json

{
  "secret": "ADMIN_SECRET",
  "thr_address": "THR...",
  "btc_address": "1...",
  "btc_amount": 0.1,
  "thr_amount": 3333.33,
  "btc_txid": "abc123...",
  "kyc_verified": true
}
```

#### Activate Wallet (Internal - requires ADMIN_SECRET)
```bash
POST /api/wallet/activate
Content-Type: application/json

{
  "secret": "ADMIN_SECRET",
  "thr_address": "THR...",
  "btc_address": "1..."
}
```

---

## Multi-Chain Non-Custodial Wallet Backend (PR-184)

ThronosChain provides a non-custodial multi-chain wallet backend that reads balances from external RPCs and never stores private keys.

### Supported Chains

| Chain | RPC Variable | Default RPC |
|-------|-------------|-------------|
| Ethereum | `ETH_RPC_URL` | `https://eth.llamarpc.com` |
| BSC | `BSC_RPC_URL` | `https://bsc-dataseed.binance.org` |
| Polygon | `POLYGON_RPC_URL` | `https://polygon-rpc.com` |
| Arbitrum | `ARBITRUM_RPC_URL` | `https://arb1.arbitrum.io/rpc` |
| Optimism | `OPTIMISM_RPC_URL` | `https://mainnet.optimism.io` |
| Solana | `SOLANA_RPC_URL` | `https://api.mainnet-beta.solana.com` |
| XRP Ledger | `XRP_RPC_URL`, `XRPL_RPC_URL` | `https://xrplcluster.com` |
| Bitcoin | `BTC_RPC_URL` | (requires configuration) |

### User Profile Model

```json
{
  "user_id": "user123",
  "kyc_id": "KYC123",
  "is_kyc_verified": true,
  "is_whitelisted_admin": false,
  "thr_address": "THR...",
  "btc_address": "1...",
  "btc_pledge_address": "1...",
  "evm_address": "0x...",
  "sol_address": "...",
  "xrp_address": "r...",
  "created_at": 1234567890,
  "updated_at": 1234567890
}
```

### API Endpoints

#### Get Wallet Profile
```bash
GET /api/wallet/profile?user_id=user123

Response:
{
  "ok": true,
  "profile": {
    "user_id": "user123",
    "thr_address": "THR...",
    "btc_address": "1...",
    "evm_address": "0x...",
    "sol_address": "...",
    "xrp_address": "r...",
    "is_kyc_verified": true
  }
}
```

#### Update Wallet Profile
```bash
POST /api/wallet/profile
Content-Type: application/json

{
  "user_id": "user123",
  "thr_address": "THR...",
  "evm_address": "0x...",
  "btc_address": "1..."
}

Response:
{
  "ok": true,
  "profile": { ... }
}
```

#### Get Aggregated Balances
```bash
GET /api/wallet/balances?user_id=user123

Response:
{
  "ok": true,
  "user_id": "user123",
  "balances": {
    "thronos": {
      "thr": 1000.0,
      "wbtc": 0.5,
      "wusdc": 500.0
    },
    "native": {
      "eth": 1.5,
      "bnb": 10.0,
      "btc": 0.1,
      "sol": 50.0,
      "xrp": 1000.0
    },
    "total_usd_value": 5000.0
  },
  "timestamp": 1234567890
}
```

#### Preview Native Transaction
```bash
POST /api/wallet/native_tx_preview
Content-Type: application/json

{
  "chain": "eth",
  "from_address": "0x...",
  "to_address": "0x...",
  "amount": 1.5
}

Response:
{
  "ok": true,
  "chain": "eth",
  "unsigned_tx": {
    "nonce": 10,
    "gasPrice": "0x4a817c800",
    "gas": "0x5208",
    "to": "0x...",
    "value": "0x14d1120d7b160000",
    "data": "0x"
  },
  "estimated_fee": 0.00042
}
```

#### Broadcast Signed Transaction
```bash
POST /api/wallet/native_tx_broadcast
Content-Type: application/json

{
  "chain": "eth",
  "signed_tx": "0xf86c0a8504a817c800825208..."
}

Response:
{
  "ok": true,
  "success": true,
  "txid": "0xabc123...",
  "chain": "eth"
}
```

#### Bridge In (Native → Wrapped)
```bash
POST /api/bridge/in
Content-Type: application/json

{
  "chain": "btc",
  "asset": "BTC",
  "amount": 0.1,
  "user_id": "user123"
}

Response:
{
  "ok": true,
  "bridge_id": "BRIDGE_IN_1234567890_abc123",
  "deposit_address": "1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ",
  "expected_wrapped_amount": 3333.33,
  "instructions": "Send 0.1 BTC to 1QFeDPwEF8yEgPEfP79hpc8pHytXMz9oEQ",
  "status": "pending"
}
```

#### Bridge Out (Wrapped → Native)
```bash
POST /api/bridge/out
Content-Type: application/json

{
  "chain": "btc",
  "asset": "BTC",
  "amount": 0.1,
  "destination_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
  "user_id": "user123"
}

Response:
{
  "ok": true,
  "bridge_id": "BRIDGE_OUT_1234567890_def456",
  "burn_tx_id": "BURN_1234567890_ghi789",
  "fee_breakdown": {
    "gross_amount": 0.1,
    "protocol_fee": 0.0005,
    "network_fee": 0.0002,
    "total_fees": 0.0007,
    "net_amount": 0.0993
  },
  "destination_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
  "status": "pending_withdrawal",
  "estimated_time": "10-60 minutes"
}
```

### Security Notes

- **Non-custodial**: Backend never stores private keys or seed phrases
- **Client-side signing**: All transactions are signed on the client
- **Address-only storage**: Only public addresses and metadata are stored
- **HTTPS required**: All API calls must use HTTPS in production
- **Authentication**: Use session tokens or JWT for user authentication

---

## Installation & Deployment

### Prerequisites
- Python 3.9+
- Node.js 16+ (for frontend)
- PostgreSQL or JSON file storage
- Access to RPC endpoints for each chain

### Local Development

```bash
# Clone repository
git clone https://github.com/Tsipchain/thronos-V3.6.git
cd thronos-V3.6

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your configuration

# Run master node
NODE_ROLE=master python server.py

# Run replica node (in another terminal)
NODE_ROLE=replica python server.py
```

### Railway Deployment

1. **Create Railway Project**
   ```bash
   railway login
   railway init
   ```

2. **Create Two Services**
   - Master Node (thrchain)
   - Replica Node (node-2)

3. **Configure Environment Variables**

   Master Node:
   ```
   NODE_ROLE=master
   THRONOS_AI_MODE=production
   SCHEDULER_ENABLED=1
   [... other env vars ...]
   ```

   Replica Node:
   ```
   NODE_ROLE=replica
   THRONOS_AI_MODE=worker
   SCHEDULER_ENABLED=1
   MASTER_NODE_URL=https://thrchain.up.railway.app
   [... other env vars ...]
   ```

4. **Mount Volumes**
   - Create persistent volume at `/app/data` for both services

5. **Deploy**
   ```bash
   railway up
   ```

---

## Blockchain Viewer & Explorer API

ThronosChain provides comprehensive APIs for viewing blocks, transactions, and mining statistics with proper categorization and filtering.

### Transaction Categories

All transactions are automatically categorized into the following types:
- `token_transfer` - Normal THR/token sends
- `music_tip` - Tips to artists (music streaming)
- `ai_reward` - AI-related rewards/payments
- `iot_telemetry` - IoT device data/GPS telemetry
- `bridge` - Bridge in/out transactions
- `pledge` - BTC/fiat pledges
- `mining` - Block mining rewards
- `swap` - Token swaps
- `liquidity` - Pool adds/removes
- `other` - Everything else

### API Endpoints

#### Get Blocks (Paginated)
```bash
GET /api/blocks?offset=0&limit=100&from_height=1&to_height=1000

Response:
{
  "ok": true,
  "blocks": [...],
  "total": 21000,
  "offset": 0,
  "limit": 100,
  "has_more": true,
  "min_height": 1,
  "max_height": 21000
}
```

#### Get Transfers with Statistics
```bash
GET /api/transfers?offset=0&limit=100&type=music_tip&address=THR...

Response:
{
  "ok": true,
  "transfers": [...],
  "total": 500,
  "offset": 0,
  "limit": 100,
  "has_more": true,
  "stats": {
    "total_transfers": 500,
    "unique_addresses": 150,
    "period": "all_time",  // or "24h" if total > 10,000
    "use_time_filter": false,
    "by_category": {
      "token_transfer": 300,
      "music_tip": 100,
      "ai_reward": 50,
      "bridge": 30,
      "pledge": 20
    }
  }
}
```

**Adaptive Statistics:**
- If total transfers < 10,000: Returns all-time statistics
- If total transfers ≥ 10,000: Returns last 24h statistics with indicator
- This ensures fast response times on large networks

**Filter Parameters:**
- `type`: Filter by category (e.g., `music_tip`, `ai_reward`, `iot_telemetry`)
- `address`: Filter by sender or receiver address
- `stats_only=true`: Return only statistics (no transaction list)

#### Get Mining Statistics
```bash
GET /api/wallet/mining_stats?address=THR...

Response:
{
  "ok": true,
  "address": "THR...",
  "blocks_mined": 42,
  "total_block_reward": 21.5,
  "total_pool_burn": 0.5,
  "total_ai_share": 2.1,
  "last_block_height": 21000,
  "last_block_time": "2026-01-11 12:00:00 UTC",
  "recent_blocks": [
    {
      "height": 21000,
      "hash": "abc123...",
      "reward": 0.5,
      "fee_burned": 0.01,
      "timestamp": "2026-01-11 12:00:00 UTC",
      "is_stratum": true
    },
    ...
  ]
}
```

### Viewer Features

**Blocks Tab:**
- Shows all blocks from genesis (height 1) to tip
- Proper pagination with "Load More"
- No artificial limits (previously stopped at ~17k)
- Displays:
  - Block height
  - Block hash
  - Miner reward
  - Fees burned
  - AI share
  - Timestamp
  - Mining type (Stratum vs CPU)

**Transfers Tab:**
- Adaptive statistics (all-time or 24h depending on network size)
- Category breakdown (music tips, AI rewards, IoT, etc.)
- Filter by transaction type
- Filter by address
- Shows unique addresses count

**Mining History:**
- Per-wallet mining statistics
- Total blocks mined
- Total rewards earned
- Recent blocks list
- Links to block details

### IoT & AI Integration

The transaction categorization system is designed to support:

1. **Hard Miners (ASICs/GPUs):**
   - Do heavy PoW computation
   - Get base block rewards
   - Transactions tagged as `mining`

2. **Music & AI Tips:**
   - Users tip artists while streaming music
   - Part of tips reserved for AI training pool
   - Transactions tagged as `music_tip` and `ai_reward`

3. **IoT Miners:**
   - Devices (cars, mobile) send GPS/telemetry
   - Store AI-related blocks and tips
   - Receive share of AI pool for telemetry
   - Transactions tagged as `iot_telemetry`

This categorization enables:
- Clear separation of value streams
- Transparent reward distribution
- AI autopilot training data collection
- Fair compensation for all participants

---

## Phase 4: IoT Miners, AI Tips Pool & Governance

### Overview

Phase 4 introduces a comprehensive rewards ecosystem that distributes value from music tips to both traditional miners and IoT contributors:

- **AI Tips Pool**: 10% of all music tips go into a shared reward pool
- **Dual Mining Rewards**: Pool distributed to both ASIC/GPU miners and IoT device operators
- **IoT Telemetry**: Devices earn rewards for contributing GPS/sensor data
- **Governance Integration**: Pytheia AI auditor can query chain metrics for automated proposals

### AI Tips Pool Economics

**Music Tip Flow:**
```
User Tips Artist 100 THR
├─ 90 THR → Artist (direct payment)
└─ 10 THR → AI Pool (shared rewards)
```

**Distribution Schedule:**
- Runs every 30 minutes (configurable via `AI_POOL_DISTRIBUTION_INTERVAL`)
- Only distributes when pool balance ≥ 10 THR (configurable via `AI_POOL_MIN_BALANCE`)
- Each distribution: 10% of current pool balance (configurable via `AI_POOL_DISTRIBUTION_PCT`)

**Reward Allocation:**
- 60% to Hard Miners (pro-rata by blocks mined in last 100 blocks)
- 40% to IoT Miners (pro-rata by telemetry samples in last 60 minutes)

### Environment Variables

**AI Pool Configuration:**
```bash
# Distribution schedule
AI_POOL_DISTRIBUTION_INTERVAL=30          # Minutes between distributions

# Pool thresholds
AI_POOL_MIN_BALANCE=10.0                  # Minimum THR before distributing
AI_POOL_DISTRIBUTION_PCT=0.10             # Percentage of pool to distribute each time

# Reward split
AI_POOL_MINER_SHARE=0.60                  # 60% to hard miners
# IoT share is automatically (1 - MINER_SHARE) = 40%

# Lookback windows
AI_POOL_LOOKBACK_BLOCKS=100               # Blocks to consider for miner rewards
AI_POOL_LOOKBACK_MINUTES=60               # Minutes to consider for IoT rewards
```

### IoT Telemetry API

**Submit Telemetry Data:**

Devices POST GPS/sensor data to earn eligibility for AI pool rewards.

```bash
POST /api/iot/telemetry
Content-Type: application/json

{
  "address": "THR...",                    # Your THR wallet address
  "device_id": "car-123",                 # Optional device identifier
  "route_hash": "sha256_hash_of_path",    # Hash of GPS coordinates
  "samples": 150                          # Number of data points collected
}
```

**Response:**
```json
{
  "ok": true,
  "tx_id": "IOT-TELEM-1736611200-abc123",
  "message": "Telemetry recorded: 150 samples"
}
```

**Transaction Schema:**
```json
{
  "type": "iot_telemetry",
  "address": "THR...",
  "device_id": "car-123",
  "route_hash": "sha256...",
  "samples": 150,
  "timestamp": "2026-01-11 12:00:00 UTC",
  "tx_id": "IOT-TELEM-...",
  "status": "confirmed"
}
```

### AI Pool Monitoring

**Get Pool Status:**

```bash
GET /api/ai_pool/status
```

**Response:**
```json
{
  "ok": true,
  "pool": {
    "ai_pool_balance": 125.5,
    "total_music_tips": 2450.0,
    "total_ai_distributed": 85.3,
    "last_distribution_time": "2026-01-11 12:30:00 UTC",
    "total_music_tips_count": 543,
    "total_ai_rewards_count": 128
  }
}
```

### Wallet History with Categories

**Get Categorized Wallet History:**

```bash
GET /api/wallet/history?address=THR...&category=ai_reward
```

**Response:**
```json
{
  "ok": true,
  "address": "THR...",
  "total_transactions": 250,
  "summary": {
    "total_mining": 150.5,
    "total_ai_rewards": 45.2,
    "total_music_tips_sent": 0.0,
    "total_music_tips_received": 80.0,
    "total_iot_rewards": 0.0,
    "total_sent": 100.0,
    "total_received": 275.7,
    "mining_count": 50,
    "ai_reward_count": 25,
    "music_tip_count": 10,
    "iot_count": 15
  },
  "transactions": [
    {
      "type": "ai_reward",
      "category": "mining",
      "to": "THR...",
      "amount": 1.5,
      "direction": "received",
      "timestamp": "2026-01-11 12:00:00 UTC",
      "details": {
        "blocks_mined": 3,
        "lookback_blocks": 100
      }
    },
    ...
  ]
}
```

**Category Filters:**
- `mining` - Mining rewards from blocks
- `ai_reward` - Rewards from AI pool distribution
- `music_tip` - Tips to/from artists
- `iot_telemetry` - IoT data submissions
- `bridge` - Cross-chain bridge transactions
- `pledge` - BTC pledge deposits
- `swap` - Token swaps
- `liquidity` - Liquidity operations
- `token_transfer` - Standard THR transfers

### Governance Integration (Pytheia)

**AI Governance Overview:**

Pytheia AI auditor can query aggregated chain metrics for automated governance proposals.

```bash
GET /api/governance/ai_overview
```

**Response:**
```json
{
  "ok": true,
  "overview": {
    "ai_pool_balance": 125.5,
    "total_ai_rewards": 85.3,
    "iot_telemetry_txs_last_24h": 45,
    "music_tips_last_24h": 12,
    "music_tips_amount_last_24h": 234.5,
    "miners_online_estimate": 8,
    "last_distribution_time": "2026-01-11 12:30:00 UTC",
    "node_role": "master",
    "read_only": false
  }
}
```

**Use Cases:**
- Monitor AI pool health and trigger alerts if balance too low/high
- Detect anomalies in tipping patterns
- Propose parameter adjustments based on network activity
- Generate reports for community governance votes

**Safety:**
- Endpoint is read-only and safe to call from replica nodes
- No authentication required (public metrics)
- All write operations (distributions) happen only on master nodes

### Transaction Categories

All transactions are automatically categorized for filtering and analytics:

| Category | Description | Examples |
|----------|-------------|----------|
| `token_transfer` | Standard THR transfers | Wallet-to-wallet sends |
| `music_tip` | Tips to artists | Music platform tips |
| `ai_reward` | AI pool distributions | Miner/IoT rewards |
| `iot_telemetry` | IoT data submissions | GPS, sensor data |
| `bridge` | Cross-chain operations | BTC ↔ THR bridge |
| `pledge` | BTC pledge deposits | BTC → THR conversions |
| `mining` | Block mining rewards | PoW coinbase txs |
| `swap` | Token swaps | DEX trades |
| `liquidity` | Pool operations | Add/remove liquidity |
| `other` | Uncategorized | Miscellaneous |

### Reward Flow Example

**Scenario:** A music listener tips an artist 100 THR

1. **Music Tip Transaction:**
   - Listener balance: -100 THR
   - Artist receives: 90 THR (90%)
   - AI Pool receives: 10 THR (10%)
   - Transaction type: `music_tip`

2. **AI Pool Accumulation:**
   - Pool balance grows with each tip
   - Scheduler monitors pool every 30 minutes

3. **Distribution Trigger:**
   - Pool balance reaches 125 THR
   - Distribution amount: 12.5 THR (10% of pool)
   - Miner allocation: 7.5 THR (60%)
   - IoT allocation: 5.0 THR (40%)

4. **Miner Rewards:**
   - Last 100 blocks analyzed
   - Miner A: 30 blocks → 3.75 THR
   - Miner B: 20 blocks → 2.5 THR
   - Miner C: 10 blocks → 1.25 THR
   - Transaction type: `ai_reward` (category: `mining`)

5. **IoT Rewards:**
   - Last 60 minutes of telemetry analyzed
   - Device A: 300 samples → 3.0 THR
   - Device B: 200 samples → 2.0 THR
   - Transaction type: `ai_reward` (category: `iot_telemetry`)

### Multi-Node Considerations

**Master Node:**
- Handles all AI pool writes
- Runs distribution scheduler
- Records music tip contributions
- Creates ai_reward transactions

**Replica Nodes:**
- Can serve `/api/ai_pool/status` (read-only)
- Can serve `/api/governance/ai_overview` (read-only)
- Can serve `/api/wallet/history` (read-only)
- Cannot modify AI pool state

**Write Protection:**
- `ai_pool.json` added to critical files list
- Replica nodes will skip AI pool credits/debits
- Only master node runs `distribute_ai_rewards_step`

---

## Base Wallet & Bridge API Contract

### Overview

The Thronos base wallet is designed as a universal interface that works across:
- Web browsers (desktop/mobile)
- Mobile native apps (Android/iOS via WebView or native)
- IoT devices (future integration)

All wallet implementations use the same backend API contract, ensuring consistency across platforms.

### API Base Configuration

**Environment Variable:**
```bash
API_BASE_URL=https://thrchain.up.railway.app
```

**Frontend Configuration:**
All wallet frontends should read the API base from a single configuration point:

```javascript
// Set in HTML template
window.TH_API_BASE_URL = "{{ api_base_url }}";

// Or via environment detection
const API_BASE = window.TH_API_BASE_URL ||
                 window.location.origin;
```

**Deployment URLs:**
- **Master Node:** https://thrchain.up.railway.app
- **Replica Node:** https://node-2.up.railway.app (read-only)
- **Gateway:** https://thronoschain.vercel.app (proxies to master)

### Core Wallet Endpoints

#### 1. Wallet Balance & Info

```bash
GET /api/wallet/profile?address=THR...
```

Returns wallet profile with all chain balances.

#### 2. Wallet History

```bash
GET /api/wallet/history?address=THR...&category=<filter>
```

**Category Filters:**
- `mining` - Mining rewards
- `ai_reward` - AI pool distributions
- `music_tip` - Music tips sent/received
- `iot_telemetry` - IoT data submissions
- `bridge` - Cross-chain operations
- `pledge` - BTC pledges
- `token_transfer` - Standard transfers
- `swap` - Token swaps
- `liquidity` - Pool operations

**Response:**
```json
{
  "ok": true,
  "address": "THR...",
  "transactions": [...],
  "summary": {
    "total_mining": 150.5,
    "total_ai_rewards": 45.2,
    "total_music_tips_sent": 0.0,
    "total_music_tips_received": 80.0,
    "total_iot_rewards": 0.0,
    "total_sent": 100.0,
    "total_received": 275.7,
    "mining_count": 50,
    "ai_reward_count": 25,
    "music_tip_count": 10,
    "iot_count": 15
  }
}
```

#### 3. Mining Statistics

```bash
GET /api/wallet/mining_stats?address=THR...
```

Returns blocks mined, rewards earned, recent blocks list.

#### 4. Send Transaction

```bash
POST /api/wallet/send
Content-Type: application/json

{
  "from_address": "THR...",
  "to_address": "THR...",
  "amount": 100.0,
  "auth_secret": "...",
  "passphrase": "..." // optional
}
```

### Cross-Chain Bridge API Contract

#### Bridge Transaction Types

All bridge operations create transactions with:
- `type`: "bridge" or "bridge_in" / "bridge_out"
- `category`: "bridge"
- Chain identifiers: "BTC", "ETH", "BNB", "XRP", "SOL"

#### 1. Bridge In (External → Thronos)

**Endpoint:** `POST /api/btc/pledge` (BTC example)

```json
{
  "secret": "ADMIN_SECRET",
  "thr_address": "THR...",
  "btc_amount": 0.001,
  "btc_txid": "abc123..."
}
```

Creates internal "bridge_in" transaction crediting THR.

#### 2. Bridge Out (Thronos → External)

**Endpoint:** `POST /api/bridge/btc/out` (future)

```json
{
  "from_address": "THR...",
  "btc_address": "bc1...",
  "amount": 100.0,  // THR amount
  "auth_secret": "..."
}
```

Creates internal "bridge_out" transaction, queues withdrawal.

#### 3. Bridge Status

```bash
GET /api/wallet/balances?address=THR...
```

Returns all chain balances (native THR + external chain balances).

### Supported Chains

| Chain | Symbol | RPC Config | Status |
|-------|--------|------------|--------|
| Thronos | THR | Built-in | ✅ Active |
| Bitcoin | BTC | `BTC_RPC_URL` | ✅ Active |
| Ethereum | ETH | `ETH_RPC_URL` | 🔄 Planned |
| BNB Chain | BNB | `BSC_RPC_URL` | 🔄 Planned |
| Solana | SOL | `SOLANA_RPC_URL` | 🔄 Planned |
| XRP Ledger | XRP | `XRP_RPC_URL` | 🔄 Planned |

### IoT Telemetry API

#### Submit IoT Data

```bash
POST /api/iot/telemetry
Content-Type: application/json

{
  "address": "THR...",
  "device_id": "car-123",
  "route_hash": "sha256_of_gps_path",
  "samples": 150
}
```

Creates `iot_telemetry` transaction, earns AI pool rewards.

#### Enable IoT Mining (Frontend)

```javascript
// UI toggle in wallet
const enableIoTMining = async () => {
  // Request location permissions
  if (!navigator.geolocation) {
    alert('Geolocation not supported');
    return;
  }

  // Start GPS tracking
  const watchId = navigator.geolocation.watchPosition(
    position => collectGPSData(position),
    error => console.error('GPS error:', error),
    { enableHighAccuracy: true }
  );

  // Periodically submit telemetry
  setInterval(() => submitTelemetry(), 60000); // Every minute
};

const submitTelemetry = async () => {
  const payload = {
    address: currentWallet,
    device_id: deviceId,
    route_hash: hashGPSPath(gpsBuffer),
    samples: gpsBuffer.length
  };

  await fetch(`${API_BASE}/api/iot/telemetry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
};
```

### Transaction Categories Reference

All transactions in wallet history are categorized for filtering:

```javascript
const CATEGORY_LABELS = {
  'token_transfer': 'THR Transfer',
  'music_tip': 'Music Tips',
  'ai_reward': 'AI Rewards',
  'iot_telemetry': 'IoT Telemetry',
  'bridge': 'Cross-Chain Bridge',
  'pledge': 'BTC Pledge',
  'mining': 'Mining Rewards',
  'swap': 'Token Swap',
  'liquidity': 'Liquidity Pool',
  'other': 'Other'
};
```

### Mobile Wallet Integration

**WebView (React Native / Flutter):**
```javascript
// Inject API base from native code
window.TH_API_BASE_URL = Platform.OS === 'android'
  ? 'https://thrchain.up.railway.app'
  : 'https://thrchain.up.railway.app';

// All API calls use this base
const response = await fetch(`${window.TH_API_BASE_URL}/api/wallet/history?address=${addr}`);
```

**Native Implementation:**
- Android: Use Retrofit/OkHttp with same API endpoints
- iOS: Use URLSession with same API endpoints
- Ensure all network calls include proper error handling
- Cache responses when appropriate (blocks, transfers)

### Security Considerations

**Authentication:**
- `auth_secret` and optional `passphrase` required for sends
- Never send raw private keys to server
- Sign transactions client-side when possible

**Rate Limiting:**
- Dashboard: 10 req/min per IP
- Wallet history: 60 req/min per IP
- IoT telemetry: 120 req/min per address

**CORS:**
- Production: Only allow thronos domains
- Development: `CORS_ORIGINS=*` for testing

---

## License

MIT License - see LICENSE file for details

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/Tsipchain/thronos-V3.6/issues
- Documentation: Coming soon
- Community: Discord (link coming soon)

---

## STATUS / Health Smoke Checks

Run local syntax + conflict sanity checks:

```bash
python3 -m py_compile server.py verify_id_service.py serv3r.py scripts/smoke_subdomains_health.py
rg -n "^(<<<<<<<|=======|>>>>>>>)" .
```

Run production smoke checks for subdomains:

```bash
python3 scripts/smoke_subdomains_health.py --timeout 20 --retries 3
```

Optional strict mode (enforces CORS `*` + stricter payload contract):

```bash
python3 scripts/smoke_subdomains_health.py --timeout 20 --retries 3 --strict
```

Targets: `api`, `ro.api`, `verifyid`, `verifyid-api`, `ai`, `explorer`, `sentinel`, `btc-api`.
