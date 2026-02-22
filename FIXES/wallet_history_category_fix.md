# Wallet History Category Persistence Fix

## Problem
Transaction categories (Gateway, Music, L2E, etc.) disappear from wallet history modal after page refresh.
Only AI Credits and Mining tabs remain visible.

## Root Cause
The `category` field is not persisted to TX_LOG when transactions are written.
The `_categorize_transaction()` function exists but is not called consistently.

## Solution

### File: `server.py`

**Search for:** `def persist_normalized_tx` or `TX_LOG` write operations (around line ~2500-2550)

**Find this block:**
```python
def persist_normalized_tx(...):
    # ... existing code ...
    normalized_tx = {
        "tx_id": tx_id,
        "from": from_addr,
        "to": to_addr,
        "amount": amount,
        "timestamp": timestamp,
        # ... other fields ...
    }
```

**ADD BEFORE `with open(TX_LOG, "a")` line:**

```python
    # QUEST FIX: Ensure category persists for wallet history modal
    if "category" not in normalized_tx or not normalized_tx["category"]:
        try:
            normalized_tx["category"] = _categorize_transaction(normalized_tx)
        except Exception as e:
            logger.warning(f"[TX_LOG] Category auto-detect failed: {e}")
            normalized_tx["category"] = "other"
```

**AFTER the fix:**
```python
    # Now write to TX_LOG with category included
    with open(TX_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(normalized_tx) + "\n")
```

## Testing

1. Make a Gateway payment transaction
2. Refresh the page
3. Open Wallet History modal
4. Gateway tab should still show the transaction ✅

## Affected Tabs
- ✅ Gateway (bridge deposits/withdrawals)
- ✅ Music (artist tips, streaming payments)
- ✅ L2E (Learn-to-Earn rewards)
- ✅ Tokens (custom token transfers)
- ✅ Other (misc transactions)

## Commit Message
```
fix: Persist transaction category for wallet history modal

- Auto-detect category if missing before TX_LOG write
- Fixes vanishing Gateway/Music/L2E tabs after page refresh
- Category now persists across sessions
- Uses existing _categorize_transaction() function
```

## Priority: 🔴 CRITICAL
This affects user experience when checking transaction history.
