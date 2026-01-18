# Node 2 Deployment Fix - Railway Troubleshooting

## 🔴 Current Problem

Node 2 (node-2.up.railway.app) shows:
- **Status**: "Online" in Railway dashboard ✅
- **Actual**: 502 Bad Gateway error when accessing URL ❌
- **Logs**: HEARTBEAT timeout errors

**Root Cause**: Node 2 deployed with buggy heartbeat code that loads CHAIN_FILE every 30 seconds, causing memory/CPU overload.

---

## ✅ Fix Status

**Commit**: `311637d` - "fix: Remove expensive chain loading from heartbeat endpoint"
**Merged to main**: PR #263 at 2026-01-18 22:01:05 (10:01 PM local time)
**Status**: ✅ MERGED to main branch

---

## 🚀 Railway Deployment Options

### Option 1: Wait for Auto-Deploy (Recommended)
Railway should auto-deploy when it detects the new commit on main branch.

**Timeline**:
- Merge happened at: 10:01 PM
- Auto-deploy triggers: Usually within 1-5 minutes
- Deployment takes: ~2-3 minutes
- Total time: ~5-8 minutes from merge

**Check if deployed**:
1. Go to Railway dashboard → Node 2
2. Check "Deploy Logs" tab
3. Look for new deployment AFTER 10:01 PM
4. Check if logs show the new build from commit `311637d`

---

### Option 2: Manual Redeploy (If Auto-Deploy Didn't Trigger)

**Steps**:
1. Go to Railway dashboard: https://railway.app/
2. Select **"thronos chain"** project
3. Click on **"node 2"** service
4. Go to **"Deployments"** tab
5. Click **"Redeploy"** button on the latest deployment
   - OR click **"Deploy"** button to trigger fresh deployment

**Alternative - Force Redeploy via Settings**:
1. Click **"Settings"** tab
2. Scroll to **"Danger Zone"**
3. Click **"Restart"** (this will restart current deployment)
   - NOTE: This only restarts, doesn't pull new code!
4. Better: Click **"Redeploy"** from Deployments tab

---

### Option 3: Trigger Deployment via Empty Commit (From Terminal)

```bash
# Create empty commit to trigger Railway webhook
git checkout main
git pull origin main
git commit --allow-empty -m "chore: trigger Railway deployment for Node 2 fix"
git push origin main
```

Railway will detect the push and trigger auto-deploy.

---

## 🔍 Verify Fix is Deployed

### 1. Check Deployment Logs
Look for these indicators in Deploy Logs:
```
Building...
[build output]
Deployed successfully
```

### 2. Check if Heartbeat Errors Stopped
**Before fix** (BAD):
```
[HEARTBEAT] ⚠️ Timeout connecting to https://thrchain.up.railway.app/api/peers/heartbeat
[HEARTBEAT] ⚠️ Replica marked as OUT OF SYNC after X consecutive failures
```

**After fix** (GOOD):
```
[STARTUP] REPLICA node initialization complete
[HEARTBEAT] ✅ Synced with master (active_peers: 1)
```
OR no heartbeat errors at all.

### 3. Test Node 2 URL
```bash
# Should return 200 OK, not 502
curl -I https://node-2.up.railway.app/

# Should return blockchain stats
curl https://node-2.up.railway.app/api/network_stats
```

---

## ⚙️ Node 2 Environment Variables (Verify These)

**Required env vars for Node 2**:
```bash
NODE_ROLE=replica
MASTER_INTERNAL_URL=https://thrchain.up.railway.app
READ_ONLY=1
ENABLE_CHAIN=1

# Cross-chain RPC URLs (for bridge monitoring)
BTC_RPC_URL=<bitcoin_rpc>
ETH_RPC_URL=https://eth.llamarpc.com
BSC_RPC_URL=https://bsc-dataseed.binance.org
POLYGON_RPC_URL=https://polygon-rpc.com
ARBITRUM_RPC_URL=https://arb1.arbitrum.io/rpc
OPTIMISM_RPC_URL=https://mainnet.optimism.io

# Flask config
PORT=8000
FLASK_ENV=production

# IMPORTANT: Node 2 should NOT have AI keys
# These should ONLY be on Node 1 and Node 4:
# ❌ OPENAI_API_KEY
# ❌ ANTHROPIC_API_KEY
# ❌ GOOGLE_API_KEY
```

**Verify in Railway**:
1. Node 2 → Settings → Variables
2. Check NODE_ROLE=replica is set
3. Check MASTER_INTERNAL_URL points to Node 1
4. Confirm NO AI keys are present

---

## 🐛 Debugging Deployment Issues

### Issue: Railway shows "Online" but URL returns 502

**Possible causes**:
1. **Old deployment still running** - Railway health check passes but app crashes on requests
2. **Deployment didn't pull new code** - Check commit hash in logs
3. **Memory limit exceeded** - Node 2 hitting Railway memory limits
4. **CHAIN_FILE too large** - If data/chain.json is 10MB+, loading causes OOM

**Solutions**:
- Force redeploy from Deployments tab
- Check memory usage in Metrics tab
- Increase memory limit if needed (Railway → Settings → Resources)

### Issue: Heartbeat errors continue after fix deployed

**Check**:
1. Is Node 2 actually using the new code?
   ```bash
   # From Node 2 logs, look for startup message
   [STARTUP] REPLICA node initialization complete
   [STARTUP] Syncing blockchain height offset...
   ```

2. Is MASTER_INTERNAL_URL correct?
   ```bash
   # Should be Node 1 URL
   echo $MASTER_INTERNAL_URL
   # Expected: https://thrchain.up.railway.app
   ```

3. Is Node 1 accessible from Node 2?
   ```bash
   # From Node 2 terminal (Railway CLI):
   railway run bash
   curl https://thrchain.up.railway.app/api/peers/heartbeat -X POST \
     -H "Content-Type: application/json" \
     -d '{"peer_id":"test","url":"http://test"}'
   
   # Should return:
   # {"ok":true,"role":"master","peer_id":"test","active_peers":1,"ttl_seconds":60}
   ```

---

## ✅ Expected Behavior After Fix

### Node 2 Startup Logs (GOOD):
```
[STARTUP] REPLICA node initialization complete
[STARTUP] READ_ONLY mode enforced (no write operations)
[STARTUP] Connecting to master at https://thrchain.up.railway.app
[HEARTBEAT] ✅ Synced with master (active_peers: 1)
[INFO] Running on http://0.0.0.0:8000
```

### Node 2 Runtime Logs (GOOD):
```
# Minimal logging - only errors or important events
# NO continuous heartbeat timeout errors
# NO "OUT OF SYNC" warnings
```

### Node 2 Response Times (GOOD):
- Homepage: <500ms
- /api/network_stats: <1s
- /api/mempool: <500ms
- No 502 errors

---

## 📞 If Still Having Issues

1. **Check Railway Status**: https://status.railway.app/
2. **Check Node 1 is online**: https://thrchain.up.railway.app/
3. **Check deployment commit hash** matches `311637d` or later
4. **Check Railway logs** for Python errors (not just heartbeat)
5. **Check memory/CPU metrics** in Railway dashboard
6. **Contact Railway support** if deployment issues persist

---

## 🎯 Summary

**Problem**: Node 2 crashes due to expensive heartbeat operation
**Fix**: Commit `311637d` removes chain loading from heartbeat (merged to main)
**Action**: Wait 5-8 minutes for auto-deploy OR manually redeploy from Railway dashboard
**Verify**: Check logs for no heartbeat errors + Node 2 URL returns 200 OK

**Current status**: Fix is merged ✅, waiting for Railway deployment to complete.
