# Node 3 Deployment Guide

## Purpose
Node 3 is configured as a **microservice for wallet history** to offload heavy queries from the main server (Node 1).

## Architecture

```
┌─────────────────┐
│   Node 1 (Main) │  ← Blockchain operations, mining, consensus
│   Port: 5000    │
└─────────────────┘

┌─────────────────┐
│   Node 2 (RPC)  │  ← Multi-chain bridge (BTC, ETH, BNB, XRP)
│   + RPC URLs    │
└─────────────────┘

┌─────────────────┐
│ Node 3 (History)│  ← Wallet history API + SDKs + API docs
│   Port: 5002    │
└─────────────────┘
```

## Node 3 Configuration

### Environment Variables
```bash
# Railway Node 3 Environment
PORT=5002
DATA_DIR=/app/data

# Optional: Redis cache for performance
REDIS_URL=redis://...

# CORS for frontend
ALLOWED_ORIGINS=https://thronos.vercel.app,https://thrchain.up.railway.app
```

### Endpoints to Serve on Node 3

#### 1. Wallet History API (Primary)
```
GET /api/v2/wallet/history
```

**Purpose**: Serve wallet transaction history with pagination and filters.

**Query Parameters**:
- `address` (required): THR address
- `limit` (optional, default: 100, max: 500): Number of transactions
- `offset` (optional, default: 0): Skip first N transactions
- `category` (optional): Filter by category (mining, bridge, swap, etc.)
- `from_date` (optional): ISO timestamp filter
- `to_date` (optional): ISO timestamp filter

**Example**:
```bash
curl "https://node3.thrchain.railway.app/api/v2/wallet/history?address=THR123...&limit=50&offset=0"
```

**Response**:
```json
{
  "ok": true,
  "address": "THR123...",
  "transactions": [...],
  "total": 1234,
  "limit": 50,
  "offset": 0,
  "has_more": true,
  "endpoint": "v2",
  "node": "microservice-optimized"
}
```

#### 2. Additional Endpoints for Node 3

**SDK Documentation** (lightweight):
```
GET /api/docs
GET /api/sdk/javascript
GET /api/sdk/python
```

**Health Check**:
```
GET /health
GET /api/health
```

**Wallet Viewer Page**:
```
GET /wallet?address=THR...
```
Uses `wallet_viewer_standalone.html` (does NOT extend base.html)

## Railway Deployment

### Step 1: Configure Node 3 Service

1. Go to Railway → Node 3 Service
2. Add environment variables above
3. Set domain: `node3.thrchain.railway.app`

### Step 2: Update Main Server (Node 1) Proxy

Option A: **Vercel Proxy** (Recommended)

Update `vercel.json`:
```json
{
  "rewrites": [
    {
      "source": "/api/v2/wallet/:path*",
      "destination": "https://node3.thrchain.railway.app/api/v2/wallet/:path*"
    },
    {
      "source": "/api/:path*",
      "destination": "https://thrchain.up.railway.app/api/:path*"
    },
    {
      "source": "/(.*)",
      "destination": "https://thrchain.up.railway.app/$1"
    }
  ]
}
```

Option B: **Nginx Reverse Proxy**

```nginx
location /api/v2/wallet/ {
    proxy_pass https://node3.thrchain.railway.app/api/v2/wallet/;
    proxy_cache wallet_history_cache;
    proxy_cache_valid 200 60s;  # Cache for 60 seconds
}

location /api/ {
    proxy_pass https://thrchain.up.railway.app/api/;
}
```

### Step 3: Update Frontend (base.html)

**Current** (uses Node 1):
```javascript
const histRes = await fetch(`/api/wallet/history?address=${addr}`);
```

**Optimized** (uses Node 3 via proxy):
```javascript
const histRes = await fetch(`/api/v2/wallet/history?address=${addr}&limit=100`);
```

## Performance Benefits

### Before (Single Node)
- All requests → Node 1
- Wallet history queries compete with blockchain operations
- Slow page loads (~6,520 lines with base.html extension)
- Page transition delays

### After (Microservice Architecture)
- **Node 1**: Core blockchain, mining, consensus
- **Node 2**: Multi-chain bridge RPC
- **Node 3**: Wallet history + SDKs (this offloads Node 1)
- Wallet viewer: Standalone (300 lines vs 6,520)
- **10x faster** page transitions

## Testing

### Test Node 3 Directly
```bash
# Health check
curl https://node3.thrchain.railway.app/health

# Wallet history
curl "https://node3.thrchain.railway.app/api/v2/wallet/history?address=THR123...&limit=10"

# Wallet viewer page
curl "https://node3.thrchain.railway.app/wallet?address=THR123..."
```

### Test Through Vercel Proxy
```bash
curl "https://thronos.vercel.app/api/v2/wallet/history?address=THR123...&limit=10"
```

## Monitoring

### Key Metrics
- Request latency: Target < 200ms
- Cache hit rate: Target > 80%
- Error rate: Target < 1%

### Logs
```bash
# Railway CLI
railway logs --service node3

# Check for errors
railway logs --service node3 | grep "ERROR"
```

## Troubleshooting

### Issue: Node 3 stuck on Node 1
**Solution**: Update Vercel proxy configuration to route `/api/v2/wallet/*` to Node 3.

### Issue: Slow page transitions
**Solution**:
1. ✅ Use `wallet_viewer_standalone.html` (NOT extending base.html)
2. ✅ Route wallet history to Node 3
3. Enable caching on Node 3

### Issue: CORS errors
**Solution**: Add CORS headers in Node 3:
```python
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = 'https://thronos.vercel.app'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response
```

## Load Balancing (Future)

For high traffic, add multiple Node 3 instances:

```
Node 3a ─┐
Node 3b ─┼─ Load Balancer ─ /api/v2/wallet/*
Node 3c ─┘
```

## Summary

✅ **Node 3 Role**: Wallet history microservice + SDKs + API docs
✅ **Primary Endpoint**: `/api/v2/wallet/history`
✅ **Benefits**: Offloads main server, faster responses, better caching
✅ **Deployment**: Railway service with dedicated domain
✅ **Proxy**: Vercel routes `/api/v2/wallet/*` → Node 3

---

**Questions?** Check main documentation or contact the dev team.
