# Pytheia Integration: What's Needed for Main Node

**Status:** Pytheia Worker exists but needs AMM pool metrics integration

---

## Current State

### ✅ What Exists
1. **Pytheia Worker** (`pytheia_worker.py`)
   - System health monitoring
   - Endpoint health checks
   - Error tracking
   - Governance advice generation
   
2. **Pythia AI Node Manager** (`pythia_node_manager.py`)
   - Bug detection (frontend/backend)
   - AMM pool monitoring
   - Oracle services
   - Treasury management
   
3. **Pool API** (`/api/pools`)
   - Returns pool list with reserves
   - Calculates TVL
   - Returns price ratios

### ❌ What's Missing
1. **Field Name Mismatch**
   - API returns: `reserves_a`, `reserves_b`
   - Pytheia expects: `reserve_a`, `reserve_b` (note singular)
   
2. **Missing Pool Metrics**
   - `volume_24h` - NOT tracked in pool struct
   - `fees_collected` - NOT tracked in pool struct
   - `name` - NOT included in pool response
   - `created_at` - NOT tracked

3. **No Pool Metrics Persistence**
   - Pools don't track daily volume
   - Pools don't accumulate fees collected
   - No historical data

---

## Solution: Enhance Pool Structure

### 1. Update Pool Creation (in `/api/v1/pools/create` endpoint)

Add to `new_pool` object:
```python
new_pool = {
    "id": pool_id,
    "name": f"{token_a}/{token_b}",  # Human-readable name
    "token_a": token_a,
    "token_b": token_b,
    "reserves_a": round(amt_a_float, state_a["decimals"]),
    "reserves_b": round(amt_b_float, state_b["decimals"]),
    "total_shares": round(shares, 6),
    "fee_bps": fee_bps_int,
    "lp_symbol": lp_symbol,
    "providers": {
        provider: round(shares, 6)
    },
    # NEW FIELDS FOR PYTHEIA
    "volume_24h": 0.0,              # Track daily volume
    "volume_total": 0.0,            # All-time volume
    "fees_collected": 0.0,          # Total fees in THR
    "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    "last_swap_time": None,         # Track activity
}
```

### 2. Update Swap Tracking

When a swap occurs in `/api/v1/swap`, update pool:
```python
# After successful swap:
pool["volume_24h"] += swap_amount_in_thr
pool["volume_total"] += swap_amount_in_thr
pool["fees_collected"] += (swap_amount_in_thr * fee_rate)
pool["last_swap_time"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
```

### 3. Daily Volume Reset

Add to a daily task (APScheduler):
```python
def reset_daily_volumes():
    """Reset 24h volumes at midnight UTC"""
    pools = load_pools()
    for pool in pools:
        pool["volume_24h"] = 0.0
        pool["fees_collected"] = 0.0  # Or accumulate
    save_pools(pools)
```

### 4. Fix API Response (api_v1_get_pools)

The `/api/pools` endpoint already works, but add these fields:
```python
for pool in pools:
    # ... existing code ...
    
    # Add for Pytheia compatibility
    pool["name"] = f"{pool.get('token_a')}/{pool.get('token_b')}"
    pool["reserve_a"] = pool.get("reserves_a", 0)  # Alias for compatibility
    pool["reserve_b"] = pool.get("reserves_b", 0)  # Alias for compatibility
    pool["volume_24h"] = pool.get("volume_24h", 0)
    pool["fees_collected"] = pool.get("fees_collected", 0)
    
    return jsonify(pools=pools), 200
```

---

## Main Node Setup Checklist

### On Startup
- [ ] Initialize Pythia AI Node Manager
- [ ] Schedule daily volume reset task
- [ ] Connect Pytheia Worker to Pythia Manager
- [ ] Initialize pool metrics tracking

### Configuration Needed
```python
# In server.py, after initialization:

from pythia_node_manager import PythiaNodeManager

# Initialize Pythia AI node
_pythia_manager = None

def _initialize_pythia():
    """Initialize Pythia AI node manager"""
    global _pythia_manager
    try:
        _pythia_manager = PythiaNodeManager()
        
        # Schedule daily tasks
        scheduler.add_job(
            func=reset_daily_pool_volumes,
            trigger="cron",
            hour=0,  # Midnight UTC
            minute=0,
            id="reset_pool_volumes"
        )
        
        # Schedule AMM monitoring
        scheduler.add_job(
            func=_pythia_manager.fetch_amm_data,
            trigger="interval",
            minutes=5,  # Check every 5 minutes
            id="monitor_amm"
        )
        
        logger.info("✅ Pythia AI Node Manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Pythia: {e}")
        _pythia_manager = None
```

### Scheduled Tasks Needed
1. **Daily Volume Reset** - 00:00 UTC
2. **AMM Health Check** - Every 5 minutes
3. **Bug Scan** - Daily at 01:00 UTC
4. **Governance Advice Generation** - Hourly

---

## Data Flow: Pytheia Integration

```
Pool Swap
    ↓
Update pool metrics (volume, fees)
    ↓
/api/pools endpoint returns updated data
    ↓
Pythia Manager fetches AMM data (every 5 min)
    ↓
Analyzes liquidity health
    ↓
Detects issues (low liquidity, extreme prices)
    ↓
Posts governance advice if needed
```

---

## Specific Changes Required

### File: server.py

**1. Add pool metrics to new pool creation** (around line 26341):
```python
new_pool = {
    # ... existing fields ...
    "name": f"{token_a}/{token_b}",
    "volume_24h": 0.0,
    "volume_total": 0.0,
    "fees_collected": 0.0,
    "created_at": datetime.utcnow().isoformat() + "Z",
    "last_swap_time": None,
}
```

**2. Update swap volume tracking** (around line 19273):
```python
# After swap execution:
pool["volume_24h"] = float(pool.get("volume_24h", 0)) + swap_amount_usd
pool["volume_total"] = float(pool.get("volume_total", 0)) + swap_amount_usd
pool["fees_collected"] = float(pool.get("fees_collected", 0)) + (swap_amount_usd * fee_rate)
pool["last_swap_time"] = datetime.utcnow().isoformat() + "Z"
```

**3. Add Pythia initialization** (in `_initialize_pythia_and_4` function):
```python
# Add after CEX LP Agent initialization
try:
    from pythia_node_manager import PythiaNodeManager
    _pythia_manager = PythiaNodeManager()
    logger.info("✅ Pythia AI Node Manager initialized")
except Exception as e:
    logger.error(f"Failed to initialize Pythia: {e}")
```

**4. Fix API response** (around line 26027):
```python
# In api_v1_get_pools, before return:
for pool in pools:
    pool["name"] = f"{pool.get('token_a')}/{pool.get('token_b')}"
    pool["reserve_a"] = pool.get("reserves_a", 0)  # Alias
    pool["reserve_b"] = pool.get("reserves_b", 0)  # Alias

return jsonify(pools=pools), 200
```

### File: pythia_node_manager.py

**Fix field name mismatch** (around line 353):
```python
reserve_a = float(pool.get('reserves_a', pool.get('reserve_a', 0)))  # Handle both names
reserve_b = float(pool.get('reserves_b', pool.get('reserve_b', 0)))
```

---

## API Endpoints Pytheia Needs

```
GET /api/pools
├─ Returns: List of pools with:
│  ├─ name: "THR/WBTC"
│  ├─ token_a, token_b
│  ├─ reserves_a, reserves_b (or reserve_a, reserve_b)
│  ├─ volume_24h
│  ├─ fees_collected
│  ├─ price_a_to_b, price_b_to_a
│  └─ tvl_thr, tvl_usd

GET /api/tokens
├─ For price lookups

GET /api/governance/pytheia/advice
└─ Post generated advice
```

---

## Testing Checklist

- [ ] Create a pool via `/api/v1/pools/create`
- [ ] Verify pool has all new fields
- [ ] Execute a swap
- [ ] Check volume_24h increased
- [ ] Check fees_collected increased
- [ ] Run Pythia.fetch_amm_data()
- [ ] Verify no errors in metrics parsing
- [ ] Check `/api/pools` returns correct format
- [ ] Run daily reset task
- [ ] Verify volume_24h resets to 0

---

## Summary

**What to add to make everything work:**

1. ✅ Pool metrics fields (volume, fees)
2. ✅ Update tracking on every swap
3. ✅ API compatibility aliases
4. ✅ Pythia initialization on startup
5. ✅ Daily reset tasks
6. ✅ Fix field name mismatches

**Effort:** ~2 hours to implement all changes

**Impact:** Pytheia can now monitor AMM health in real-time
