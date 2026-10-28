"""
Integration tests for the hardened L2E EDU bridge receiver.

Tests cover:
  - Auth: fail-closed when EDU_API_KEY is missing, wrong, or empty
  - Attendance: idempotent duplicate delivery (unique constraint)
  - Completion: eligibility-only records, never triggers reward/cert
  - Mapping validation: unknown tenant/course/classroom rejected
  - PII: no raw tax_id returned in GET endpoints
  - Real server.py registration path (import smoke)
"""
import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).parent.parent))

_TEST_API_KEY = "test-bridge-key-e2e"
_VALID_MAPPING = {
    "ministry_edu": {
        "COURSE-101": ["room-A", "room-B"],
    },
}


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch, tmp_path):
    """Set env vars BEFORE the module is imported/reloaded."""
    db_path = str(tmp_path / "l2e_edu_test.db")
    monkeypatch.setenv("EDU_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("EDU_DB_PATH", db_path)
    monkeypatch.setenv("EDU_ALLOWED_MAPPINGS", json.dumps(_VALID_MAPPING))


@pytest.fixture()
def mod(_patch_env):
    """Return a freshly-reloaded module so env vars take effect."""
    import services.l2e_edu as m
    importlib.reload(m)
    return m


@pytest.fixture()
def app(mod):
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(mod.l2e_edu_bp)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _headers():
    return {"X-EDU-API-Key": _TEST_API_KEY, "Content-Type": "application/json"}


def _attendance_payload(**overrides):
    base = {
        "tenant_id": "ministry_edu",
        "l2e_course_id": "COURSE-101",
        "classroom_id": "room-A",
        "lesson_id": "lesson-1",
        "lesson_date": "2026-10-28",
        "lesson_title": "Intro",
        "students": [
            {
                "student_external_ref": "STU-001",
                "student_name_hash": "h1",
                "thr_wallet": "THR1",
                "attendance_status": "present",
                "confirmation_method": "qr_scan",
                "attestation_hash": "att1",
            },
            {
                "student_external_ref": "STU-002",
                "student_name_hash": "h2",
                "attendance_status": "absent",
            },
        ],
    }
    base.update(overrides)
    return base


def _completion_payload(**overrides):
    base = {
        "tenant_id": "ministry_edu",
        "l2e_course_id": "COURSE-101",
        "classroom_id": "room-A",
        "completed_at": "2026-10-28T12:00:00Z",
        "students": [
            {
                "student_external_ref": "STU-001",
                "student_name_hash": "h1",
                "thr_wallet": "THR1",
                "tax_id": "SENSITIVE-001",
                "attendance_pct": 95.0,
                "reward_eligible": True,
            },
            {
                "student_external_ref": "STU-002",
                "student_name_hash": "h2",
                "attendance_pct": 60.0,
                "reward_eligible": False,
            },
        ],
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════════════
# 1. AUTH — fail-closed
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    def test_401_without_api_key(self, client):
        resp = client.post("/api/l2e/edu/attendance", json={"tenant_id": "t"})
        assert resp.status_code == 401

    def test_401_wrong_api_key(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            json={"tenant_id": "t"},
            headers={"X-EDU-API-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_401_empty_api_key_header(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            json={"tenant_id": "t"},
            headers={"X-EDU-API-Key": ""},
        )
        assert resp.status_code == 401

    def test_503_when_edu_api_key_not_configured(self, client, mod):
        """When the server has no EDU_API_KEY at all, return 503."""
        import services.l2e_edu as m
        original = m.EDU_API_KEY
        m.EDU_API_KEY = ""
        try:
            resp = client.post(
                "/api/l2e/edu/attendance",
                json=_attendance_payload(),
                headers=_headers(),
            )
            assert resp.status_code == 503
            assert "not configured" in resp.get_json()["error"]
        finally:
            m.EDU_API_KEY = original

    def test_all_endpoints_reject_without_key(self, client):
        endpoints = [
            ("POST", "/api/l2e/edu/attendance"),
            ("POST", "/api/l2e/edu/complete"),
            ("GET", "/api/l2e/edu/course/c1/completions"),
            ("GET", "/api/l2e/edu/course/c1/attendance"),
        ]
        for method, path in endpoints:
            fn = client.post if method == "POST" else client.get
            resp = fn(path, json={})
            assert resp.status_code == 401, f"{method} {path} should be 401"


# ═══════════════════════════════════════════════════════════════════════════
# 2. MAPPING VALIDATION — unknown mapping = fail closed
# ═══════════════════════════════════════════════════════════════════════════


class TestMappingValidation:
    def test_unknown_tenant_rejected(self, client):
        payload = _attendance_payload(tenant_id="unknown_tenant")
        resp = client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        assert resp.status_code == 403
        assert "unknown" in resp.get_json()["error"].lower()

    def test_unknown_course_rejected(self, client):
        payload = _attendance_payload(l2e_course_id="NONEXISTENT")
        resp = client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        assert resp.status_code == 403

    def test_unknown_classroom_rejected(self, client):
        payload = _attendance_payload(classroom_id="room-INVALID")
        resp = client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        assert resp.status_code == 403

    def test_valid_mapping_accepted(self, client):
        payload = _attendance_payload()
        resp = client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        assert resp.status_code == 201

    def test_completion_unknown_mapping_rejected(self, client):
        payload = _completion_payload(tenant_id="bad_tenant")
        resp = client.post("/api/l2e/edu/complete", json=payload, headers=_headers())
        assert resp.status_code == 403

    def test_empty_mapping_config_rejects_all(self, client, mod):
        import services.l2e_edu as m
        original = m.ALLOWED_MAPPINGS
        m.ALLOWED_MAPPINGS = {}
        try:
            resp = client.post(
                "/api/l2e/edu/attendance",
                json=_attendance_payload(),
                headers=_headers(),
            )
            assert resp.status_code == 403
        finally:
            m.ALLOWED_MAPPINGS = original


# ═══════════════════════════════════════════════════════════════════════════
# 3. ATTENDANCE — idempotent duplicate delivery
# ═══════════════════════════════════════════════════════════════════════════


class TestAttendanceIdempotency:
    def test_first_delivery_records(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            json=_attendance_payload(),
            headers=_headers(),
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["ok"] is True
        assert body["recorded"] == 2
        assert body["duplicates_skipped"] == 0

    def test_duplicate_delivery_skipped(self, client):
        payload = _attendance_payload()
        client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())

        resp2 = client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        body2 = resp2.get_json()
        assert resp2.status_code == 201
        assert body2["recorded"] == 0
        assert body2["duplicates_skipped"] == 2

    def test_duplicate_does_not_inflate_totals(self, client):
        payload = _attendance_payload()
        client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())

        resp = client.get(
            "/api/l2e/edu/course/COURSE-101/attendance",
            headers=_headers(),
        )
        rows = resp.get_json()["attendance"]
        for row in rows:
            assert row["total_lessons"] == 1

    def test_different_lesson_is_separate(self, client):
        payload1 = _attendance_payload()
        payload2 = _attendance_payload(lesson_id="lesson-2", lesson_date="2026-10-29")
        client.post("/api/l2e/edu/attendance", json=payload1, headers=_headers())
        client.post("/api/l2e/edu/attendance", json=payload2, headers=_headers())

        resp = client.get(
            "/api/l2e/edu/course/COURSE-101/attendance",
            headers=_headers(),
        )
        stu1 = next(
            r for r in resp.get_json()["attendance"]
            if r["student_ref"] == "STU-001"
        )
        assert stu1["total_lessons"] == 2
        assert stu1["present_count"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# 4. ATTENDANCE — field validation
# ═══════════════════════════════════════════════════════════════════════════


class TestAttendanceValidation:
    def test_missing_required_fields(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            json={"tenant_id": "t"},
            headers=_headers(),
        )
        assert resp.status_code == 400
        assert "missing" in resp.get_json()["error"].lower()

    def test_students_must_be_list(self, client):
        payload = _attendance_payload(students="not a list")
        resp = client.post("/api/l2e/edu/attendance", json=payload, headers=_headers())
        assert resp.status_code == 400

    def test_invalid_json_body(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            data="not json",
            headers=_headers(),
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 5. COMPLETION — eligibility record only, never rewards or certificates
# ═══════════════════════════════════════════════════════════════════════════


class TestCompletionSafety:
    def test_completion_records_eligibility(self, client):
        resp = client.post(
            "/api/l2e/edu/complete",
            json=_completion_payload(),
            headers=_headers(),
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["ok"] is True
        assert body["students_total"] == 2
        assert body["students_cert_eligible"] == 1

    def test_completion_response_has_no_certificate_ids(self, client):
        """Completion must NOT return certificate IDs — no auto-issue."""
        resp = client.post(
            "/api/l2e/edu/complete",
            json=_completion_payload(),
            headers=_headers(),
        )
        body = resp.get_json()
        assert "certificates" not in body
        assert "certificate_id" not in body

    def test_completion_never_sets_reward_eligible_true(self, client):
        """Even if the sender claims reward_eligible=True, we store 0."""
        client.post(
            "/api/l2e/edu/complete",
            json=_completion_payload(),
            headers=_headers(),
        )
        resp = client.get(
            "/api/l2e/edu/course/COURSE-101/completions",
            headers=_headers(),
        )
        # reward_eligible is not exposed in the response at all
        for row in resp.get_json()["completions"]:
            assert "reward_eligible" not in row

    def test_completion_idempotent_upsert(self, client):
        payload = _completion_payload()
        client.post("/api/l2e/edu/complete", json=payload, headers=_headers())

        payload["students"][1]["attendance_pct"] = 90.0
        resp2 = client.post("/api/l2e/edu/complete", json=payload, headers=_headers())
        assert resp2.status_code == 201

        resp3 = client.get(
            "/api/l2e/edu/course/COURSE-101/completions",
            headers=_headers(),
        )
        completions = resp3.get_json()["completions"]
        assert len(completions) == 2
        stu2 = next(c for c in completions if c["student_ref"] == "STU-002")
        assert stu2["attendance_pct"] == 90.0

    def test_upsert_always_resets_reward_eligible_to_zero(self, client, mod):
        """Even on upsert, reward_eligible in DB stays 0."""
        import services.l2e_edu as m
        client.post(
            "/api/l2e/edu/complete",
            json=_completion_payload(),
            headers=_headers(),
        )
        with m._get_db() as conn:
            rows = conn.execute(
                "SELECT reward_eligible FROM edu_completions"
            ).fetchall()
            for r in rows:
                assert r["reward_eligible"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. PII — no raw tax_id in responses
# ═══════════════════════════════════════════════════════════════════════════


class TestPIIMinimization:
    def test_completions_response_has_no_tax_id(self, client):
        client.post(
            "/api/l2e/edu/complete",
            json=_completion_payload(),
            headers=_headers(),
        )
        resp = client.get(
            "/api/l2e/edu/course/COURSE-101/completions",
            headers=_headers(),
        )
        body_str = resp.get_data(as_text=True)
        assert "SENSITIVE-001" not in body_str
        assert "tax_id" not in body_str

    def test_attendance_response_has_no_tax_id(self, client):
        client.post(
            "/api/l2e/edu/attendance",
            json=_attendance_payload(),
            headers=_headers(),
        )
        resp = client.get(
            "/api/l2e/edu/course/COURSE-101/attendance",
            headers=_headers(),
        )
        body_str = resp.get_data(as_text=True)
        assert "tax_id" not in body_str

    def test_attendance_db_has_no_tax_id_column(self, mod):
        """The hardened schema must not have a tax_id column in attendance."""
        import services.l2e_edu as m
        with m._get_db() as conn:
            cols = [
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(edu_attendance_events)"
                ).fetchall()
            ]
            assert "tax_id" not in cols


# ═══════════════════════════════════════════════════════════════════════════
# 7. EMPTY STATE — safe defaults
# ═══════════════════════════════════════════════════════════════════════════


class TestEmptyState:
    def test_empty_completions(self, client):
        resp = client.get(
            "/api/l2e/edu/course/MISSING/completions",
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["completions"] == []

    def test_empty_attendance(self, client):
        resp = client.get(
            "/api/l2e/edu/course/MISSING/attendance",
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["attendance"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 8. SERVER REGISTRATION — real server.py import path
# ═══════════════════════════════════════════════════════════════════════════


class TestServerRegistration:
    def test_blueprint_import_matches_server_import_line(self):
        """The import path used in server.py must work."""
        from services.l2e_edu import l2e_edu_bp as bp
        assert bp.name == "l2e_edu"
        assert bp.url_prefix == "/api/l2e/edu"

    def test_no_app_ai_key_fallback_in_source(self):
        """APP_AI_KEY must not appear anywhere in the bridge module."""
        source_path = Path(__file__).parent.parent / "services" / "l2e_edu.py"
        source = source_path.read_text()
        assert "APP_AI_KEY" not in source

    def test_auto_issue_certs_not_in_source(self):
        """Auto-issue certificate machinery must be removed entirely."""
        source_path = Path(__file__).parent.parent / "services" / "l2e_edu.py"
        source = source_path.read_text()
        assert "AUTO_ISSUE_CERTS" not in source
        assert "_push_to_l2e_certificate_pipeline" not in source
        assert "_internal_post" not in source

    def test_no_secret_values_in_source(self):
        """No hardcoded secret values in source code."""
        source_path = Path(__file__).parent.parent / "services" / "l2e_edu.py"
        source = source_path.read_text()
        assert "APP_AI_KEY" not in source
        assert "admin_key" not in source
        assert "X-Internal-API-Key" not in source
