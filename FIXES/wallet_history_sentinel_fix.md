# Fix: KeyError 'total_sentinel_spent' in wallet_history

## Error
```
ERROR:thronos:[wallet_history] failed: 'total_sentinel_spent'
```

## Root Cause

Commit `c05ba27f` (2026-03-16) added sentinel subscription tracking to wallet history.
It added accumulation code inside `_collect_wallet_history_transactions()`:

```python
elif category == "sentinel":
    summary["total_sentinel_spent"] += amount   # line ~8477
    summary["sentinel_count"] += 1              # line ~8478
```

But the inline `summary = {...}` dict at the top of that function was NOT updated
to include these two keys. So any wallet with a sentinel transaction raises KeyError.

Note: `_empty_wallet_history_summary()` (the fallback) was correctly updated,
which is why the fallback path works but the main path crashes.

## Fix (3 lines in server.py)

In `_collect_wallet_history_transactions`, find the `summary = {` dict
(around line 8439 in main branch) and add the two missing fields:

**Before:**
```python
    summary = {
        "total_mining": 0.0,
        "total_ai_rewards": 0.0,
        "total_music_tips_sent": 0.0,
        "total_music_tips_received": 0.0,
        "total_iot_rewards": 0.0,
        "total_sent": 0.0,
        "total_received": 0.0,
        "mining_count": 0,
        "ai_reward_count": 0,
        "music_tip_count": 0,
        "iot_count": 0
    }
```

**After:**
```python
    summary = {
        "total_mining": 0.0,
        "total_ai_rewards": 0.0,
        "total_music_tips_sent": 0.0,
        "total_music_tips_received": 0.0,
        "total_iot_rewards": 0.0,
        "total_sent": 0.0,
        "total_received": 0.0,
        "mining_count": 0,
        "ai_reward_count": 0,
        "music_tip_count": 0,
        "iot_count": 0,
        "total_sentinel_spent": 0.0,
        "sentinel_count": 0,
    }
```

## Apply via git

```bash
git apply FIXES/wallet_history_sentinel_fix.patch
git add server.py
git commit -m 'fix(wallet): initialize sentinel fields in wallet_history summary'
git push origin main
```

## Urgency

This affects **every** call to `/api/wallet/history/<address>` —
the error path falls back to `_build_wallet_history_fallback()` which
works but returns less data. Production requests are currently degraded.
