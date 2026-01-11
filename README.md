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

## License

MIT License - see LICENSE file for details

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/Tsipchain/thronos-V3.6/issues
- Documentation: Coming soon
- Community: Discord (link coming soon)
