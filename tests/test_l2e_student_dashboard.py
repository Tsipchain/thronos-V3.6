"""Tests for the L2E Student Dashboard route and template."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server
import server_ext  # noqa: F401 — registers ext routes on the Flask app


def _client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def test_student_dashboard_returns_200():
    resp = _client().get("/student-dashboard")
    assert resp.status_code == 200


def test_student_dashboard_is_html():
    resp = _client().get("/student-dashboard")
    assert b"text/html" in resp.content_type.encode()


def test_student_dashboard_extends_base():
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    assert "<html" in html.lower()
    assert "</html>" in html.lower()


def test_student_dashboard_contains_key_elements():
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    assert "student-dashboard" in html.lower() or "Student Dashboard" in html
    assert "/api/v1/courses" in html


def test_student_dashboard_calls_course_api():
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    assert "/api/v1/courses" in html


def test_student_dashboard_has_wallet_detection():
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    assert "localStorage" in html


def test_student_dashboard_has_language_toggle():
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    assert "thronos_lang" in html


def test_student_dashboard_no_secrets_in_template():
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    for keyword in ["API_KEY", "SECRET_KEY", "STRIPE", "private_key", "password", "send_secret"]:
        assert keyword not in html, f"Sensitive keyword '{keyword}' found in dashboard template"
