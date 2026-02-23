"""AI Core Bootstrap for Thronos V3.6

This module is imported by server.py at startup to register
AI Core chat routes with app-specific routing.

Usage in server.py:
    import ai_core_bootstrap
    ai_core_bootstrap.init(app, llm_router_instance)
"""

import logging

logger = logging.getLogger(__name__)

def init(app, llm_router=None):
    """
    Initialize AI Core chat routes.
    Called from server.py after Flask app creation.
    
    Args:
        app: Flask application instance
        llm_router: Optional LLM router for OpenAI/Anthropic/Gemini
    """
    try:
        from ai_core_chat import register_ai_chat_routes
        register_ai_chat_routes(app, llm_router)
        logger.info("[AI Core] ✅ Chat routes registered with app-specific routing")
        logger.info("[AI Core] Endpoint: POST /api/ai/chat")
        logger.info("[AI Core] Supports X-Thronos-App header: verifyid | thronos")
        return True
    except ImportError as e:
        logger.warning(f"[AI Core] ⚠️  Module not available: {e}")
        return False
    except Exception as e:
        logger.error(f"[AI Core] ❌ Registration failed: {e}")
        return False

# Auto-register if Flask app is available in globals
if 'app' in globals():
    init(globals().get('app'), globals().get('llm_router'))
