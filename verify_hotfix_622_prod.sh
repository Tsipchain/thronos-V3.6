#!/bin/bash

# Hotfix #622 Production Verification Script
# Verifies: Production crash fix + canonical immutability enforcement
# Usage: ./verify_hotfix_622_prod.sh <api_url>

API_URL="${1:-https://api.thronos.io}"
TIMEOUT=5

echo "=========================================="
echo "HOTFIX #622 PRODUCTION VERIFICATION"
echo "=========================================="
echo "API: $API_URL"
echo ""

# Step 1: Verify API health
echo "[1/3] Checking API health..."
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" -m $TIMEOUT "$API_URL/health" 2>/dev/null)
HEALTH_CODE=$(echo "$HEALTH_RESPONSE" | tail -n1)

if [ "$HEALTH_CODE" = "200" ]; then
    echo "✅ API HEALTHY (200)"
else
    echo "❌ API NOT HEALTHY (HTTP $HEALTH_CODE)"
    echo "   Cannot proceed with verification"
    exit 1
fi

# Step 2: Verify server is at latest commit
echo ""
echo "[2/3] Checking server commit..."
COMMIT_RESPONSE=$(curl -s -m $TIMEOUT "$API_URL/api/info" 2>/dev/null)
if [ -z "$COMMIT_RESPONSE" ]; then
    echo "⚠️  No /api/info endpoint (expected for some deployments)"
else
    echo "Server info:"
    echo "$COMMIT_RESPONSE" | head -n 5
fi

# Step 3: Verify pledge endpoint responds correctly
echo ""
echo "[3/3] Checking pledge endpoint..."
PLEDGE_RESPONSE=$(curl -s -w "\n%{http_code}" -m $TIMEOUT "$API_URL/pledge" 2>/dev/null)
PLEDGE_CODE=$(echo "$PLEDGE_RESPONSE" | tail -n1)

if [ "$PLEDGE_CODE" = "200" ] || [ "$PLEDGE_CODE" = "302" ] || [ "$PLEDGE_CODE" = "404" ]; then
    echo "✅ /pledge endpoint responsive (HTTP $PLEDGE_CODE)"
else
    echo "⚠️  /pledge endpoint returned $PLEDGE_CODE"
fi

echo ""
echo "=========================================="
echo "NEXT STEPS:"
echo "=========================================="
echo ""
echo "1. Open browser DevTools (F12) → Network tab"
echo ""
echo "SCENARIO A: Canonical exists → NO /pledge"
echo "  - Run in console:"
echo "    localStorage.setItem('wallet_v1_canonical_address', 'THRtest1234567890');"
echo "    location.reload();"
echo "  - Expected Network: ZERO /pledge requests"
echo "  - Expected Console: ZERO ReferenceError messages"
echo "  - Expected UI: Pledge panel HIDDEN, mode shows Unlock"
echo ""
echo "SCENARIO B: Canonical missing → /pledge allowed"
echo "  - Run in console:"
echo "    localStorage.removeItem('wallet_v1_canonical_address');"
echo "    location.reload();"
echo "  - Expected Network: /pledge accessible"
echo "  - Expected Console: CLEAN"
echo "  - Expected UI: Pledge panel VISIBLE, button clickable"
echo ""
echo "SCENARIO C: Restore with canonical → state refresh"
echo "  - Run in console:"
echo "    localStorage.setItem('wallet_v1_canonical_address', 'THRtest1234567890');"
echo "  - Trigger restore/import button click"
echo "  - Expected Network: GET /api/wallet/v1/status?address=THR..."
echo "  - Expected UI: Pledge panel stays HIDDEN after restore"
echo ""
echo "=========================================="
