#!/bin/bash
# Complete Feature Test Script for Thronos
# Tests all implemented features

BASE_URL="${BASE_URL:-https://thrchain.up.railway.app}"

echo "🚀 THRONOS COMPLETE FEATURE TEST"
echo "================================"
echo "Testing: $BASE_URL"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"

    echo -n "Testing $name... "

    status=$(curl -s -o /dev/null -w "%{http_code}" "$url")

    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $status)"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC} (Expected $expected_status, got $status)"
        ((FAIL++))
    fi
}

test_json_endpoint() {
    local name="$1"
    local url="$2"
    local check_field="$3"

    echo -n "Testing $name... "

    response=$(curl -s "$url")

    if echo "$response" | jq -e ".$check_field" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC} (Field '$check_field' exists)"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC} (Field '$check_field' missing)"
        echo "Response: $response"
        ((FAIL++))
    fi
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. BASIC PAGES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
test_endpoint "Homepage" "$BASE_URL/"
test_endpoint "Chat Interface" "$BASE_URL/chat"
test_endpoint "Pools Page" "$BASE_URL/pools"
test_endpoint "Swap Page" "$BASE_URL/swap"
test_endpoint "Playground (EVM)" "$BASE_URL/playground"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. CHAT API"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
test_json_endpoint "AI Sessions" "$BASE_URL/api/ai/sessions" "sessions"
test_json_endpoint "AI Telemetry" "$BASE_URL/api/ai/telemetry" "hashrate"
test_json_endpoint "AI Wallet" "$BASE_URL/api/ai/wallet" "connected"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. EVM/SMART CONTRACTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
test_json_endpoint "EVM Contracts List" "$BASE_URL/api/evm/contracts" "contracts"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. DEX/POOLS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
test_json_endpoint "Pools List" "$BASE_URL/api/v1/pools" "pools"
test_json_endpoint "Tokens List" "$BASE_URL/api/v1/tokens" "tokens"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. STATIC ASSETS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
test_endpoint "WBTC Logo" "$BASE_URL/static/img/wbtc.png"
test_endpoint "THR Logo" "$BASE_URL/static/img/logo.png"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. BACKEND LOGS CHECK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${YELLOW}⚠ Manual check required:${NC}"
echo "  1. Go to Railway Dashboard → Logs"
echo "  2. Look for: '[EVM] routes registered'"
echo "  3. Check for: No AssertionError or 404s"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${RED}Failed: $FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Check above for details.${NC}"
    exit 1
fi
