#!/bin/bash

# Phase 1: Deploy Gate Verification for Wallet V1 UI Fix (commit b24057d)
# Verify production is running correct commit and manual QA passes

API_URL="${1:-https://api.throschain.org}"
TIMEOUT=10

echo "================================================================================"
echo "PHASE 1: DEPLOY GATE VERIFICATION - Commit b24057d"
echo "================================================================================"
echo ""

# Step 1: Verify production commit
echo "[STEP 1] Verify production running commit b24057d"
echo "  Checking: GET $API_URL/api/health"
echo ""

HEALTH=$(curl -s -m $TIMEOUT "$API_URL/api/health" 2>/dev/null)

if [ -z "$HEALTH" ]; then
    echo "❌ FAIL: /api/health not responding"
    exit 1
fi

echo "Response:"
echo "$HEALTH" | head -20
echo ""

# Try to extract git_commit from response
GIT_COMMIT=$(echo "$HEALTH" | grep -o '"git_commit":"[^"]*"' | cut -d'"' -f4)
BUILD_ID=$(echo "$HEALTH" | grep -o '"build_id":"[^"]*"' | cut -d'"' -f4)
VERSION=$(echo "$HEALTH" | grep -o '"version":"[^"]*"' | cut -d'"' -f4)

echo "Extracted values:"
echo "  git_commit: ${GIT_COMMIT:-N/A}"
echo "  build_id: ${BUILD_ID:-N/A}"
echo "  version: ${VERSION:-N/A}"
echo ""

# Check if commit looks like b24057d (7 chars of SHA)
if [[ "$GIT_COMMIT" == b24057d* ]] || [[ "$BUILD_ID" == *b24057d* ]]; then
    echo "✅ Production appears to be running commit b24057d"
else
    echo "⚠️  Could not verify exact commit (API may not expose it)"
    echo "   Ensure b24057d is deployed manually"
fi

echo ""
echo "================================================================================"
echo "STEP 2: MANUAL QA SCENARIOS"
echo "================================================================================"
echo ""
echo "You must run these scenarios in browser (F12 → Network + Console tabs)"
echo ""
echo "SCENARIO A: Canonical exists (legacy key only)"
echo "  Setup:"
echo "    localStorage.setItem('wallet_v1_address', 'THRxxxxxxxxxxxxxxxx');"
echo "    location.reload();"
echo ""
echo "  Expected Results:"
echo "    ✅ hasCanonical() returns: true"
echo "    ✅ localStorage.wallet_v1_canonical_address: populated (auto-migrated)"
echo "    ✅ Mode dropdown: shows 'Unlock Wallet V1', NOT 'Create Wallet V1'"
echo "    ✅ CTA button: shows 'Unlock Wallet V1' (not 'Create')"
echo "    ✅ Network: ZERO requests to /pledge or /pledge_submit"
echo "    ✅ Console: NO ReferenceError messages"
echo ""
echo "  IF FAIL:"
echo "    - Screenshot Network tab (show /pledge requests if any)"
echo "    - Screenshot Console (show errors)"
echo "    - Report exact request: METHOD PATH STATUS"
echo ""

echo ""
echo "SCENARIO B: Canonical missing"
echo "  Setup:"
echo "    localStorage.removeItem('wallet_v1_canonical_address');"
echo "    localStorage.removeItem('wallet_v1_address');"
echo "    location.reload();"
echo ""
echo "  Expected Results:"
echo "    ✅ Pledge panel visible"
echo "    ✅ 'Go to Pledge Activation' button clickable"
echo "    ✅ Mode dropdown includes 'Create Wallet V1' option"
echo "    ✅ Console: NO errors"
echo ""

echo ""
echo "SCENARIO C: Restore/Import with canonical present"
echo "  Setup:"
echo "    localStorage.setItem('wallet_v1_address', 'THRxxxxxxxxxxxxxxxx');"
echo "    location.reload();"
echo "    Click 'Import Matching Signing Key' or 'Restore Recovery Kit'"
echo ""
echo "  Expected Results:"
echo "    ✅ GET /api/wallet/v1/status called (Network tab shows it)"
echo "    ✅ Pledge panel HIDDEN after restore completes"
echo "    ✅ Mode shows 'Unlock' (not 'Create')"
echo "    ✅ ZERO requests to /pledge_submit"
echo "    ✅ Console: NO ReferenceError"
echo ""

echo ""
echo "================================================================================"
echo "GATE DECISION"
echo "================================================================================"
echo ""
echo "If ALL scenarios pass (A ✅ + B ✅ + C ✅):"
echo "  ✅ APPROVED: Safe to merge PR #621 (State Machine Contract)"
echo ""
echo "If ANY scenario fails:"
echo "  ❌ BLOCKED: Do NOT merge #621"
echo "  - Report exact failure details"
echo "  - Check WALLET_V1_UI_BUG_DIAGNOSTIC.md for debug"
echo ""
echo "================================================================================"

