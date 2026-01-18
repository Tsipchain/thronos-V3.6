# Node 3 Deployment Guide

## Purpose
Node 3 is configured as a **static CDN for wallet SDK and assets** deployed on Vercel. It serves wallet JavaScript SDK files, images, and documentation with zero backend processing.

## Architecture

```
┌─────────────────────────┐
│   Node 1 (Master)       │  ← Blockchain operations, mining, consensus
│   thrchain.up.railway   │     Wallet backend, AI (fallback)
└─────────────────────────┘

┌─────────────────────────┐
│   Node 2 (Replica)      │  ← Read-only replica, cross-chain bridge
│   node-2.up.railway     │     BTC/ETH/BSC/XRP monitoring
└─────────────────────────┘

┌─────────────────────────┐
│   Node 3 (Static CDN)   │  ← Wallet SDK files, images, docs
│   thrchain.vercel.app   │     No backend, pure static assets
└─────────────────────────┘

┌─────────────────────────┐
│   Node 4 (AI Core)      │  ← AI model catalog, chat, architect
│   thronos-v3-6.onrender │     Offloads AI from Node 1 (passive)
└─────────────────────────┘
```

## Node 3 Configuration

### Vercel Deployment

**Platform**: Vercel (Static Site Hosting)
**URL**: `https://thrchain.vercel.app`
**Root Directory**: `public/`
**Build Command**: `echo 'Static site - no build needed'`
**Output Directory**: `.`

### Environment Variables

Node 3 has **NO backend secrets**. Only public environment variables:

```bash
# Public environment variables only (NEXT_PUBLIC_* prefix)
NEXT_PUBLIC_API_BASE_URL=https://thrchain.up.railway.app
NEXT_PUBLIC_NODE2_URL=https://node-2.up.railway.app
NEXT_PUBLIC_CHAIN_NAME=Thronos
```

**Security Note**: Never add `ADMIN_SECRET`, `OPENAI_API_KEY`, or any private keys to Vercel.

### Static Files Served

Node 3 serves these files via CDN:

#### 1. Wallet SDK Files
```
/static/wallet_sdk.js         - Main wallet SDK (5.6 KB)
/static/wallet_auth.js        - Authentication helpers (6.3 KB)
/static/wallet_session.js     - Session management (5.3 KB)
/static/music_module.js       - Music streaming module (8.7 KB)
```

#### 2. Images & Assets
```
/static/img/thronos-token.png - Thronos logo
/static/img/token_logos/      - Token logo directory
```

#### 3. Landing Page
```
/index.html                   - SDK landing page with links
```

### Usage from Node 1 Templates

All script tags in `templates/base.html` should reference Node 3 CDN:

```html
<!-- Wallet SDK from Node 3 CDN -->
<script src="https://thrchain.vercel.app/static/wallet_sdk.js"></script>
<script src="https://thrchain.vercel.app/static/wallet_auth.js"></script>
<script src="https://thrchain.vercel.app/static/wallet_session.js"></script>
<script src="https://thrchain.vercel.app/static/music_module.js"></script>
```

**Benefits**:
- ✅ Fast global CDN delivery
- ✅ Offloads static asset traffic from Node 1
- ✅ No 502 errors from backend overload
- ✅ Browser caching (immutable assets)

## Vercel Deployment Steps

### Step 1: Connect Repository to Vercel

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Click "Add New" → "Project"
3. Import the `Tsipchain/thronos-V3.6` repository
4. Configure project settings:

### Step 2: Project Settings

**Framework Preset**: Other (Static Site)
**Root Directory**: `public`
**Build Command**: `echo 'Static site - no build needed'`
**Output Directory**: `.`

### Step 3: Environment Variables

Add these public environment variables in Vercel dashboard:

```bash
NEXT_PUBLIC_API_BASE_URL=https://thrchain.up.railway.app
NEXT_PUBLIC_NODE2_URL=https://node-2.up.railway.app
NEXT_PUBLIC_CHAIN_NAME=Thronos
```

### Step 4: Deploy

1. Click "Deploy"
2. Vercel will build and deploy to `https://thrchain.vercel.app`
3. Verify static files are accessible:
   - https://thrchain.vercel.app/index.html
   - https://thrchain.vercel.app/static/wallet_sdk.js
   - https://thrchain.vercel.app/static/wallet_auth.js

### Step 5: API Proxy Configuration (Optional)

The `vercel.json` file in `/public/` includes API proxying:

```json
{
  "version": 2,
  "buildCommand": "echo 'Static site - no build needed'",
  "outputDirectory": ".",
  "rewrites": [
    {
      "source": "/api/v1/write/:path*",
      "destination": "https://thrchain.up.railway.app/api/:path*"
    },
    {
      "source": "/api/v1/read/:path*",
      "destination": "https://node-2.up.railway.app/api/:path*"
    },
    { "source": "/api/:path*", "destination": "https://node-2.up.railway.app/api/:path*" },
    { "source": "/viewer", "destination": "https://node-2.up.railway.app/viewer" },
    { "source": "/wallet", "destination": "https://thrchain.up.railway.app/wallet" }
  ],
  "headers": [
    {
      "source": "/static/(.*)",
      "headers": [
        {
          "key": "Cache-Control",
          "value": "public, max-age=31536000, immutable"
        },
        {
          "key": "Access-Control-Allow-Origin",
          "value": "*"
        }
      ]
    }
  ]
}
```

**What this does**:
- `/static/*` → Served directly from Vercel CDN (fast, cached)
- `/api/*` → Proxied to Node 2 (read operations)
- `/api/v1/write/*` → Proxied to Node 1 (write operations)
- `/wallet` → Proxied to Node 1 (wallet backend)
- `/viewer` → Proxied to Node 2 (wallet viewer)

## Performance Benefits

### Before (All Assets from Node 1)
- Static JS files served from Node 1 backend
- Competes with blockchain operations for bandwidth
- No CDN caching
- Potential 502 errors during high load
- Slower international users

### After (CDN Architecture)
- **Node 1**: Core blockchain, mining, consensus
- **Node 2**: Multi-chain bridge RPC, read-only queries
- **Node 3**: Wallet SDK + static assets (global CDN)
- **Node 4**: AI operations (passive, graceful degradation)
- Static assets cached globally (Vercel edge network)
- **Faster** page loads worldwide
- **No 502 errors** from static asset requests

## Testing

### Test Node 3 Static Files
```bash
# Landing page
curl https://thrchain.vercel.app/

# Wallet SDK
curl https://thrchain.vercel.app/static/wallet_sdk.js

# Authentication helper
curl https://thrchain.vercel.app/static/wallet_auth.js

# Session management
curl https://thrchain.vercel.app/static/wallet_session.js

# Music module
curl https://thrchain.vercel.app/static/music_module.js

# Verify headers (should include Cache-Control)
curl -I https://thrchain.vercel.app/static/wallet_sdk.js
```

**Expected Response**: 200 OK with valid JavaScript content and CORS headers

### Test API Proxy (Optional)
```bash
# API calls proxied to Node 2
curl "https://thrchain.vercel.app/api/wallet/balances?address=THR123..."

# Wallet viewer proxied to Node 1
curl "https://thrchain.vercel.app/wallet?address=THR123..."
```

## Monitoring

### Vercel Analytics

Monitor Node 3 performance in Vercel dashboard:

1. Go to Vercel Dashboard → Project → Analytics
2. Check:
   - **Request Count**: Number of static file requests
   - **Bandwidth**: Data transferred
   - **Cache Hit Rate**: Should be >90% for static assets
   - **Error Rate**: Should be <0.1%
   - **Top Files**: Most requested assets

### Key Metrics

- **Static asset latency**: <50ms (global CDN)
- **Cache hit rate**: >90% (immutable assets)
- **Availability**: 99.99% (Vercel SLA)

## Troubleshooting

### Issue: 404 errors for /static/* files
**Solution**:
1. Check that files exist in `public/static/` directory
2. Verify Vercel build succeeded
3. Check Root Directory is set to `public`

### Issue: CORS errors when loading SDK from Node 1
**Solution**:
Ensure `vercel.json` includes CORS headers:
```json
{
  "headers": [
    {
      "source": "/static/(.*)",
      "headers": [
        {
          "key": "Access-Control-Allow-Origin",
          "value": "*"
        }
      ]
    }
  ]
}
```

### Issue: Outdated JS files being served
**Solution**:
1. Vercel automatically invalidates cache on new deployments
2. If manual cache clear needed, redeploy the project
3. Check browser dev tools for correct file versions

### Issue: Failed to load resource: 502
**Solution**:
This should NOT happen with Node 3 (static CDN). If it does:
1. Check Vercel status page
2. Verify domain DNS is pointing to Vercel
3. Check deployment logs for errors

## Summary

✅ **Node 3 Role**: Static CDN for wallet SDK and assets
✅ **Platform**: Vercel (global edge network)
✅ **Primary Files**: wallet_sdk.js, wallet_auth.js, wallet_session.js, music_module.js
✅ **Benefits**: Global CDN delivery, no backend load, immutable caching, 99.99% uptime
✅ **Security**: No secrets, no backend processing, pure static assets

---

## Multi-Node Architecture

For the complete multi-node architecture and environment variable specifications, see:

📖 **[INFRA_ROLES.md](./INFRA_ROLES.md)** – Node roles, responsibilities, and configuration

### Quick Reference: Node Environment Expectations

**Node 1 (Master)** – `thrchain.up.railway.app`
```bash
NODE_ROLE=master
READ_ONLY=0
SCHEDULER_ENABLED=1
OPENAI_API_KEY=sk-...        # AI provider keys
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
```

**Node 2 (Replica)** – `node-2.up.railway.app`
```bash
NODE_ROLE=replica
READ_ONLY=1
SCHEDULER_ENABLED=0           # No schedulers on replica
MASTER_NODE_URL=https://thrchain.up.railway.app
BTC_RPC_URL=...               # Cross-chain bridge config
ETH_RPC_URL=...
BSC_RPC_URL=...
```

**Node 3 (Static/SDK)** – `thrchain.vercel.app`
```bash
# Public-only environment (no secrets)
NEXT_PUBLIC_API_BASE_URL=https://thrchain.up.railway.app
```

**Node 4 (Future AI Core)** – `TBD`
```bash
NODE_ROLE=ai-core
OPENAI_API_KEY=sk-...         # AI keys moved from Node 1
ANTHROPIC_API_KEY=sk-ant-...
AI_CORE_PORT=8001
```

### Important Notes

⚠️ **Node 2 Behavior**:
- **NO AI KEYS** on Node 2 - all AI processing happens on Node 1 or Node 4
- Node 2 is read-only (cross-chain bridge monitoring only)
- Heartbeat failures log warnings but **DO NOT** crash the process
- Stratum mining does **NOT** run on Node 2 (master only)

⚠️ **Node 3 Security**:
- Never deploy secrets (API keys, ADMIN_SECRET) to Vercel
- All assets served via CDN (no backend processing)
- Pure static site - no Python, no database, no blockchain operations

⚠️ **Node 4 Behavior** (Passive AI Core):
- If Node 4 is down, AI chat fails gracefully but **wallet, mining, and chain continue to operate**
- Node 1 has AI keys as fallback
- Node 4 runs **NO blockchain operations** (ENABLE_CHAIN=0)

✅ **Clean Separation**:
- Node 1 = blockchain coordinator + AI fallback
- Node 2 = cross-chain watchers (read-only)
- Node 3 = static SDK/docs (Vercel CDN)
- Node 4 = AI core (passive, graceful degradation)

---

**Questions?** Check main documentation or contact the dev team.
