"""VerifyID AI Integration Bootstrap for Thronos V3.6

This module is imported by server.py at startup to register
VerifyID KYC AI analysis routes.

Usage in server.py:
    import verifyid_bootstrap
    verifyid_bootstrap.init(app)
"""

import logging

logger = logging.getLogger(__name__)

def init(app):
    """
    Initialize VerifyID AI routes.
    Called from server.py after Flask app creation.
    """
    try:
        from verifyid_ai_endpoint import register_verifyid_ai_routes
        register_verifyid_ai_routes(app)
        logger.info("[VerifyID AI] ✅ Integration routes registered")
        logger.info("[VerifyID AI] Endpoint: /internal/verifyid/analyze-kyc")
        return True
    except ImportError as e:
        logger.warning(f"[VerifyID AI] ⚠️  Module not available: {e}")
        return False
    except Exception as e:
        logger.error(f"[VerifyID AI] ❌ Registration failed: {e}")
        return False

# Auto-register if Flask app is available in globals
if 'app' in globals():
    init(globals()['app'])
