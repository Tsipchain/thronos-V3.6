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


# ── Acceptance: walletless learner, enrollment states, API failure ──────────


def test_walletless_earn_learner_via_authenticated_session():
    """A walletless learner with valid thr_earn_session cookie gets server_learner_id set."""
    import os, tempfile
    os.environ.setdefault("EARN_ACCOUNT_ENABLED", "1")
    from services.earn_account import EarnAccountStore
    with tempfile.TemporaryDirectory() as td:
        store = EarnAccountStore(os.path.join(td, "test.db"), "testkey")
        store.register("learner42@example.com", "StrongP@ss1")
        acct, token = store.login("learner42@example.com", "StrongP@ss1")
        import server as _srv
        _srv._earn_acct_store = store
        try:
            client = _client()
            client.set_cookie("thr_earn_session", token, domain="localhost")
            resp = client.get("/student-dashboard")
            html = resp.data.decode()
            assert resp.status_code == 200
            assert f'"{acct["earn_user_id"]}"' in html
            assert "serverVerifiedWallet" in html
        finally:
            _srv._earn_acct_store = None


def test_walletless_learner_claim_disabled_in_template():
    """Template disables L2E claim when serverVerifiedWallet is falsy."""
    html = _read_template()
    assert 'disabled' in html
    assert 'Verified wallet required' in html or 'επαληθευμένο πορτοφόλι' in html
    # Claim function guards on serverVerifiedWallet
    assert 'if (!serverVerifiedWallet)' in html


def test_enrollment_pending_state():
    """Template handles enrollment-pending (404 from enrollment endpoint) distinctly."""
    html = _read_template()
    assert 'enrollment_pending' in html
    assert 'Enrollment Pending' in html or 'Εγγραφή σε εκκρεμότητα' in html


def test_api_failure_state():
    """Dashboard shows api-failure state when course API fetch fails."""
    html = _read_template()
    assert 'data-state="api-failure"' in html
    assert 'try again later' in html.lower() or 'Δοκιμάστε ξανά αργότερα' in html


def test_no_localstorage_wallet_for_display():
    """displayWallet must NOT fall back to localStorage — only serverVerifiedWallet."""
    html = _read_template()
    # Ensure no localStorage wallet reading in syncWalletFromSession
    lines = html.split('\n')
    in_sync = False
    for line in lines:
        if 'function syncWalletFromSession' in line:
            in_sync = True
        elif in_sync and line.strip().startswith('function '):
            break
        if in_sync:
            assert 'earn_account' not in line, "syncWalletFromSession must not read earn_account from localStorage"
            assert 'walletAddress' not in line, "syncWalletFromSession must not read walletAddress from localStorage"
            assert 'thr_address' not in line, "syncWalletFromSession must not read thr_address from localStorage"


def test_server_ext_separate_learner_id():
    """server_ext route separates server_learner_id from server_wallet."""
    import inspect
    import server_ext
    source = inspect.getsource(server_ext.l2e_student_dashboard_page)
    assert "server_learner_id" in source
    assert "server_wallet" in source
    # Must use authenticated thr_earn_session, not raw earn_learner_id
    assert "thr_earn_session" in source
    assert "user_for_session" in source


# ── P0 Earn session authentication tests ─────────────────────────────────────

import contextlib as _ctxlib
import os as _os
import shutil as _shutil
import tempfile as _tempfile

_os.environ.setdefault("EARN_ACCOUNT_ENABLED", "1")
from services.earn_account import EarnAccountStore as _EarnAccountStore


@_ctxlib.contextmanager
def _earn_env():
    """Yield an EarnAccountStore bound to server._earn_acct_store for the block."""
    import server as _srv
    td = _tempfile.mkdtemp()
    s = _EarnAccountStore(_os.path.join(td, "test.db"), "testkey")
    _srv._earn_acct_store = s
    try:
        yield s
    finally:
        _srv._earn_acct_store = None
        _shutil.rmtree(td, ignore_errors=True)


def test_raw_earn_learner_id_cookie_rejected():
    """Raw earn_learner_id cookie must NOT be accepted as identity (P0 fix)."""
    with _earn_env():
        client = _client()
        client.set_cookie("earn_learner_id", "impersonated_id", domain="localhost")
        resp = client.get("/student-dashboard")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert '"impersonated_id"' not in html


def test_anonymous_session_no_private_data():
    """Anonymous request (no cookies) must not expose any learner ID."""
    with _earn_env():
        client = _client()
        resp = client.get("/student-dashboard")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "serverLearnerId" in html
        assert "let serverLearnerId = null" in html


def test_forged_session_token_rejected():
    """Forged thr_earn_session token must not expose private data."""
    with _earn_env():
        client = _client()
        client.set_cookie("thr_earn_session", "forged_token_12345", domain="localhost")
        resp = client.get("/student-dashboard")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "let serverLearnerId = null" in html


def test_expired_session_rejected():
    """Expired thr_earn_session must not resolve to a learner."""
    import hashlib, time
    with _earn_env() as st:
        st.register("expired@example.com", "StrongP@ss1")
        acct, token = st.login("expired@example.com", "StrongP@ss1")
        key = hashlib.sha256(token.encode()).hexdigest()
        with st._tx() as con:
            con.execute("UPDATE earn_sessions SET expires_at = ? WHERE token_hash = ?",
                        (int(time.time()) - 3600, key))
        client = _client()
        client.set_cookie("thr_earn_session", token, domain="localhost")
        resp = client.get("/student-dashboard")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert f'"{acct["earn_user_id"]}"' not in html
        assert "let serverLearnerId = null" in html


def test_cross_account_isolation():
    """Learner A's session must NOT resolve to learner B's data."""
    with _earn_env() as st:
        st.register("alice@example.com", "StrongP@ss1")
        acct_a, token_a = st.login("alice@example.com", "StrongP@ss1")
        st.register("bob@example.com", "StrongP@ss2")
        acct_b, token_b = st.login("bob@example.com", "StrongP@ss2")
        client = _client()
        client.set_cookie("thr_earn_session", token_a, domain="localhost")
        resp_a = client.get("/student-dashboard")
        html_a = resp_a.data.decode()
        assert f'"{acct_a["earn_user_id"]}"' in html_a
        assert f'"{acct_b["earn_user_id"]}"' not in html_a
        client.set_cookie("thr_earn_session", token_b, domain="localhost")
        resp_b = client.get("/student-dashboard")
        html_b = resp_b.data.decode()
        assert f'"{acct_b["earn_user_id"]}"' in html_b
        assert f'"{acct_a["earn_user_id"]}"' not in html_b


def test_earn_session_resolves_wallet_link():
    """Authenticated Earn user with linked wallet gets server_wallet set."""
    import time as _time
    with _earn_env() as st:
        st.register("withwallet@example.com", "StrongP@ss1")
        acct, token = st.login("withwallet@example.com", "StrongP@ss1")
        with st._tx() as con:
            con.execute(
                "INSERT INTO earn_wallet_links (wallet_address, earn_user_id, public_key, linked_at) VALUES (?,?,?,?)",
                ("0xDEADBEEF1234", acct["earn_user_id"], "pubkey_placeholder", int(_time.time())),
            )
        client = _client()
        client.set_cookie("thr_earn_session", token, domain="localhost")
        resp = client.get("/student-dashboard")
        html = resp.data.decode()
        assert '"0xDEADBEEF1234"' in html or '"0xdeadbeef1234"' in html


def test_walletless_earn_user_no_server_wallet():
    """Authenticated Earn user WITHOUT linked wallet gets null server_wallet."""
    with _earn_env() as st:
        st.register("nowallet@example.com", "StrongP@ss1")
        acct, token = st.login("nowallet@example.com", "StrongP@ss1")
        client = _client()
        client.set_cookie("thr_earn_session", token, domain="localhost")
        resp = client.get("/student-dashboard")
        html = resp.data.decode()
        assert f'"{acct["earn_user_id"]}"' in html
        assert "let serverVerifiedWallet = null" in html
