"""VerifyID KYC AI Analysis Endpoint for Thronos V3.6

Internal endpoint called by VerifyID SaaS to analyze KYC documents.
Returns fraud score and flags for agent review.
"""

import os
import json
import random
import secrets
import urllib.request
import urllib.error
from datetime import datetime
from flask import request, jsonify

# Environment variables
VERIFYID_INTERNAL_KEY = os.getenv("VERIFYID_INTERNAL_KEY", "verifyid-saas-internal-20260222-xyz789")
VERIFYID_SAAS_API_URL = os.getenv("VERIFYID_SAAS_API_URL", "https://verifyid-api.thronoschain.org")


def register_verifyid_ai_routes(app):
    """Register VerifyID AI analysis routes with Flask app"""
    
    @app.route("/internal/verifyid/analyze-kyc", methods=["POST"])
    def internal_verifyid_analyze_kyc():
        """
        Internal endpoint for KYC document analysis.
        Called by VerifyID SaaS backend.
        
        POST body:
        {
            "request_id": "KYC-abc123",
            "documents": [
                {"type": "passport", "file_hash": "sha256..."},
                {"type": "selfie", "file_hash": "sha256..."}
            ]
        }
        
        Returns:
        {
            "ok": true,
            "fraud_score": 0.35,
            "flags": [],
            "ai_job_id": "ai-kyc-xyz"
        }
        """
        # Auth check
        internal_key = request.headers.get("X-Internal-Key", "")
        if internal_key != VERIFYID_INTERNAL_KEY:
            return jsonify({
                "ok": False,
                "error": "Unauthorized: Invalid X-Internal-Key"
            }), 401
        
        data = request.get_json() or {}
        request_id = data.get("request_id")
        documents = data.get("documents", [])
        
        if not request_id:
            return jsonify({
                "ok": False,
                "error": "request_id required"
            }), 400
        
        # Mock AI analysis (production: real OCR + fraud detection ML model)
        # fraud_score: 0.0 (no risk) to 1.0 (high fraud risk)
        fraud_score = round(0.28 + (random.random() * 0.4), 3)  # 0.28-0.68
        
        flags = []
        requires_agent = False
        
        # Fraud detection logic
        if fraud_score > 0.6:
            flags.append("High fraud score detected")
            requires_agent = True
        elif fraud_score > 0.5:
            flags.append("Document quality suspicious")
            flags.append("Face mismatch possible")
            requires_agent = True
        
        # Determine status
        if fraud_score <= 0.3:
            status = "auto_approved"  # Low risk → auto-approve
        elif fraud_score <= 0.5:
            status = "ai_review"  # Medium risk → AI review
        else:
            status = "agent_queue"  # High risk → agent needed
        
        ai_job_id = f"ai-kyc-{secrets.token_hex(8)}"
        
        # Callback to VerifyID SaaS backend
        callback_url = f"{VERIFYID_SAAS_API_URL}/internal/ai/callback"
        callback_data = {
            "request_id": request_id,
            "fraud_score": fraud_score,
            "flags": flags,
            "requires_agent": requires_agent,
            "status": status,
            "ai_job_id": ai_job_id,
            "analyzed_at": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            # POST callback to VerifyID SaaS
            req = urllib.request.Request(
                callback_url,
                data=json.dumps(callback_data).encode("utf-8"),
                headers={
                    "X-Internal-Key": VERIFYID_INTERNAL_KEY,
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                callback_result = json.loads(resp.read().decode("utf-8"))
                
        except Exception as e:
            # Non-blocking: log error but still return result
            print(f"[VerifyID AI] Callback failed: {e}")
        
        return jsonify({
            "ok": True,
            "fraud_score": fraud_score,
            "flags": flags,
            "requires_agent": requires_agent,
            "status": status,
            "ai_job_id": ai_job_id,
            "documents_analyzed": len(documents)
        }), 200
    
    @app.route("/internal/verifyid/health", methods=["GET"])
    def internal_verifyid_health():
        """Health check for VerifyID AI integration"""
        return jsonify({
            "ok": True,
            "service": "verifyid-ai",
            "status": "online",
            "callback_url": f"{VERIFYID_SAAS_API_URL}/internal/ai/callback"
        }), 200
    
    print("[VerifyID AI] Routes registered: /internal/verifyid/analyze-kyc")


# Integration with main server.py:
# Add this line near the bottom of server.py (before app.run()):
#
#   from verifyid_ai_endpoint import register_verifyid_ai_routes
#   register_verifyid_ai_routes(app)
