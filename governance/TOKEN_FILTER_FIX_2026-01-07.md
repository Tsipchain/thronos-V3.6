# Wallet Token Filter Fix
**Date:** 2026-01-07
**Commit:** 803b1f3

## Issue

Generic "TOKEN" tokens were displaying in the wallet widget balance list, showing as "TOKEN 5" even though they are not legitimate named tokens. This caused confusion for users.

## Root Cause

The wallet widget was displaying ALL tokens from the API response without filtering out generic/placeholder tokens like:
- `TOKEN` (generic placeholder)
- `UNKNOWN_TOKEN` (fallback value)
- `UNKNOWN` (another fallback)

## Solution

Added filtering in two places in `wallet_widget.html`:

### 1. Token List Display (`renderTokensList`)
```javascript
// Filter out invalid/generic tokens
const validTokens = allTokens.filter(token => {
    const sym = token.symbol.toUpperCase();
    return sym !== 'TOKEN' && sym !== 'UNKNOWN_TOKEN' && sym !== 'UNKNOWN';
});
```

### 2. Token Dropdown Selector (`renderWallet`)
```javascript
// Filter out invalid/generic tokens
const validTokensForDropdown = allTokens.filter(token => {
    const sym = token.symbol.toUpperCase();
    return sym !== 'TOKEN' && sym !== 'UNKNOWN_TOKEN' && sym !== 'UNKNOWN';
});
```

## Result

✅ Generic "TOKEN" no longer displays in wallet balance list
✅ Generic tokens excluded from dropdown filter
✅ Only legitimate named tokens (THR, L2E, WBTC, 7CEB, JAM, HPENNIS, etc.) are shown
✅ Cleaner, more professional wallet UI

## Files Modified

- `templates/wallet_widget.html` (+15 -3 lines)

## Testing

Test at: https://thrchain.up.railway.app/wallet

Expected behavior:
- No "TOKEN" entries in balance list
- Only named tokens with specific symbols
- Dropdown filter only shows valid tokens

---

**Status:** ✅ Fixed & Pushed
**Branch:** claude/fix-wallet-viewer-theme-CgnZH
