"""
server_ext.py — thin wrapper over server.py
Registers additional blueprints without touching the 1.2MB monolith.
Gunicorn entry point: server_ext:app
"""
from server import app  # noqa: F401  — imports the Flask app + all routes

# L2E EDU Bridge — receives attendance events from thronos-edupresence
try:
    from services.l2e_edu import l2e_edu_bp
    app.register_blueprint(l2e_edu_bp)
    app.logger.info("[L2E-EDU] Blueprint registered at /api/l2e/edu")
except Exception as exc:  # pragma: no cover
    app.logger.warning("[L2E-EDU] Blueprint NOT loaded: %s", exc)
