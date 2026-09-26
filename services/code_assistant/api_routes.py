"""Flask API routes for the Code Assistant tenant.

Mount these on the main server with:
    from services.code_assistant.api_routes import code_assistant_bp
    app.register_blueprint(code_assistant_bp, url_prefix="/api/code-assistant")
"""

import logging
from flask import Blueprint, request, jsonify

from .code_assistant_service import CodeAssistantService

logger = logging.getLogger(__name__)

code_assistant_bp = Blueprint("code_assistant", __name__)
_service = CodeAssistantService()


@code_assistant_bp.route("/health", methods=["GET"])
def health():
    status = _service.get_model_status()
    return jsonify(status), 200 if status["healthy"] else 503


@code_assistant_bp.route("/models", methods=["GET"])
def list_models():
    status = _service.get_model_status()
    return jsonify({"models": status.get("available_models", [])})


@code_assistant_bp.route("/models/pull", methods=["POST"])
def pull_model():
    data = request.get_json(force=True)
    model_name = data.get("model")
    if not model_name:
        return jsonify({"error": "model is required"}), 400
    result = _service.pull_model(model_name)
    return jsonify(result)


@code_assistant_bp.route("/sessions", methods=["POST"])
def create_session():
    data = request.get_json(force=True) if request.data else {}
    result = _service.create_session(
        repo_url=data.get("repo_url"),
        branch=data.get("branch"),
        model=data.get("model"),
        workspace_path=data.get("workspace_path"),
    )
    status_code = 201 if "error" not in result else 400
    return jsonify(result), status_code


@code_assistant_bp.route("/sessions", methods=["GET"])
def list_sessions():
    sessions = _service.list_sessions()
    return jsonify({"sessions": sessions})


@code_assistant_bp.route("/sessions/<session_id>", methods=["GET"])
def get_session(session_id: str):
    session = _service.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)


@code_assistant_bp.route("/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id: str):
    result = _service.delete_session(session_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@code_assistant_bp.route("/sessions/<session_id>/message", methods=["POST"])
def send_message(session_id: str):
    data = request.get_json(force=True)
    message = data.get("message")
    if not message:
        return jsonify({"error": "message is required"}), 400
    result = _service.send_message(
        session_id=session_id,
        message=message,
        model=data.get("model"),
    )
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
