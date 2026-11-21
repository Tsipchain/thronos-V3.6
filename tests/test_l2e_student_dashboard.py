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
    for keyword in ["API_KEY", "SECRET_KEY", "STRIPE", "private_key", "password", "send_secret",
                     "auth_secret", "passphrase", "connectedSecret", "connectedPassphrase"]:
        assert keyword not in html, f"Sensitive keyword '{keyword}' found in dashboard template"


def test_student_dashboard_no_credentials_in_api_calls():
    """Verify no auth_secret or passphrase is sent in POST bodies."""
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    assert "auth_secret:" not in html
    assert "passphrase:" not in html
    assert "'auth_secret'" not in html
    assert "'passphrase'" not in html


def test_student_dashboard_has_sanitize_id():
    """Template must sanitize dynamic IDs before using them in HTML attributes."""
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    assert "sanitizeId" in html


def test_student_dashboard_uses_data_attributes():
    """Action buttons must use data-action attributes, not inline onclick with dynamic IDs."""
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    assert "data-action" in html
    assert "data-course-id" in html


def test_student_dashboard_walletless_notice():
    """Dashboard must show walletless notice element for students without wallet."""
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    assert "walletlessNotice" in html


def test_student_dashboard_claim_button_disabled_without_wallet():
    """L2E claim buttons must be disabled when no wallet is connected."""
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    assert "disabled" in html
    assert "Verified wallet required" in html or "επαληθευμένο πορτοφόλι" in html


def test_student_dashboard_error_handling():
    """Dashboard must have explicit error state rendering."""
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    assert "showDashboardError" in html
    assert "Failed to load" in html


def test_student_dashboard_server_wallet_variable():
    """Template must receive server_wallet as a Jinja2 variable."""
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    assert "server_wallet" in html
    assert "serverVerifiedWallet" in html


def test_student_dashboard_walletless_browse_link():
    """Dashboard without wallet should still offer a link to browse courses."""
    tpl = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"
    html = tpl.read_text()
    assert "/courses" in html
    assert "Browse Courses" in html or "Αναζήτηση Μαθημάτων" in html
