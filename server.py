from flask import Flask

# ... all your existing imports ...

# ... your existing Flask app creation and routes ...

# --- AI Core integration (add at the end, after all routes are defined) ---

from ai_core_server_integration import init_ai_core_integration

# Wire AI Core landing + /health for ai.thronoschain.org
init_ai_core_integration(app)

# ... rest of your file (if __name__ == '__main__' etc.) ...
