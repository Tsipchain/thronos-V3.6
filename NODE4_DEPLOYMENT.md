# Node 4 Deployment Guide (AI Core on Render)

**Version**: 1.0.0
**Last Updated**: 2026-01-18
**Status**: Ready for deployment

---

## Overview

Node 4 is the **AI Core** – a dedicated service for all LLM operations (OpenAI, Anthropic, Gemini). It runs independently from the blockchain infrastructure and handles:

- `/api/ai/chat` – AI chat completions
- `/api/architect_generate` – AI Architect blueprint generation
- `/api/ai_models` – Available models list
- AI model catalog sync
- AI knowledge watcher
- AI rewards pool distribution

---

## Deployment Steps

### 1. Create Render Web Service

1. Go to https://render.com
2. Click "New +" → "Web Service"
3. Connect GitHub repository: `Tsipchain/thronos-V3.6`
4. Configure service:

```yaml
Name: thronos-v3-6
Branch: main
Root Directory: . (leave blank)
Runtime: Python 3
Build Command: pip install -r requirements.txt
Start Command: gunicorn server:app -b 0.0.0.0:$PORT --timeout 120 --workers 2
```

**Important**: Set workers to 2-4 (not more) to avoid concurrent API key usage limits.

---

### 2. Environment Variables

Add the following environment variables in Render dashboard:

#### Node Role Configuration
```bash
NODE_ROLE=ai_core
READ_ONLY=1
SCHEDULER_ENABLED=1
ENABLE_CHAIN=0
```

#### AI Mode
```bash
THRONOS_AI_MODE=production
```

#### AI Provider API Keys (REQUIRED)
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
```

#### Admin Secret (MUST match Node 1 and Node 2)
```bash
ADMIN_SECRET=<same-as-node1-and-node2>
```

#### Data Directory
```bash
DATA_DIR=/app/data
```

#### Optional: Performance Tuning
```bash
# AI pool distribution interval (minutes)
AI_POOL_DISTRIBUTION_INTERVAL=30

# Model refresh interval (seconds)
MODEL_REFRESH_INTERVAL_SECONDS=600
```

---

### 3. Get Node 4 URL

After deployment, Render will give you a public URL like:

```
https://thronos-v3-6.onrender.com
```

**Copy this URL** – you'll need it for Node 1 configuration.

---

### 4. Configure Node 1 (Railway)

Go to Railway dashboard → Node 1 service → Environment Variables

Add:

```bash
AI_CORE_URL=https://thronos-v3-6.onrender.com
```

**DO NOT change any other environment variables on Node 1.**

After adding `AI_CORE_URL`, Node 1 will automatically proxy AI requests to Node 4.

---

### 5. (Optional) Configure Node 2

If you want Node 2 to also proxy to Node 4 (instead of running local AI), add:

```bash
AI_CORE_URL=https://thronos-v3-6.onrender.com
```

**Note**: Node 2 already has `THRONOS_AI_MODE=worker` so it doesn't serve user-facing AI. This is optional.

---

## Verification

### 1. Check Node 4 Health

Visit:
```
https://thronos-v3-6.onrender.com/api/ai/providers/health
```

Expected response:
```json
{
  "openai": "ok",
  "anthropic": "ok",
  "google": "ok"
}
```

### 2. Check Node 4 Models

Visit:
```
https://thronos-v3-6.onrender.com/api/ai_models
```

Expected response:
```json
{
  "models": [...],
  "default_model_id": "gpt-4.1"
}
```

### 3. Check Node 1 Proxy

From thrchain.up.railway.app, open browser DevTools → Network tab

Visit `/chat` page and send a message

Look for API request to `/api/ai/chat`

Check Node 1 logs (Railway) for:
```
[AI_CORE] Proxying to https://thronos-v3-6.onrender.com/api/ai/chat
[AI_CORE] Successfully proxied /api/ai/chat to Node 4
```

### 4. Check Fallback

Temporarily stop Node 4 service on Render

Try sending a chat message from thrchain.up.railway.app

Node 1 should automatically fall back to local AI

Check Node 1 logs for:
```
[AI_CORE] Node 4 call failed, falling back to local AI
```

---

## Architecture Flow

```
┌──────────────────────────────────────────────────────────┐
│                    User Request                          │
│    https://thrchain.up.railway.app/chat                 │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│              Node 1 (Railway) - Master                   │
│                                                          │
│  1. Receives /api/ai/chat request                       │
│  2. Checks AI_CORE_URL is set                           │
│  3. Proxies to Node 4                                    │
│     - Headers: X-Admin-Secret                           │
│     - Timeout: 90s                                       │
│  4. If Node 4 fails → Fallback to local AI              │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│            Node 4 (Render) - AI Core                     │
│                                                          │
│  1. Validates X-Admin-Secret header                     │
│  2. Processes AI request locally                         │
│  3. Calls OpenAI/Anthropic/Gemini APIs                  │
│  4. Returns response to Node 1                           │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│              External AI Providers                       │
│   • OpenAI API (gpt-4.1, o3-mini)                       │
│   • Anthropic API (Claude 3.5 Sonnet)                   │
│   • Google Gemini API (Gemini 2.5 Flash/Pro)            │
└──────────────────────────────────────────────────────────┘
```

---

## Security

### Admin Secret

**CRITICAL**: `ADMIN_SECRET` must be:
- ✅ Identical on Node 1, Node 2, and Node 4
- ✅ Long and random (32+ characters)
- ✅ Kept secret (not in public repos)

Node 4 validates every request has the correct `X-Admin-Secret` header.

### API Keys

AI provider API keys (OpenAI, Anthropic, Google) are now:
- ✅ Only on Node 4 (not on Node 1/2)
- ✅ Isolated from blockchain infrastructure
- ❌ Never exposed to frontend

### Rate Limiting

Render may throttle requests. Consider:
- Using Render's paid plan for higher limits
- Implementing Redis-based rate limiting on Node 4
- Setting `--workers 2` (not more) to avoid API key conflicts

---

## Monitoring

### Render Dashboard

- **Metrics** tab: CPU, Memory, Response time
- **Logs** tab: Application logs, errors
- **Events** tab: Deployments, restarts

### Key Metrics to Watch

- **Response Time**: Should be < 5s for AI requests
- **Error Rate**: Should be < 1%
- **CPU Usage**: Should be < 80%
- **Memory Usage**: Should be < 512MB

### Alerts

Set up Render alerts for:
- Service down
- High error rate (> 5%)
- High response time (> 10s)

---

## Troubleshooting

### Problem: Node 4 returns 403 errors

**Solution**: Check `ADMIN_SECRET` matches on Node 1 and Node 4

```bash
# On Railway (Node 1)
echo $ADMIN_SECRET

# On Render (Node 4)
echo $ADMIN_SECRET
```

### Problem: Node 4 returns 503 "AI Agent not available"

**Solution**: Check AI provider API keys are set

```bash
# On Render (Node 4)
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY
echo $GOOGLE_API_KEY
```

### Problem: Timeout errors from Node 1

**Solution**: Increase timeout in Node 1 code (already set to 90s for chat, 120s for architect)

Or check Render logs for slow AI provider responses

### Problem: Node 1 always uses fallback

**Solution**: Check `AI_CORE_URL` is set correctly on Node 1

```bash
# On Railway (Node 1)
echo $AI_CORE_URL
# Should be: https://thronos-v3-6.onrender.com
```

### Problem: Node 4 scheduler errors

**Solution**: Check `ENABLE_CHAIN=0` is set on Node 4

Node 4 should NOT run blockchain jobs (mint_first_blocks, confirm_mempool, etc.)

---

## Cost Optimization

### Render Free Tier

Render free tier includes:
- ✅ 750 hours/month
- ✅ Automatic sleep after 15 min inactivity
- ✅ Free SSL certificate
- ❌ Spins down when inactive (cold start delay)

### Paid Plan ($7/month)

Consider upgrading if:
- Cold starts are unacceptable
- Need > 750 hours/month
- Need higher rate limits

### Alternative: Railway

If Render is too slow, consider deploying Node 4 on Railway:

```bash
NODE_ROLE=ai_core
ENABLE_CHAIN=0
SCHEDULER_ENABLED=1
# ... same env vars as Render
```

---

## Rollback Plan

If Node 4 deployment fails or causes issues:

1. **Remove AI_CORE_URL from Node 1**
   ```bash
   # On Railway (Node 1)
   # Delete AI_CORE_URL environment variable
   ```

2. **Restore AI keys on Node 1** (if removed)
   ```bash
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GOOGLE_API_KEY=...
   ```

3. **Restart Node 1** service on Railway

Node 1 will fall back to local AI handling (same as before Node 4).

---

## Next Steps

1. ✅ Deploy Node 4 on Render
2. ✅ Set environment variables
3. ✅ Get public URL
4. ✅ Add `AI_CORE_URL` to Node 1
5. ✅ Test AI chat from thrchain.up.railway.app
6. ✅ Monitor Render logs and metrics
7. ⏳ (Optional) Remove AI keys from Node 1 after confirming Node 4 works
8. ⏳ (Optional) Deploy Node 4 on Railway if Render is slow

---

## References

- [INFRA_ROLES.md](./INFRA_ROLES.md) – Multi-node architecture
- [AI_CORE.md](./AI_CORE.md) – AI Core architecture and migration plan
- [Render Documentation](https://render.com/docs)
- [Gunicorn Documentation](https://docs.gunicorn.org/)

---

**Questions?** Check logs or contact dev team.
