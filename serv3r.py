from flask import Flask

from health_check_v3 import health_bp, health_check


def create_app() -> Flask:
    app = Flask(__name__)

    # Register health blueprint for AI Core and other nodes
    app.register_blueprint(health_bp)

    # Simple wrapper so /health works (and matches runbook / Render checks)
    @app.route("/health", methods=["GET"])
    def simple_health():  # type: ignore[func-returns-value]
        # Reuse the existing /api/v1/health handler
        return health_check()

    return app


app = create_app()
