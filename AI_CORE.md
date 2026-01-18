# AI Core Architecture (Node 4)

**Version**: 1.0.0
**Status**: 🚧 Planned (not yet deployed)
**Last Updated**: 2026-01-18

---

## Overview

The **AI Core** (future Node 4) will be a dedicated service for all LLM operations, AI model management, and AI-driven features in the Thronos ecosystem. This document outlines the migration plan to move AI responsibilities from Node 1 (master) to a specialized AI Core node.

---

## Current State (Before Node 4)

### Current AI Responsibilities on Node 1

Node 1 (master blockchain node) currently handles:

✅ AI model catalog sync (OpenAI, Anthropic, Gemini)
✅ AI chat endpoint (`/chat`, `/api/ai/providers/chat`)
✅ AI architect endpoint (`/architect`, `/api/architect_generate`)
✅ AI interaction ledger (tracking all AI conversations)
✅ AI rewards pool distribution
✅ AI risk scoring (anti-Ponzi watcher)

### Current AI Providers

| Provider   | Environment Variable    | Default Model               |
|------------|-------------------------|----------------------------|
| OpenAI     | `OPENAI_API_KEY`        | `gpt-4.1-mini`             |
| Anthropic  | `ANTHROPIC_API_KEY`     | `claude-3.5-sonnet-latest` |
| Google     | `GOOGLE_API_KEY`        | `gemini-2.5-flash-latest`  |

### Current AI Mode Configuration

```python
# In server.py
THRONOS_AI_MODE = os.getenv("THRONOS_AI_MODE", "production" if NODE_ROLE == "master" else "worker").lower()
```

**Modes**:
- `production` – User-facing AI chat and architect (Node 1)
- `worker` – Background AI tasks (Node 2)
- `openai` / `anthropic` / `google` – Force specific provider

---

## Future State (After Node 4 Deployment)

### Node 4 Responsibilities

Node 4 (AI Core) will handle:

🎯 **AI Model Management**:
- Model catalog sync from OpenAI, Anthropic, Gemini
- Model health checks and failover
- Model performance monitoring

🎯 **LLM Operations**:
- Chat completions (`/api/ai/chat`)
- Architect blueprint generation (`/api/ai/architect`)
- Image generation (DALL-E, Stable Diffusion)
- Code generation and analysis

🎯 **AI Scoring & Analytics**:
- Risk scoring for anti-Ponzi watcher
- Sentiment analysis for governance proposals
- AI-driven market predictions

🎯 **L2 Game Logic**:
- Crypto Hunters AI NPCs
- Dynamic quest generation
- AI-driven game economy balancing

🎯 **AI Rewards & Incentives**:
- AI interaction ledger
- AI rewards pool calculations
- Quality scoring for AI contributions

---

## Architecture Diagram

### Before Node 4

```
┌──────────────────────────────────────────┐
│         Node 1 (Master)                  │
│  ┌────────────────────────────────────┐  │
│  │  Blockchain + AI (mixed)           │  │
│  │  • Block production                │  │
│  │  • AI model sync ⚠️                │  │
│  │  • AI chat ⚠️                      │  │
│  │  • Risk scoring ⚠️                 │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### After Node 4

```
┌─────────────────────────┐      ┌─────────────────────────┐
│   Node 1 (Master)       │      │   Node 4 (AI Core)      │
│  ┌───────────────────┐  │      │  ┌───────────────────┐  │
│  │  Blockchain Only  │──┼──────┼─▶│  AI Operations    │  │
│  │  • Block prod.    │  │ HTTP │  │  • Model sync     │  │
│  │  • Consensus      │  │      │  │  • LLM calls      │  │
│  │  • Smart contracts│  │      │  │  • Risk scoring   │  │
│  └───────────────────┘  │      │  └───────────────────┘  │
└─────────────────────────┘      └─────────────────────────┘
         │                                  │
         │                                  │
         ▼                                  ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│   Node 2 (Replica)      │      │   External AI APIs      │
│  • Cross-chain bridge   │      │  • OpenAI               │
│  • Watchers             │      │  • Anthropic            │
└─────────────────────────┘      │  • Google Gemini        │
                                 └─────────────────────────┘
```

---

## Migration Plan

### Phase 1: Preparation

**Status**: ✅ **COMPLETE** (2026-01-18)

- [x] Add `AI_CORE_URL` environment variable to server.py
- [x] Create `call_ai_core()` helper function for HTTP calls to Node 4
- [x] Add role-based guards: `is_ai_core()`, `should_run_schedulers()`, `should_sync_ai_models()`
- [x] Add `ENABLE_CHAIN` flag to disable blockchain on AI Core
- [x] Document AI Core architecture (this file)
- [x] Update INFRA_ROLES.md with Node 4 specifications
- [x] Create NODE4_DEPLOYMENT.md deployment guide

### Phase 2: Deploy Node 4 (Standalone)

**Status**: ✅ **READY FOR DEPLOYMENT** (see [NODE4_DEPLOYMENT.md](./NODE4_DEPLOYMENT.md))

1. **Create AI Core Service**:
   ```bash
   # New repository or dedicated directory
   ai-core/
   ├── server.py          # Flask/FastAPI service
   ├── requirements.txt   # AI-specific dependencies
   ├── llm_router.py      # LLM provider routing
   ├── model_sync.py      # Model catalog management
   └── health_check.py    # Health monitoring
   ```

2. **Deploy to Railway/GCP**:
   ```bash
   # Environment variables
   NODE_ROLE=ai-core
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GOOGLE_API_KEY=...
   AI_CORE_PORT=8001
   ADMIN_SECRET=<shared-secret>
   ```

3. **Expose AI Endpoints**:
   - `POST /api/ai/chat` – Chat completions
   - `POST /api/ai/architect` – Blueprint generation
   - `POST /api/ai/risk-score` – Anti-Ponzi risk scoring
   - `GET /api/ai/models` – Available models catalog
   - `GET /api/ai/health` – Health check

### Phase 3: Migrate Node 1 → Node 4

**Status**: ⏳ Planned

1. **Update Node 1 Configuration**:
   ```bash
   # Add to Node 1 environment
   AI_CORE_URL=https://ai-core.up.railway.app
   ```

2. **Update Node 1 Code**:
   ```python
   # In server.py - Replace direct LLM calls with AI Core calls

   # OLD (direct call)
   response = openai_helper.generate(prompt, model)

   # NEW (via AI Core)
   response = call_ai_core("/api/ai/chat", {
       "prompt": prompt,
       "model": model,
       "provider": "openai"
   })
   ```

3. **Remove AI Keys from Node 1**:
   ```bash
   # Node 1 no longer needs these
   # OPENAI_API_KEY (removed)
   # ANTHROPIC_API_KEY (removed)
   # GOOGLE_API_KEY (removed)
   ```

### Phase 4: Migrate Node 2 → Node 4

**Status**: ⏳ Planned

1. **Remove Unused AI Keys from Node 2**:
   ```bash
   # Node 2 currently has AI keys but doesn't use them
   # Remove these after Node 4 is live
   ```

2. **Update Cross-Chain Watchers**:
   - Anti-Ponzi watcher calls `/api/ai/risk-score` on Node 4
   - Price prediction calls `/api/ai/forecast` on Node 4

### Phase 5: Optimization & Monitoring

**Status**: ⏳ Planned

- [ ] Add Redis caching for AI responses
- [ ] Implement rate limiting per wallet address
- [ ] Monitor AI Core performance (latency, throughput)
- [ ] Set up alerts for AI provider failures
- [ ] Implement automatic failover between providers

---

## API Contract: Node 1 ↔ Node 4

### Authentication

All requests from Node 1/Node 2 to Node 4 must include:

```http
X-Admin-Secret: <ADMIN_SECRET>
Content-Type: application/json
```

### Endpoints

#### 1. Chat Completion

**Request**:
```http
POST /api/ai/chat
{
  "prompt": "Explain blockchain consensus",
  "model": "gpt-4.1-mini",
  "provider": "openai",
  "max_tokens": 1024,
  "temperature": 0.7,
  "wallet_address": "THR123...",  // Optional (for billing)
  "session_id": "sess_abc123"     // Optional (for context)
}
```

**Response**:
```json
{
  "ok": true,
  "content": "Blockchain consensus is...",
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 150,
    "total_tokens": 160
  },
  "model": "gpt-4.1-mini",
  "provider": "openai"
}
```

#### 2. Risk Scoring

**Request**:
```http
POST /api/ai/risk-score
{
  "wallet_address": "THR123...",
  "transaction_history": [...],
  "behavioral_patterns": {...}
}
```

**Response**:
```json
{
  "ok": true,
  "risk_score": 0.75,
  "risk_level": "high",
  "explanation": "Detected high-frequency trading with suspicious patterns",
  "recommended_action": "flag_for_review"
}
```

#### 3. Model Catalog

**Request**:
```http
GET /api/ai/models?provider=openai
```

**Response**:
```json
{
  "ok": true,
  "models": [
    {
      "id": "gpt-4.1",
      "label": "GPT-4.1 (OpenAI)",
      "provider": "openai",
      "default": true,
      "available": true
    }
  ]
}
```

---

## Environment Variables

### Node 4 (AI Core)

```bash
# ─── Node Role ─────────────────────────────────────────
NODE_ROLE=ai-core

# ─── AI Provider Keys ──────────────────────────────────
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# ─── AI Core Configuration ─────────────────────────────
AI_CORE_PORT=8001
AI_CORE_HOST=0.0.0.0
AI_CORE_ALLOWED_ORIGINS=https://thrchain.up.railway.app,https://node-2.up.railway.app

# ─── Admin & Security ──────────────────────────────────
ADMIN_SECRET=<shared-secret>  # Must match Node 1 and Node 2

# ─── Model Configuration ───────────────────────────────
OPENAI_DEFAULT_MODEL=gpt-4.1-mini
ANTHROPIC_DEFAULT_MODEL=claude-3.5-sonnet-latest
GEMINI_DEFAULT_MODEL=gemini-2.5-flash-latest

# ─── Rate Limiting ─────────────────────────────────────
AI_RATE_LIMIT_PER_MINUTE=60
AI_RATE_LIMIT_PER_HOUR=1000

# ─── Caching ───────────────────────────────────────────
REDIS_URL=redis://...
AI_CACHE_TTL_SECONDS=3600

# ─── Monitoring ────────────────────────────────────────
SENTRY_DSN=https://...
LOG_LEVEL=INFO
```

### Node 1 (After Migration)

```bash
# Add AI Core URL
AI_CORE_URL=https://ai-core.up.railway.app

# Remove AI keys (moved to Node 4)
# OPENAI_API_KEY (removed)
# ANTHROPIC_API_KEY (removed)
# GOOGLE_API_KEY (removed)
```

---

## Implementation: call_ai_core() Helper

Already implemented in `server.py` (lines 507-532):

```python
def call_ai_core(path: str, payload: dict, timeout: int = 30) -> dict:
    """
    Call AI core service for LLM operations (future Node 4).

    Args:
        path: API endpoint path (e.g., "/api/chat")
        payload: Request payload
        timeout: Request timeout in seconds

    Returns:
        Response JSON

    Raises:
        RuntimeError: If AI_CORE_URL not configured
        requests.RequestException: If request fails
    """
    if not AI_CORE_URL:
        raise RuntimeError("AI_CORE_URL not configured. Set AI_CORE_URL environment variable.")

    url = f"{AI_CORE_URL.rstrip('/')}/{path.lstrip('/')}"
    response = requests.post(url, json=payload, timeout=timeout, headers={
        "X-Admin-Secret": ADMIN_SECRET,
        "Content-Type": "application/json"
    })
    response.raise_for_status()
    return response.json()
```

**Usage Example**:
```python
# In Node 1 - AI chat endpoint
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    prompt = data.get("prompt")
    model = data.get("model", "gpt-4.1-mini")

    # Call AI Core instead of direct LLM call
    result = call_ai_core("/api/ai/chat", {
        "prompt": prompt,
        "model": model,
        "wallet_address": data.get("wallet_address")
    })

    return jsonify(result), 200
```

---

## Benefits of AI Core Separation

### 1. **Performance**
- Dedicated resources for AI operations (GPU instances)
- No interference with blockchain consensus
- Independent scaling (scale AI horizontally)

### 2. **Security**
- AI API keys isolated from blockchain nodes
- Separate attack surface
- Easier to rotate credentials

### 3. **Cost Optimization**
- AI Core can use GPU instances (A100, H100)
- Node 1/2 use cheaper CPU instances
- Better resource utilization

### 4. **Maintainability**
- Clear separation of concerns
- Easier to update AI models without blockchain downtime
- Independent deployment pipelines

### 5. **Reliability**
- AI Core failure doesn't crash blockchain
- Graceful degradation (fallback to cached responses)
- Easier to implement failover strategies

---

## Testing Strategy

### Unit Tests
```python
# Test call_ai_core helper
def test_call_ai_core_success():
    response = call_ai_core("/api/ai/chat", {"prompt": "Hello"})
    assert response["ok"] is True
    assert "content" in response

def test_call_ai_core_no_url():
    with pytest.raises(RuntimeError, match="AI_CORE_URL not configured"):
        call_ai_core("/api/ai/chat", {})
```

### Integration Tests
```bash
# Test Node 1 → Node 4 communication
curl -X POST https://thrchain.up.railway.app/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Test", "wallet_address": "THR123"}'

# Verify request reaches Node 4
tail -f /var/log/ai-core.log
```

### Load Tests
```bash
# Simulate 100 concurrent AI requests
ab -n 1000 -c 100 -p payload.json \
  -T application/json \
  https://ai-core.up.railway.app/api/ai/chat
```

---

## Rollback Plan

If Node 4 deployment fails, rollback to Node 1 handling AI:

1. **Remove AI_CORE_URL** from Node 1 environment
2. **Restore AI API keys** to Node 1 environment
3. **Revert code changes** (use direct LLM calls)
4. **Restart Node 1** service

---

## References

- [INFRA_ROLES.md](./INFRA_ROLES.md) – Multi-node architecture
- [AGENTS.md](./AGENTS.md) – AI agents and LLM integration
- [server.py](./server.py) – Main server with `call_ai_core()` helper
- [ai/llm_router.py](./ai/llm_router.py) – LLM provider routing logic

---

## Next Steps

1. ✅ Document AI Core architecture (this file)
2. ✅ Add `call_ai_core()` helper to server.py
3. ⏳ Create AI Core service repository
4. ⏳ Deploy Node 4 to Railway/GCP
5. ⏳ Migrate endpoints from Node 1 to Node 4
6. ⏳ Remove AI keys from Node 1/2
7. ⏳ Monitor performance and optimize

---

**Questions?** See [INFRA_ROLES.md](./INFRA_ROLES.md) or contact the dev team.
