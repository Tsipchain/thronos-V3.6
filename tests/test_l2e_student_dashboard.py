"""Tests for the L2E Student Dashboard route and template."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server
import server_ext  # noqa: F401 — registers ext routes on the Flask app

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "l2e_student_dashboard.html"


def _client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def _read_template():
    return TEMPLATE_PATH.read_text()


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
    html = _read_template()
    for keyword in ["API_KEY", "SECRET_KEY", "STRIPE", "private_key", "password", "send_secret",
                     "auth_secret", "passphrase", "connectedSecret", "connectedPassphrase"]:
        assert keyword not in html, f"Sensitive keyword '{keyword}' found in dashboard template"


def test_student_dashboard_no_credentials_in_api_calls():
    """Verify no auth_secret or passphrase is sent in POST bodies."""
    html = _read_template()
    assert "auth_secret:" not in html
    assert "passphrase:" not in html
    assert "'auth_secret'" not in html
    assert "'passphrase'" not in html


def test_student_dashboard_has_sanitize_id():
    """Template must sanitize dynamic IDs before using them in HTML attributes."""
    html = _read_template()
    assert "sanitizeId" in html


def test_student_dashboard_uses_data_attributes():
    """Action buttons must use data-action attributes, not inline onclick with dynamic IDs."""
    html = _read_template()
    assert "data-action" in html
    assert "data-course-id" in html


def test_student_dashboard_walletless_notice():
    """Dashboard must show walletless notice element for students without wallet."""
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    assert "walletlessNotice" in html


def test_student_dashboard_claim_button_disabled_without_wallet():
    """L2E claim buttons must be disabled when no wallet is connected."""
    html = _read_template()
    assert "disabled" in html
    assert "Verified wallet required" in html or "επαληθευμένο πορτοφόλι" in html


def test_student_dashboard_error_handling():
    """Dashboard must have explicit error state rendering."""
    html = _read_template()
    assert "showDashboardError" in html
    assert "Failed to load" in html


def test_student_dashboard_server_wallet_variable():
    """Template must receive server_wallet as a Jinja2 variable."""
    html = _read_template()
    assert "server_wallet" in html
    assert "serverVerifiedWallet" in html


def test_student_dashboard_walletless_browse_link():
    """Dashboard without wallet should still offer a link to browse courses."""
    html = _read_template()
    assert "/courses" in html
    assert "Browse Courses" in html or "Αναζήτηση Μαθημάτων" in html


# ── Acceptance corrections: auth identity, enrollment lookup, states ──────────


def test_no_connectedwallet_variable():
    """connectedWallet must not exist — replaced by serverLearnerId + displayWallet."""
    html = _read_template()
    assert "connectedWallet" not in html


def test_server_learner_id_variable():
    """Template receives server_learner_id from route and uses serverLearnerId."""
    html = _read_template()
    assert "server_learner_id" in html
    assert "serverLearnerId" in html


def test_no_localstorage_wallet_in_api_calls():
    """API calls must use serverLearnerId/serverVerifiedWallet, not localStorage values."""
    html = _read_template()
    # claimReward must use serverLearnerId for learner_id
    assert "learner_id: serverLearnerId" in html
    # claimReward must use serverVerifiedWallet for thr_addr
    assert "thr_addr: serverVerifiedWallet" in html
    # certificate request must use serverLearnerId in URL path
    assert "certificates/${encodeURIComponent(serverLearnerId)}" in html


def test_claim_requires_server_verified_wallet():
    """L2E claim button requires serverVerifiedWallet, not any wallet."""
    html = _read_template()
    # The claim guard checks serverVerifiedWallet, not displayWallet
    assert "if (!serverVerifiedWallet)" in html
    assert "if (serverVerifiedWallet)" in html


def test_enrollment_uses_students_array():
    """Enrollment filtering uses c.students (populated at enroll time)."""
    html = _read_template()
    assert "(c.students || []).includes(serverLearnerId)" in html
    # Must NOT use the always-empty c.enrollments for filtering
    lines_with_filter = [l for l in html.split('\n') if 'courses.filter' in l]
    for line in lines_with_filter:
        assert "c.enrollments" not in line, "Must not use c.enrollments for filtering (always empty from API)"


def test_distinct_unauthenticated_state():
    """Unauthenticated state shows 'Sign in', not 'connect wallet' or 'no enrollments'."""
    html = _read_template()
    assert 'data-state="unauthenticated"' in html
    assert 'data-state="no-enrollments"' in html


def test_walletless_learner_template_support():
    """Template supports walletless learner — uses serverLearnerId for enrollment lookups."""
    html = _read_template()
    # enrollment endpoint uses serverLearnerId
    assert "enrollment/${encodeURIComponent(serverLearnerId)}" in html
    # displayWallet is for UI only, not for API calls
    assert "displayWallet" in html
    # certificate history uses serverLearnerId
    assert "certificates/${encodeURIComponent(serverLearnerId)}/history" in html


def test_certificate_uses_server_identity():
    """Certificate request uses server-verified identity, not unverified localStorage."""
    html = _read_template()
    assert "actor_thr: serverVerifiedWallet || serverLearnerId" in html


def test_route_provides_server_learner_id():
    """The /student-dashboard route provides server_learner_id Jinja2 variable."""
    resp = _client().get("/student-dashboard")
    html = resp.data.decode()
    # When unauthenticated (no cookie), server_learner_id renders as null
    assert "serverLearnerId" in html
