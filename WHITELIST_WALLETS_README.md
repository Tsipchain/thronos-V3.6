# Whitelist Wallets System

## Overview

The Whitelist Wallets system allows THR addresses to access all pledge-requiring features WITHOUT needing a BTC pledge. This is useful for:
- Testing wallets
- Admin wallets
- Partner/VIP wallets
- Development/staging environments

## Configuration

### Option 1: JSON File (Recommended for Production)

Create `data/whitelist_wallets.json` with a list of THR addresses:

```json
[
  "THR1234567890abcdef1234567890abcdef12345678",
  "THR9876543210fedcba9876543210fedcba98765432"
]
```

### Option 2: Environment Variable (Recommended for Docker/Railway)

Set the `THRONOS_WHITELIST_WALLETS` environment variable with comma-separated addresses:

```bash
export THRONOS_WHITELIST_WALLETS="THR1234...,THR5678...,THR9012..."
```

**Note:** Environment variable takes precedence over the JSON file.

## Features

### Pledge Modes

The system now supports three pledge modes:

1. **`btc_pledge`**: Traditional BTC pledge with auth_secret authentication
2. **`whitelist`**: Whitelisted wallet with no auth_secret required
3. **`none`**: No access - requires pledge or whitelist

### API Endpoint: `/api/wallet/status`

**Request:**
```
GET /api/wallet/status?address=THR1234567890abcdef1234567890abcdef12345678
```

**Response:**
```json
{
  "ok": true,
  "address": "THR1234567890abcdef1234567890abcdef12345678",
  "is_whitelisted": true,
  "pledge_mode": "whitelist",
  "has_pledge_access": true
}
```

### Affected Endpoints

All the following endpoints now check `has_pledge_access()` instead of requiring BTC pledge:

#### Send/Transfer
- `/send_thr` (POST)
- `/api/wallet/send` (POST)
- `/api/send_token` (POST)
- `/send_l2e` (POST)

#### Pool/Liquidity
- `/api/v1/pools` (POST) - Create pool
- `/api/v1/pools/add_liquidity` (POST)
- `/api/v1/pools/remove_liquidity` (POST)
- `/api/v1/pools/swap` (POST)

#### Bridge
- `/api/bridge/burn` (POST)
- `/api/bridge/withdraw` (POST)

**Note:** Bridge deposits and withdrawals still write transactions to chain correctly, regardless of whitelist/pledge status.

### Wallet UI

The wallet viewer (`/wallet?address=THR...`) now displays:

- **Whitelist badge**: 🌟 **Whitelist (No BTC pledge required)** (gold color)
- **BTC Pledge badge**: ✅ **BTC Pledge Active** (green color)
- **No access**: ❌ **No Pledge** (red color)

## Security Considerations

1. **Whitelist File Protection**: Store `data/whitelist_wallets.json` securely and limit write access
2. **Environment Variable**: Use secure environment management for production
3. **Auth Requirements**:
   - Whitelisted wallets do NOT require `auth_secret` for transactions
   - BTC pledged wallets STILL require `auth_secret` for all operations
4. **Audit Trail**: All transactions (from both whitelisted and pledged wallets) are logged to chain

## Testing

To test the whitelist system:

1. Add a test wallet address to `data/whitelist_wallets.json`
2. Check status: `curl "http://localhost:8000/api/wallet/status?address=THR..."`
3. Try sending THR without auth_secret (should succeed for whitelisted wallets)
4. View wallet: `http://localhost:8000/wallet?address=THR...` (should show whitelist badge)

## Implementation Details

### Helper Functions (server.py)

- `load_whitelist_wallets()`: Load from file or env variable
- `is_wallet_whitelisted(thr_address)`: Check if address is whitelisted
- `get_wallet_pledge_mode(thr_address)`: Returns "btc_pledge" | "whitelist" | "none"
- `has_pledge_access(thr_address)`: True if pledge_mode != "none"
- `get_pledge_for_auth(thr_address)`: Get pledge object for BTC pledged wallets only

### Pledge Check Logic

```python
# Check pledge access
if not has_pledge_access(wallet_address):
    return error("No pledge access")

pledge_mode = get_wallet_pledge_mode(wallet_address)

if pledge_mode == "whitelist":
    # No auth needed - proceed with transaction
    pass
elif pledge_mode == "btc_pledge":
    # Verify auth_secret as usual
    if not auth_secret:
        return error("Missing auth_secret")
    # ... verify auth hash ...
```

## Migration Notes

- **Backward Compatible**: Existing BTC pledge wallets continue to work without changes
- **No Database Changes**: Uses existing pledge_chain.json + new whitelist_wallets.json
- **Bridge Transactions**: Continue to write to chain correctly (verified at server.py:6496-6498)
