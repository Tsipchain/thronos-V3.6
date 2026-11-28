"""
AI Core Chat Endpoint for Thronos V3.6

Provides POST /api/ai/chat endpoint with app-specific prompt routing.
Reads X-Thronos-App header to determine which persona/system prompt to use.

Usage:
    from ai_core_chat import register_ai_chat_routes
    register_ai_chat_routes(app, llm_router)
"""

import os
import json
import logging
from flask import request, jsonify

logger = logging.getLogger(__name__)

# Environment variables
AI_CORE_DEFAULT_APP = os.getenv("AI_CORE_DEFAULT_APP", "thronos")

# Base prompts per app
THRONOS_AUTONOMOUS_PROMPT = """
You are Thronos Autonomous AI.
You know the Thronos V3.6 architecture, governance docs, billing systems,
and chain economics. You help core devs and power users with architecture,
code, and protocol-level questions.
""".strip()

VERIFYID_BASE_PROMPT = """
You are the VerifyID Assistant for Thronos.
Your job is to help users understand and use KYC, device verification,
risk scoring and fraud-prevention features. You never talk about chain
governance, node roles or internal dev issues unless explicitly asked.
Stay focused on identity, device verification, rewards, and compliance.
You can assist with:
- KYC document verification questions
- Device registration (ASIC, GPS, Vehicle nodes)
- Risk score interpretation
- Fraud detection features
- Verification rewards and incentives
- Compliance requirements
""".strip()

# App ID → base prompt mapping
APP_PROMPTS = {
    "verifyid": VERIFYID_BASE_PROMPT,
    "thronos": THRONOS_AUTONOMOUS_PROMPT,
    "default": THRONOS_AUTONOMOUS_PROMPT,
}


def register_ai_chat_routes(app, llm_router=None):
    """
    Register AI chat routes with Flask app.
    
    Args:
        app: Flask application instance
        llm_router: Optional LLM router instance for calling providers
                   (OpenAI, Anthropic, Gemini, etc.)
    """
    
    @app.route("/api/ai/chat", methods=["POST"])
    def api_ai_chat():
        """
        AI Chat completion endpoint with app-specific routing.
        
        Headers:
            X-Thronos-App: verifyid | thronos (default: thronos)
            X-Admin-Secret: Admin secret for internal requests (optional)
            Content-Type: application/json
        
        POST body:
        {
            "model": "claude-sonnet-4-5-20250929",
            "messages": [
                {"role": "system", "content": "..."},  # Optional, merged with base
                {"role": "user", "content": "Hello"}
            ],
            "temperature": 0.3,
            "max_tokens": 1024
        }
        
        Returns:
        {
            "ok": true,
            "content": "AI response text",
            "model": "claude-sonnet-4-5-20250929",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 50,
                "total_tokens": 60
            }
        }
        """
        try:
            # Determine app from header
            app_id = request.headers.get("X-Thronos-App", AI_CORE_DEFAULT_APP).lower().strip()
            
            # Select base prompt
            base_prompt = APP_PROMPTS.get(app_id, APP_PROMPTS["default"])
            
            logger.info(f"[AI Chat] Request from app={app_id}, using base prompt for {app_id}")
            
            # Parse request
            data = request.get_json() or {}
            model = data.get("model", "claude-sonnet-4-5-20250929")
            user_messages = data.get("messages", [])
            temperature = data.get("temperature", 0.3)
            max_tokens = data.get("max_tokens", 1024)
            
            # Build message list with app-specific system prompt
            messages = [{"role": "system", "content": base_prompt}]
            
            # Merge any user-provided system message with base
            for msg in user_messages:
                if msg.get("role") == "system":
                    # Append user system prompt after base
                    messages.append(msg)
                else:
                    messages.append(msg)
            
            # Call LLM (via router if provided, otherwise return mock for now)
            if llm_router is None:
                # No LLM router available - return informative response
                # In production, this should call your actual LLM provider
                return jsonify({
                    "ok": True,
                    "content": f"[AI Core] Request received from app={app_id}. "
                               f"This is the AI Core with app-specific routing enabled. "
                               f"Base prompt: {'VerifyID' if app_id == 'verifyid' else 'Thronos'}. "
                               f"Model requested: {model}. "
                               f"Integrate your LLM router (OpenAI/Anthropic/Gemini) to get actual responses.",
                    "model": model,
                    "app_id": app_id,
                    "usage": {
                        "prompt_tokens": sum(len(m.get("content", "")) for m in messages) // 4,
                        "completion_tokens": 50,
                        "total_tokens": sum(len(m.get("content", "")) for m in messages) // 4 + 50
                    }
                }), 200
            
            # Call through LLM router
            try:
                result = llm_router.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                return jsonify({
                    "ok": True,
                    "content": result.get("content"),
                    "model": model,
                    "app_id": app_id,
                    "usage": result.get("usage", {})
                }), 200
                
            except Exception as e:
                logger.error(f"[AI Chat] LLM router error: {e}")
                return jsonify({
                    "ok": False,
                    "error": f"LLM call failed: {str(e)}"
                }), 500
                
        except Exception as e:
            logger.exception(f"[AI Chat] Unexpected error: {e}")
            return jsonify({
                "ok": False,
                "error": str(e)
            }), 500
    
    @app.route("/api/ai/chat", methods=["GET"])
    def api_ai_chat_info():
        """Info endpoint for AI chat service."""
        return jsonify({
            "ok": True,
            "service": "ai-core-chat",
            "version": "1.0.0",
            "supported_apps": list(APP_PROMPTS.keys()),
            "default_app": AI_CORE_DEFAULT_APP,
            "endpoint": "POST /api/ai/chat",
            "headers": {
                "X-Thronos-App": "verifyid | thronos (default: thronos)"
            },
            "note": "Send X-Thronos-App header to get app-specific persona"
        }), 200
    
    logger.info(f"[AI Core Chat] Routes registered: /api/ai/chat")
    logger.info(f"[AI Core Chat] Default app: {AI_CORE_DEFAULT_APP}")
    logger.info(f"[AI Core Chat] Supported apps: {list(APP_PROMPTS.keys())}")


# Integration with server.py:
# Add near the bottom of server.py (before app.run()):
#
#   from ai_core_chat import register_ai_chat_routes
#   register_ai_chat_routes(app, llm_router=your_llm_router_instance)
