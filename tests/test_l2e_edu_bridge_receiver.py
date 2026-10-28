"""
Tests for the L2E EDU bridge receiver blueprint (services/l2e_edu.py).

Uses a standalone Flask app with the blueprint registered so we don't
need the full server.py dependency tree.
"""
import os
import sqlite3
import tempfile
import sys
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_API_KEY = "test-edu-bridge-key-secret"


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch, tmp_path):
    db_path = str(tmp_path / "l2e_edu_test.db")
    monkeypatch.setenv("EDU_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("EDU_DB_PATH", db_path)
    monkeypatch.setenv("EDU_AUTO_ISSUE_CERTS", "false")


@pytest.fixture()
def app(_patch_env):
    import importlib
    import services.l2e_edu as mod
    importlib.reload(mod)

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(mod.l2e_edu_bp)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def _auth_headers():
    return {"X-EDU-API-Key": TEST_API_KEY, "Content-Type": "application/json"}


# ── Auth ────────────────────────────────────────────────────────────────


class TestAuth:
    def test_attendance_rejects_without_api_key(self, client):
        resp = client.post("/api/l2e/edu/attendance", json={"tenant_id": "t"})
        assert resp.status_code == 401

    def test_attendance_rejects_wrong_api_key(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            json={"tenant_id": "t"},
            headers={"X-EDU-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_complete_rejects_without_api_key(self, client):
        resp = client.post("/api/l2e/edu/complete", json={"tenant_id": "t"})
        assert resp.status_code == 401

    def test_completions_get_rejects_without_api_key(self, client):
        resp = client.get("/api/l2e/edu/course/c1/completions")
        assert resp.status_code == 401

    def test_attendance_get_rejects_without_api_key(self, client):
        resp = client.get("/api/l2e/edu/course/c1/attendance")
        assert resp.status_code == 401

    def test_returns_503_when_edu_api_key_not_configured(self, client, monkeypatch):
        import services.l2e_edu as mod
        monkeypatch.setattr(mod, "EDU_API_KEY", "")
        resp = client.post(
            "/api/l2e/edu/attendance",
            json={"tenant_id": "t"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 503
        assert "not configured" in resp.get_json()["error"]


# ── Attendance ──────────────────────────────────────────────────────────


class TestAttendance:
    def _valid_attendance_payload(self):
        return {
            "tenant_id": "ministry_edu",
            "l2e_course_id": "COURSE-101",
            "classroom_id": "room-A",
            "lesson_id": "lesson-1",
            "lesson_date": "2026-10-28",
            "lesson_title": "Intro to Blockchain",
            "students": [
                {
                    "student_external_ref": "STU-001",
                    "student_name_hash": "abc123",
                    "thr_wallet": "THR_WALLET_1",
                    "tax_id": "TAX001",
                    "attendance_status": "present",
                    "confirmation_method": "qr_scan",
                    "attestation_hash": "hash1",
                },
                {
                    "student_external_ref": "STU-002",
                    "student_name_hash": "def456",
                    "attendance_status": "absent",
                },
            ],
        }

    def test_records_attendance_successfully(self, client):
        payload = self._valid_attendance_payload()
        resp = client.post("/api/l2e/edu/attendance", json=payload, headers=_auth_headers())
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["ok"] is True
        assert body["recorded"] == 2

    def test_rejects_missing_fields(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            json={"tenant_id": "t"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "missing fields" in resp.get_json()["error"]

    def test_rejects_non_list_students(self, client):
        payload = self._valid_attendance_payload()
        payload["students"] = "not a list"
        resp = client.post("/api/l2e/edu/attendance", json=payload, headers=_auth_headers())
        assert resp.status_code == 400
        assert "must be a list" in resp.get_json()["error"]

    def test_rejects_invalid_json(self, client):
        resp = client.post(
            "/api/l2e/edu/attendance",
            data="not json",
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_attendance_persists_in_db(self, client):
        payload = self._valid_attendance_payload()
        client.post("/api/l2e/edu/attendance", json=payload, headers=_auth_headers())

        resp = client.get("/api/l2e/edu/course/COURSE-101/attendance", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert len(body["attendance"]) == 2
        present = next(s for s in body["attendance"] if s["student_ref"] == "STU-001")
        assert present["present_count"] == 1
        assert present["total_lessons"] == 1

    def test_multiple_lessons_aggregate(self, client):
        payload = self._valid_attendance_payload()
        client.post("/api/l2e/edu/attendance", json=payload, headers=_auth_headers())
        payload["lesson_id"] = "lesson-2"
        payload["lesson_date"] = "2026-10-29"
        client.post("/api/l2e/edu/attendance", json=payload, headers=_auth_headers())

        resp = client.get("/api/l2e/edu/course/COURSE-101/attendance", headers=_auth_headers())
        rows = resp.get_json()["attendance"]
        stu1 = next(s for s in rows if s["student_ref"] == "STU-001")
        assert stu1["total_lessons"] == 2
        assert stu1["present_count"] == 2


# ── Completion ──────────────────────────────────────────────────────────


class TestCompletion:
    def _valid_completion_payload(self):
        return {
            "tenant_id": "ministry_edu",
            "l2e_course_id": "COURSE-101",
            "classroom_id": "room-A",
            "completed_at": "2026-10-28T12:00:00Z",
            "students": [
                {
                    "student_external_ref": "STU-001",
                    "student_name_hash": "abc123",
                    "thr_wallet": "THR_WALLET_1",
                    "tax_id": "TAX001",
                    "attendance_pct": 95.0,
                    "reward_eligible": True,
                },
                {
                    "student_external_ref": "STU-002",
                    "student_name_hash": "def456",
                    "attendance_pct": 60.0,
                    "reward_eligible": False,
                },
            ],
        }

    def test_records_completion_successfully(self, client):
        payload = self._valid_completion_payload()
        resp = client.post("/api/l2e/edu/complete", json=payload, headers=_auth_headers())
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["ok"] is True
        assert body["students_total"] == 2
        assert body["students_eligible"] == 1
        assert "STU-001" in body["certificates"]
        assert "STU-002" not in body["certificates"]

    def test_below_threshold_not_cert_eligible(self, client):
        payload = self._valid_completion_payload()
        resp = client.post("/api/l2e/edu/complete", json=payload, headers=_auth_headers())
        body = resp.get_json()
        assert body["students_eligible"] == 1

    def test_rejects_missing_fields(self, client):
        resp = client.post(
            "/api/l2e/edu/complete",
            json={"tenant_id": "t", "l2e_course_id": "c"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

    def test_completions_persisted_and_queryable(self, client):
        payload = self._valid_completion_payload()
        client.post("/api/l2e/edu/complete", json=payload, headers=_auth_headers())

        resp = client.get("/api/l2e/edu/course/COURSE-101/completions", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert len(body["completions"]) == 2

        stu1 = next(c for c in body["completions"] if c["student_ref"] == "STU-001")
        assert stu1["attendance_pct"] == 95.0
        assert stu1["cert_eligible"] == 1
        assert stu1["certificate_id"].startswith("CERT-EDU-")

        stu2 = next(c for c in body["completions"] if c["student_ref"] == "STU-002")
        assert stu2["cert_eligible"] == 0

    def test_duplicate_completion_is_idempotent_upsert(self, client):
        payload = self._valid_completion_payload()
        resp1 = client.post("/api/l2e/edu/complete", json=payload, headers=_auth_headers())
        assert resp1.status_code == 201

        payload["students"][1]["attendance_pct"] = 90.0
        resp2 = client.post("/api/l2e/edu/complete", json=payload, headers=_auth_headers())
        assert resp2.status_code == 201
        assert resp2.get_json()["students_eligible"] == 2

        resp3 = client.get("/api/l2e/edu/course/COURSE-101/completions", headers=_auth_headers())
        completions = resp3.get_json()["completions"]
        assert len(completions) == 2
        stu2 = next(c for c in completions if c["student_ref"] == "STU-002")
        assert stu2["attendance_pct"] == 90.0
        assert stu2["cert_eligible"] == 1

    def test_certificate_id_is_deterministic(self, client):
        payload = self._valid_completion_payload()
        resp1 = client.post("/api/l2e/edu/complete", json=payload, headers=_auth_headers())
        certs1 = resp1.get_json()["certificates"]

        resp2 = client.post("/api/l2e/edu/complete", json=payload, headers=_auth_headers())
        certs2 = resp2.get_json()["certificates"]

        assert certs1["STU-001"] == certs2["STU-001"]

    def test_empty_course_completions_returns_empty_list(self, client):
        resp = client.get(
            "/api/l2e/edu/course/NONEXISTENT/completions",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["completions"] == []

    def test_empty_course_attendance_returns_empty_list(self, client):
        resp = client.get(
            "/api/l2e/edu/course/NONEXISTENT/attendance",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["attendance"] == []
