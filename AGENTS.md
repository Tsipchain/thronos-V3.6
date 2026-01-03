# Thronos AI Agent Architecture

**Version**: 1.0.0
**Last Updated**: 2026-01-03
**Maintainer**: Thronos Dev Team

## Overview

This document maps all AI agents, services, and workers in the Thronos V3.6 ecosystem. It identifies active vs. deprecated components, dependencies, testing procedures, and monitoring requirements.

---

## Active Agents & Services

### 1. **AI Chat Agent** (Production)

**Purpose**: Provides conversational AI interface for users
**Location**: `server.py` (routes: `/api/ai/providers/chat`, `/chat`)
**Templates**: `templates/chat.html`
**Dependencies**:
- LLM Router (`ai/llm_router.py`)
- Provider helpers: `ai/providers/openai_helper.py`, `ai/providers/anthropic_helper.py`, `ai/providers/gemini_helper.py`
- AI Interaction Ledger (`ai_interaction_ledger.py`)
- Session storage (localStorage + server-side JSON)

**Environment Variables**:
```bash
OPENAI_API_KEY          # Optional: OpenAI provider
ANTHROPIC_API_KEY       # Optional: Anthropic provider
GOOGLE_API_KEY          # Optional: Google Gemini provider
THRONOS_AI_MODE         # "all" | "openai" | "anthropic" | "google"
```

**Routes**:
- `GET /chat` - Render chat interface
- `POST /api/ai/providers/chat` - Send message, get AI response
- `GET /api/ai/sessions` - List chat sessions
- `POST /api/ai/sessions` - Create new session
- `GET /api/ai/sessions/<id>/messages` - Get session messages
- `POST /api/ai/feedback` - Record thumbs up/down feedback
- `GET /api/ai/models` - List available models (dynamic discovery)

**How to Test**:
```bash
# Start server
python3 server.py

# Visit http://localhost:5000/chat
# Send test message
# Verify response from AUTO router
# Test specific model selection
# Verify session persistence after refresh
```

**Active**: ✅ Yes
**Production Ready**: ✅ Yes
**Known Issues**: See governance/PYTHEIA_REPORT_E_chat_issues.md

---

### 2. **Architect Agent** (Production)

**Purpose**: Generates software architecture from blueprints and user specs
**Location**: `server.py` (routes: `/api/architect_generate`, `/architect`)
**Templates**: `templates/architect.html`
**Dependencies**:
- LLM Router (`ai/llm_router.py`)
- Blueprint loader (`/app/data/ai_blueprints/`)
- File generation utilities
- Same AI providers as Chat Agent

**Environment Variables**: Same as Chat Agent

**Routes**:
- `GET /architect` - Render architect interface
- `POST /api/architect_generate` - Generate architecture from blueprint + spec
- `GET /api/ai_blueprints` - List available blueprints

**How to Test**:
```bash
# Visit http://localhost:5000/architect
# Select blueprint (e.g., "SaaS Platform")
# Enter custom specs
# Click "Generate Architecture"
# Verify generated files and download ZIP
```

**Active**: ✅ Yes
**Production Ready**: ✅ Yes
**Known Issues**: Model dropdown may show degraded mode when providers unavailable

---

### 3. **PYTHEIA Worker** (Node3) (New)

**Purpose**: Inline system health monitor, auto-generates PYTHEIA_ADVICE
**Location**: `pytheia_worker.py`
**Dependencies**:
- `requests` library
- Access to all health check endpoints
- Write access to `data/pytheia_state.json` and `governance/`

**Environment Variables**:
```bash
PYTHEIA_BASE_URL="http://localhost:5000"  # Server base URL
PYTHEIA_CHECK_INTERVAL="300"              # Check interval in seconds (default: 5 min)
PYTHEIA_STATE_FILE="data/pytheia_state.json"  # State persistence file
```

**Monitored Endpoints**:
- `/chat` - Chat page health
- `/architect` - Architect page health
- `/api/ai/models` - Models API health (detects degraded mode)
- `/api/bridge/status` - Bridge status
- `/tokens` - Token explorer
- `/nft` - NFT marketplace
- `/governance` - Governance page
- `/wallet_viewer` - Wallet viewer

**How to Run**:
```bash
# Standalone mode
python3 pytheia_worker.py

# As scheduled job (TODO: integrate with APScheduler in server.py)
# from pytheia_worker import PYTHEIAWorker
# worker = PYTHEIAWorker()
# scheduler.add_job(worker.run_cycle, 'interval', seconds=300)
```

**How to Test**:
```bash
# Run one cycle
python3 pytheia_worker.py &
sleep 10
tail -f logs/pytheia_worker.log

# Verify health checks run
# Check governance/ for generated advice files
# Verify posts to /api/governance/pytheia/advice
```

**Active**: ✅ Yes
**Production Ready**: ⚠️ Ready but needs APScheduler integration
**Known Issues**: None

---

### 4. **Quorum Agent** (Production)

**Purpose**: BLS signature aggregation for quorum consensus
**Location**: `quorum_agent.py`, `quorum_consensus_bls.py`
**Dependencies**:
- BLS signature library
- Network consensus protocol

**Environment Variables**: None

**Routes**: N/A (consensus layer, not HTTP)

**How to Test**:
```bash
python3 quorum_agent.py
# Verify signature aggregation
# Check consensus participation
```

**Active**: ✅ Yes
**Production Ready**: ✅ Yes
**Known Issues**: None

---

### 5. **Watchers Service** (Production)

**Purpose**: Monitors blockchain events, BTC bridge, price oracles
**Location**: `watchers_service.py`, `binance_btc_watcher.py`, `btc_watcher_wrapped_thr.py`
**Dependencies**:
- Binance API (for BTC price)
- Bitcoin RPC (for bridge monitoring)
- THR blockchain RPC

**Environment Variables**:
```bash
BINANCE_API_KEY      # Binance price oracle
BINANCE_API_SECRET
BTC_RPC_URL          # Bitcoin node for bridge
BTC_RPC_USER
BTC_RPC_PASSWORD
```

**How to Test**:
```bash
python3 watchers_service.py &
tail -f logs/watchers.log

# Verify BTC price updates
# Check bridge event detection
```

**Active**: ✅ Yes
**Production Ready**: ✅ Yes
**Known Issues**: None

---

### 6. **AI Agent Service** (Experimental)

**Purpose**: Autonomous agent for onchain AI developer tasks
**Location**: `ai_agent_service.py`, `onchain_ai_developer.py`
**Dependencies**:
- LLM Router
- Smart contract compiler (`evm_solidity_compiler.py`)
- Blockchain write access

**Environment Variables**: Same as Chat Agent + blockchain access

**Status**: ⚠️ Experimental
**Production Ready**: ❌ No
**Known Issues**: Needs testing, security review

---

## Deprecated / Inactive Agents

### 1. **agent_prototype.py** (Deprecated)

**Status**: 🗑️ Deprecated
**Location**: `addons/ai_agent/agent_prototype.py`
**Reason**: Replaced by AI Agent Service
**Action**: Archive or remove

---

### 2. **Autonomous Trading** (Disabled by Default)

**Status**: ⚠️ Disabled
**Location**: `autonomous_trading.py`
**Reason**: High risk, needs manual approval
**Environment Flag**: `ENABLE_AUTONOMOUS_TRADING=false`
**Action**: Keep code but disabled by default

---

## Support Services

### AI Model Registry (`llm_registry.py`)

**Purpose**: Central registry of all AI models across providers
**Status**: ✅ Active
**Used By**: Chat Agent, Architect Agent, AI Agent Service

### AI Interaction Ledger (`ai_interaction_ledger.py`, `ai/ai_ledger.py`)

**Purpose**: Tracks all AI interactions for billing, analytics, training
**Status**: ✅ Active
**Used By**: All AI agents

### AI Training Loop (`ai_training_loop.py`)

**Purpose**: Continuous learning from user feedback
**Status**: ⚠️ Experimental
**Production Ready**: ❌ No

### Thronos AI Scoring (`thronos_ai_scoring.py`)

**Purpose**: Quality scoring for AI responses
**Status**: ⚠️ Experimental
**Production Ready**: ❌ No

---

## Monitoring & Verification

### What PYTHEIA Worker Should Monitor

**Critical Endpoints** (check every 5 minutes):
- `/chat` - User-facing chat interface
- `/architect` - User-facing architect interface
- `/api/ai/models` - Model discovery (critical for UX)
- `/tokens` - Token explorer
- `/governance` - Governance interface

**Important Endpoints** (check every 15 minutes):
- `/api/bridge/status` - BTC bridge health
- `/nft` - NFT marketplace
- `/wallet_viewer` - Wallet functionality

**Telemetry** (collect every 5 minutes):
- Error counts from `logs/server.log`
- AI Interaction Ledger stats
- Degraded mode activations
- Provider availability

### How to Verify Agent is Running

**Chat Agent**:
```bash
curl http://localhost:5000/chat
# Should return HTML (status 200)
```

**Architect Agent**:
```bash
curl http://localhost:5000/architect
# Should return HTML (status 200)
```

**PYTHEIA Worker**:
```bash
ps aux | grep pytheia_worker
tail -f logs/pytheia_worker.log
# Should see health check cycles every 5 minutes
```

**Watchers Service**:
```bash
ps aux | grep watchers_service
tail -f logs/watchers.log
# Should see BTC price updates
```

---

## Quick Reference Table

| Agent | File | Routes | Env Flags | Status | Production |
|-------|------|--------|-----------|--------|------------|
| Chat Agent | server.py:10496+ | `/chat`, `/api/ai/providers/chat` | AI keys | ✅ Active | ✅ Yes |
| Architect | server.py:* | `/architect`, `/api/architect_generate` | AI keys | ✅ Active | ✅ Yes |
| PYTHEIA Worker | pytheia_worker.py | N/A | `PYTHEIA_*` | ✅ Active | ⚠️ Needs integration |
| Quorum Agent | quorum_agent.py | N/A | None | ✅ Active | ✅ Yes |
| Watchers | watchers_service.py | N/A | Binance, BTC RPC | ✅ Active | ✅ Yes |
| AI Agent Service | ai_agent_service.py | `/api/ai_agent/*` | AI keys | ⚠️ Experimental | ❌ No |
| Autonomous Trading | autonomous_trading.py | N/A | `ENABLE_AUTONOMOUS_TRADING` | 🚫 Disabled | ❌ No |
| agent_prototype | addons/ai_agent/agent_prototype.py | N/A | None | 🗑️ Deprecated | ❌ No |

---

## Integration Roadmap

### Short-term (Next Sprint)

1. **Integrate PYTHEIA Worker with APScheduler**
   - Add scheduled job in `server.py`
   - Run worker in background thread
   - Expose `/api/pytheia/status` endpoint

2. **Fix Chat Session Persistence** (See governance/PYTHEIA_REPORT_E_chat_issues.md)
   - Implement proper session reloading
   - Fix file upload processing

3. **Implement Learn-to-Earn Auto-Rewards** (See governance/PYTHEIA_REPORT_B_courses.md)
   - Auto-complete on passing quiz
   - Auto-mint L2E rewards

### Mid-term (Next Month)

1. **AI Agent Service Security Review**
   - Audit onchain_ai_developer.py
   - Limit execution permissions
   - Add approval workflows

2. **AI Training Loop Production Testing**
   - Verify feedback collection
   - Test model fine-tuning pipeline

### Long-term (Next Quarter)

1. **Autonomous Trading Enable (with DAO approval)**
   - Complete security audit
   - Implement kill switches
   - DAO vote required

---

## Appendix: Environment Variables Master List

```bash
# AI Providers (all optional)
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
THRONOS_AI_MODE=all  # all | openai | anthropic | google

# PYTHEIA Worker
PYTHEIA_BASE_URL=http://localhost:5000
PYTHEIA_CHECK_INTERVAL=300
PYTHEIA_STATE_FILE=data/pytheia_state.json

# Blockchain Watchers
BINANCE_API_KEY
BINANCE_API_SECRET
BTC_RPC_URL
BTC_RPC_USER
BTC_RPC_PASSWORD

# Feature Flags
ENABLE_AUTONOMOUS_TRADING=false
ENABLE_AI_TRAINING=false
```

---

**End of Document**
