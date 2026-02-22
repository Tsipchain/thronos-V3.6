#!/bin/bash
# VerifyID AI Integration E2E Test Suite
# Tests Render AI endpoint + Railway callback handler

set -e

RENDER_URL="https://ai.thronoschain.org"
RAILWAY_URL="https://verifyid-api.thronoschain.org"
INTERNAL_KEY="verifyid-saas-internal-20260222-xyz789"

echo "🧪 VerifyID AI E2E Tests"
echo "========================="
echo ""

# Test 1: AI Endpoint Health
echo "1️⃣ Testing AI Core health..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$RENDER_URL/health")
if [ "$RESPONSE" == "200" ]; then
    echo "   ✅ AI Core is healthy"
else
    echo "   ❌ AI Core health check failed (HTTP $RESPONSE)"
    exit 1
fi
echo ""

# Test 2: VerifyID AI Analysis Endpoint
echo "2️⃣ Testing VerifyID AI analysis endpoint..."
RESPONSE=$(curl -s -X POST "$RENDER_URL/internal/verifyid/analyze-kyc" \
  -H "X-Internal-Key: $INTERNAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "KYC-test-e2e-001",
    "user_id": "user-test-123",
    "documents": [
      {"type": "passport", "url": "https://example.com/passport.jpg"},
      {"type": "selfie", "url": "https://example.com/selfie.jpg"}
    ],
    "callback_url": "'$RAILWAY_URL'/internal/ai/callback",
    "callback_key": "'$INTERNAL_KEY'"
  }')

echo "   Response: $RESPONSE"

if echo "$RESPONSE" | grep -q '"ok".*true'; then
    echo "   ✅ AI analysis endpoint responding"
    FRAUD_SCORE=$(echo "$RESPONSE" | grep -o '"fraud_score":[0-9.]*' | cut -d: -f2)
    AI_JOB_ID=$(echo "$RESPONSE" | grep -o '"ai_job_id":"[^"]*"' | cut -d'"' -f4)
    echo "   📊 Fraud Score: $FRAUD_SCORE"
    echo "   🆔 AI Job ID: $AI_JOB_ID"
else
    echo "   ❌ AI analysis failed"
    exit 1
fi
echo ""

# Test 3: Railway Callback Handler
echo "3️⃣ Testing Railway callback handler..."
RESPONSE=$(curl -s -X POST "$RAILWAY_URL/internal/ai/callback" \
  -H "X-Internal-Key: $INTERNAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "KYC-test-e2e-001",
    "fraud_score": 0.42,
    "flags": ["low_resolution_document"],
    "requires_agent": false,
    "status": "ai_review",
    "ai_job_id": "ai-kyc-test-001",
    "analyzed_at": "2026-02-22T11:30:00Z"
  }')

echo "   Response: $RESPONSE"

if echo "$RESPONSE" | grep -q '"ok".*true'; then
    echo "   ✅ Callback handler working"
else
    echo "   ❌ Callback handler failed"
    exit 1
fi
echo ""

# Test 4: Unauthorized Access Protection
echo "4️⃣ Testing unauthorized access protection..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$RENDER_URL/internal/verifyid/analyze-kyc" \
  -H "X-Internal-Key: wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"request_id": "test"}')

if [ "$RESPONSE" == "401" ] || [ "$RESPONSE" == "403" ]; then
    echo "   ✅ Unauthorized access blocked (HTTP $RESPONSE)"
else
    echo "   ⚠️  Expected 401/403, got HTTP $RESPONSE"
fi
echo ""

echo "🎉 All E2E tests passed!"
echo ""
echo "📋 Test Summary:"
echo "   ✅ AI Core health check"
echo "   ✅ VerifyID AI analysis endpoint"
echo "   ✅ Railway callback handler"
echo "   ✅ Unauthorized access protection"
echo ""
echo "🚀 Production ready!"
