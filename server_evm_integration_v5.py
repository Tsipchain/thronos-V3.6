# server_evm_integration.py
# Instructions for integrating EVM into server.py

"""
To integrate the Thronos EVM into server.py, add the following:

1. Add import at the top of server.py (after other imports):
   from evm_api import register_evm_routes

2. After the Flask app is created (after 'app = Flask(__name__)'), add:
   # Register EVM routes
   register_evm_routes(app, DATA_DIR, LEDGER_FILE, CHAIN_FILE, PLEDGE_CHAIN)

3. Add EVM page route (around line 850, with other page routes):
   @app.route("/evm")
   def evm_page():
       return render_template("evm.html")

That's it! The EVM will be fully integrated.
"""

# Here's the exact code to add:

IMPORT_LINE = """
from evm_api import register_evm_routes
"""

REGISTRATION_CODE = """
# ─── EVM INTEGRATION ────────────────────────────────────────────────────
register_evm_routes(app, DATA_DIR, LEDGER_FILE, CHAIN_FILE, PLEDGE_CHAIN)
print("[SERVER] EVM routes registered")
"""

PAGE_ROUTE = """
@app.route("/evm")
def evm_page():
    '''Render the EVM smart contracts interface.'''
    return render_template("evm.html")
"""