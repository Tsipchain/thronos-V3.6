from flask import Flask
from health_check_v3 import health_bp


def create_app() -> Flask:
    app = Flask(__name__)

    # Register health blueprint for AI Core and other nodes
    app.register_blueprint(health_bp)

    return app


app = create_app()
