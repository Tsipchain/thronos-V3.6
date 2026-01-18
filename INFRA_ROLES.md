# Infrastructure Roles – Thronos Multi-Node Architecture

**Version**: 1.0.0
**Last Updated**: 2026-01-18
**Status**: Production

---

## Overview

The Thronos blockchain operates across multiple specialized nodes, each with distinct responsibilities. This document defines the role of each node type and their expected configuration.

---

## Node Types

### Node 1 – Master Blockchain Node (Railway)

**URL**: `thrchain.up.railway.app`
**Role**: Primary blockchain coordinator and transaction processor

**Responsibilities**:
- ✅ Write operations to blockchain (block minting, transaction confirmation)
- ✅ Run all scheduler jobs (block production, AI rewards, aggregation)
- ✅ **Proxy AI requests to Node 4** (when AI_CORE_URL is set)
- ✅ Fallback to local AI if Node 4 is unavailable
- ✅ Initialize AI wallet and voting systems
- ✅ Process mempool and execute smart contracts
- ✅ Serve as heartbeat master for replica nodes

**Environment Configuration**:
```bash
# Node Identity
NODE_ROLE=master
NODE_NAME=node1-master
THRONOS_ENV=production

# Node Capabilities
READ_ONLY=0
IS_LEADER=1
SCHEDULER_ENABLED=1
ENABLE_CHAIN=1

# Network Configuration
DOMAIN_URL=https://thrchain.up.railway.app
API_BASE_URL=https://thrchain.up.railway.app
LEADER_URL=https://thrchain.up.railway.app
REPLICA_EXTERNAL_URL=https://node-2.up.railway.app

# AI Configuration
THRONOS_AI_MODE=proxy
AI_CORE_URL=https://thronos-v3-6.onrender.com

# AI Provider Keys (for fallback when Node 4 is unavailable)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Cross-Chain RPC URLs (ONLY on Node 1, not on Node 2)
BTC_RPC_URL=https://...
BTC_HOT_WALLET=<btc-address>
BTC_PLEDGE_VAULT=<btc-address>
BSC_RPC_URL=https://bsc-dataseed.binance.org
ETH_RPC_URL=https://eth-mainnet.alchemyapi.io/v2/...
XRP_RPC_URL=https://s1.ripple.com:51234
SOL_RPC_URL=https://api.mainnet-beta.solana.com

# Security
ADMIN_SECRET=<shared-secret>
```

**Startup Sequence**:
1. Refresh AI model catalog (OpenAI, Anthropic, Gemini)
2. Start model refresh scheduler
3. Initialize AI wallet
4. Sync blockchain height offset
5. Initialize voting system
6. Prune empty AI sessions
7. Start all master scheduler jobs

---

### Node 2 – Replica + Cross-Chain Watchers (Railway)

**URL**: `node-2.up.railway.app`
**Role**: Read-only blockchain replica with cross-chain bridge monitoring

**Responsibilities**:
- ✅ Read-only blockchain queries (balance checks, transaction history)
- ✅ BTC bridge pledge monitoring (`btc_pledge_watcher.py`)
- ✅ Cross-chain RPC integration (Bitcoin, BSC, Ethereum, XRP)
- ✅ Send heartbeat to master node every 30 seconds
- ❌ **NO** write operations to blockchain
- ❌ **NO** AI model sync (defers to master or future Node 4)
- ❌ **NO** scheduler jobs except BTC watcher

**Environment Configuration**:
```bash
# Node Identity
NODE_ROLE=replica
NODE_NAME=node2-replica
THRONOS_ENV=production

# Node Capabilities
READ_ONLY=1
IS_LEADER=0
SCHEDULER_ENABLED=0
ENABLE_CHAIN=1

# Network Configuration
DOMAIN_URL=https://node-2.up.railway.app
API_BASE_URL=https://node-2.up.railway.app
MASTER_NODE_URL=https://thrchain.up.railway.app
REPLICA_EXTERNAL_URL=https://node-2.up.railway.app

# Cross-Chain Configuration (read-only access for bridge monitoring)
# Note: Only include if strictly needed for reads; never for writes
BTC_RPC_URL=https://...
BTC_HOT_WALLET=<btc-address>  # Read-only monitoring
BTC_PLEDGE_VAULT=<btc-address>  # Read-only monitoring
BTC_TREASURY=<btc-address>
BSC_RPC_URL=https://bsc-dataseed.binance.org
ETH_RPC_URL=https://eth-mainnet.alchemyapi.io/v2/...
XRP_RPC_URL=https://s1.ripple.com:51234

# Bridge Parameters
THR_BTC_RATE=0.00001
MIN_BTC_WITHDRAWAL=0.0001
MAX_BTC_WITHDRAWAL=1.0
WITHDRAWAL_FEE_PERCENT=0.5

# Heartbeat Configuration
HEARTBEAT_ENABLED=1
HEARTBEAT_LOG_ERRORS=0

# Security
ADMIN_SECRET=<shared-secret>

# NO AI KEYS ON REPLICA
# Replica does not run AI jobs - all AI processing happens on Node 1 or Node 4
```

**Important Notes**:
- ❌ **NO AI KEYS** - Node 2 should not have OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY
- ❌ Node 2 does **NOT** initialize AI models or run model sync
- ✅ Cross-chain RPC URLs only for read operations (bridge monitoring)
- ✅ Heartbeat failures log warnings but **DO NOT** crash the process

---

### Node 3 – Static SDK & Documentation (Vercel)

**URL**: `thrchain.vercel.app`
**Role**: Static frontend for wallet SDK and documentation

**Responsibilities**:
- ✅ Serve wallet SDK files (`wallet_sdk.js`, `wallet_auth.js`, `music_module.js`)
- ✅ Host wallet history viewer (lightweight, standalone)
- ✅ Public documentation and API reference
- ✅ No backend processing (static site only)

**Environment Configuration**:
```bash
# Public-only environment variables
NEXT_PUBLIC_API_BASE_URL=https://thrchain.up.railway.app
NEXT_PUBLIC_NODE2_URL=https://node-2.up.railway.app
NEXT_PUBLIC_CHAIN_NAME=Thronos

# NO SECRETS (Vercel public environment)
# No ADMIN_SECRET
# No API keys
# No private keys
```

**Deployment**:
- Vercel automatically deploys from `main` branch
- SDK files must be in `/public/` or `/static/` directory
- All assets served via CDN (no dynamic routes)

---

### Node 4 – AI Core (Render)

**URL**: `https://thronos-v3-6.onrender.com` (or your Render URL)
**Role**: Centralized AI processing and LLM orchestration
**Status**: ✅ **READY FOR DEPLOYMENT** (see [NODE4_DEPLOYMENT.md](./NODE4_DEPLOYMENT.md))

**Responsibilities**:
- ✅ AI model catalog management (OpenAI, Anthropic, Gemini)
- ✅ AI chat completions (`/api/ai/chat`)
- ✅ AI Architect blueprint generation (`/api/architect_generate`)
- ✅ AI models listing (`/api/ai_models`)
- ✅ AI knowledge watcher scheduler
- ✅ AI rewards pool distribution
- ❌ **NO** blockchain operations (mining, mempool, peers)
- ❌ **NO** heartbeats (not part of chain cluster)

**Environment Configuration**:
```bash
# Node Role
NODE_ROLE=ai_core
READ_ONLY=1
SCHEDULER_ENABLED=1
ENABLE_CHAIN=0              # Disable all blockchain functionality

# AI Mode
THRONOS_AI_MODE=production

# AI Provider Keys (ALL AI KEYS HERE)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# AI Core API
AI_CORE_PORT=8001
AI_CORE_ALLOWED_ORIGINS=https://thrchain.up.railway.app,https://node-2.up.railway.app

# Admin Secret (shared with all nodes)
ADMIN_SECRET=<shared-secret>
```

**Graceful Degradation**:
⚠️ **IMPORTANT**: If Node 4 is down, only AI features degrade. Wallet, mining, and chain operations continue normally.
- Node 1 has AI provider keys as fallback
- AI chat/architect endpoints will use Node 1's local AI
- Core blockchain functionality is NOT affected
- This is by design - Node 4 is a passive optimization, not a critical dependency

**Migration Plan**:
1. Node 1 and Node 2 will call Node 4 via `AI_CORE_URL` for AI operations
2. AI model sync moves from Node 1 to Node 4
3. Risk scoring and governance AI logic migrates to Node 4
4. Node 1 becomes pure blockchain coordinator
5. Node 2 remains cross-chain watcher (no AI dependencies)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Thronos Network                        │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   Node 1 (Master)│◄─────┤   Node 2 (Replica)│      │   Node 3 (SDK)   │
│   Railway        │      │   Railway         │      │   Vercel         │
│                  │      │                   │      │                  │
│ • Write ops      │      │ • Read-only       │      │ • Static files   │
│ • Schedulers     │      │ • BTC watcher     │      │ • SDK bundles    │
│ • AI models      │      │ • Heartbeat       │      │ • Docs           │
│ • Voting         │      │ • Cross-chain     │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
         │                         │                         │
         │                         │                         │
         ▼                         ▼                         ▼
┌──────────────────────────────────────────────────────────────┐
│                    External Chains & APIs                    │
│   Bitcoin • BSC • Ethereum • XRP • Ripple                   │
└──────────────────────────────────────────────────────────────┘

         │
         ▼
┌──────────────────┐
│   Node 4 (Future)│  ◄── AI Core (LLM orchestration)
│   Railway/GCP    │
│                  │
│ • OpenAI         │
│ • Anthropic      │
│ • Gemini         │
│ • Risk scoring   │
│ • Governance AI  │
└──────────────────┘
```

---

## Secrets Policy

**CRITICAL SECURITY REQUIREMENT**: All secrets and sensitive credentials must be distributed according to this policy:

### Secrets Distribution by Node

**Node 1 (Master) - Full Secrets Access**:
- ✅ AI Provider API Keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY)
- ✅ Cross-Chain RPC URLs with authentication
- ✅ BTC Hot Wallet Private Keys (for bridge operations)
- ✅ ADMIN_SECRET (shared with all nodes)

**Node 2 (Replica) - Minimal Secrets**:
- ✅ ADMIN_SECRET only (shared with all nodes)
- ✅ Cross-Chain RPC URLs (read-only, if needed for monitoring)
- ❌ NO AI provider API keys
- ❌ NO private keys for write operations

**Node 3 (Vercel) - No Secrets**:
- ❌ NO secrets whatsoever (public static site)
- ✅ Only public environment variables (NEXT_PUBLIC_*)

**Node 4 (AI Core) - AI Secrets Only**:
- ✅ AI Provider API Keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY)
- ✅ ADMIN_SECRET (shared with all nodes)
- ❌ NO blockchain private keys
- ❌ NO cross-chain RPC credentials

### Summary

**All secrets (AI keys, BTC hot wallets, etc.) live only on Node 1 and Node 4.**

- Node 1: Blockchain secrets + AI fallback
- Node 4: AI secrets only
- Node 2: ADMIN_SECRET only
- Node 3: No secrets

This ensures:
1. **Principle of Least Privilege**: Each node only has credentials needed for its role
2. **Blast Radius Reduction**: Compromise of Node 2 or Node 3 does not expose AI keys or hot wallets
3. **Clear Separation of Concerns**: AI operations isolated to Node 4, blockchain operations to Node 1

---

## Role-Based Code Patterns

### Helper Functions

```python
# In server.py or a shared config module

def is_master():
    """Check if current node is master"""
    return os.getenv("NODE_ROLE", "master") == "master"

def is_replica():
    """Check if current node is replica"""
    return os.getenv("NODE_ROLE") == "replica"

def is_ai_core():
    """Check if current node is AI core"""
    return os.getenv("NODE_ROLE") == "ai-core"

def should_run_schedulers():
    """Check if schedulers should run on this node"""
    return is_master() and os.getenv("SCHEDULER_ENABLED", "1") == "1"

def should_sync_ai_models():
    """Check if AI model sync should run on this node"""
    return is_master() and os.getenv("OPENAI_API_KEY")
```

### Conditional Initialization

```python
# AI model sync (master only)
if is_master() and os.getenv("OPENAI_API_KEY"):
    refresh_model_catalog(force=True)
    _start_model_scheduler()
else:
    print(f"[AI] Skipping model sync on {NODE_ROLE} node")

# Schedulers (master only)
if should_run_schedulers():
    start_schedulers()
else:
    print(f"[SCHEDULER] Disabled on {NODE_ROLE} node")

# AI wallet (master only)
if is_master():
    ensure_ai_wallet()
    initialize_voting()
    prune_empty_sessions()
```

---

## Troubleshooting

### Node 2 Issues

**Problem**: `OpenAI model sync failed on replica nodes`
**Solution**: AI model sync should be disabled on Node 2. Check that:
- `NODE_ROLE=replica` is set
- Startup code skips `refresh_model_catalog()` on replicas

**Problem**: `Heartbeat 502 when contacting the master`
**Solution**: Check that:
- `MASTER_NODE_URL` points to Node 1's base URL (not a heavy endpoint)
- Master node's `/api/peers/heartbeat` endpoint is accessible
- Heartbeat failures log warnings but don't crash the process

### Node 3 Issues

**Problem**: SDK files return 502 errors (`wallet_sdk.js`, `wallet_auth.js`)
**Solution**: Check that:
- Files exist in `/public/` directory for Vercel
- Vercel build includes static assets
- No dynamic routes are used for SDK files

**Problem**: `ReferenceError: openHeaderWalletModal is not defined`
**Solution**: Check that:
- `wallet_sdk.js` is loaded before any onclick handlers
- Global function is defined in a script loaded in `<head>` or early in `<body>`
- Browser console shows successful file load (200 OK)

---

## Security Considerations

1. **Shared Secrets**: `ADMIN_SECRET` must be identical across Node 1 and Node 2
2. **API Keys**: Only Node 1 (and future Node 4) should have AI provider API keys
3. **Read-Only Protection**: Node 2 must enforce `READ_ONLY=1` for all write operations
4. **Heartbeat Authentication**: Consider adding HMAC signatures to heartbeat payloads
5. **Cross-Chain Security**: BTC hot wallet private keys must be encrypted at rest

---

## Future Enhancements

- [ ] Migrate AI operations from Node 1 to Node 4
- [ ] Add BLS signature aggregation for multi-node consensus
- [ ] Implement Redis pub/sub for real-time node communication
- [ ] Add Prometheus metrics for node health monitoring
- [ ] Deploy Node 4 on dedicated GPU instance for AI workloads

---

## References

- [NODE3_DEPLOYMENT.md](./NODE3_DEPLOYMENT.md) – Node 3 wallet history microservice
- [AGENTS.md](./AGENTS.md) – AI agents and LLM integration
- [README.md](./README.md) – Main project documentation
- [governance/](./governance/) – Governance and PYTHEIA reports
