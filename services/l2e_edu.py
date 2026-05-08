"""
Thronos L2E — EDU Bridge Blueprint
Receives attendance & completion events from thronos-edupresence service.
Mount in server.py:
    from services.l2e_edu import l2e_edu_bp
    app.register_blueprint(l2e_edu_bp)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

l2e_edu_bp = Blueprint("l2e_edu", __name__, url_prefix="/api/l2e/edu")

# ---------------------------------------------------------------------------
# Config (read from env at import time)
# ---------------------------------------------------------------------------

EDU_API_KEY: str = os.environ.get("EDU_API_KEY", "")
EDU_DB_PATH: str = os.environ.get("EDU_DB_PATH", "/app/data/l2e_edu.db")
ATTENDANCE_THRESHOLD_PCT: int = int(os.environ.get("L2E_ATTENDANCE_THRESHOLD_PCT", "80"))

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    Path(EDU_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(EDU_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS edu_attendance_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT    NOT NULL,
                course_id       TEXT    NOT NULL,
                classroom_id    TEXT    NOT NULL,
                lesson_id       TEXT    NOT NULL,
                lesson_date     TEXT    NOT NULL,
                lesson_title    TEXT    NOT NULL DEFAULT '',
                student_ref     TEXT    NOT NULL,
                student_hash    TEXT    NOT NULL,
                thr_wallet      TEXT    NOT NULL DEFAULT '',
                tax_id          TEXT    NOT NULL DEFAULT '',
                status          TEXT    NOT NULL,
                method          TEXT    NOT NULL DEFAULT '',
                attestation     TEXT    NOT NULL DEFAULT '',
                received_at     TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edu_att_course
                ON edu_attendance_events(course_id, student_ref);

            CREATE TABLE IF NOT EXISTS edu_completions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT    NOT NULL,
                course_id       TEXT    NOT NULL,
                classroom_id    TEXT    NOT NULL,
                student_ref     TEXT    NOT NULL,
                student_hash    TEXT    NOT NULL,
                thr_wallet      TEXT    NOT NULL DEFAULT '',
                tax_id          TEXT    NOT NULL DEFAULT '',
                attendance_pct  REAL    NOT NULL,
                reward_eligible INTEGER NOT NULL DEFAULT 0,
                cert_eligible   INTEGER NOT NULL DEFAULT 0,
                certificate_id  TEXT    NOT NULL DEFAULT '',
                completed_at    TEXT    NOT NULL,
                processed_at    TEXT    NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_edu_comp_uniq
                ON edu_completions(course_id, student_ref);
        """)


_init_db()

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not EDU_API_KEY:
            logger.warning("EDU_API_KEY not configured — refusing request")
            return jsonify({"ok": False, "error": "service not configured"}), 503
        provided = request.headers.get("X-EDU-API-Key", "")
        if not hmac.compare_digest(provided, EDU_API_KEY):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# POST /api/l2e/edu/attendance
# Called by EduPresence when a lesson is closed.
# ---------------------------------------------------------------------------

@l2e_edu_bp.route("/attendance", methods=["POST"])
@_require_api_key
def receive_attendance():
    """
    Expected payload (from app/l2e_bridge.py in thronos-edupresence):
    {
      "tenant_id": "ministry_edu",
      "l2e_course_id": "COURSE-001",
      "classroom_id": "uuid",
      "lesson_id": "uuid",
      "lesson_date": "2026-05-08",
      "lesson_title": "Εισαγωγή",
      "students": [
        {
          "student_external_ref": "uuid",
          "student_name_hash": "abc123",
          "thr_wallet": "0x...",
          "tax_id": "123456789",
          "attendance_status": "present",
          "confirmation_method": "qr",
          "attestation_hash": "sha256hex"
        }
      ]
    }
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "invalid JSON"}), 400

    required = {"tenant_id", "l2e_course_id", "classroom_id", "lesson_id",
                "lesson_date", "students"}
    missing = required - set(data.keys())
    if missing:
        return jsonify({"ok": False, "error": f"missing fields: {missing}"}), 400

    now = datetime.now(timezone.utc).isoformat()
    tenant_id    = data["tenant_id"]
    course_id    = data["l2e_course_id"]
    classroom_id = data["classroom_id"]
    lesson_id    = data["lesson_id"]
    lesson_date  = data["lesson_date"]
    lesson_title = data.get("lesson_title", "")
    students     = data["students"]

    if not isinstance(students, list):
        return jsonify({"ok": False, "error": "students must be a list"}), 400

    rows = []
    for s in students:
        rows.append((
            tenant_id, course_id, classroom_id, lesson_id,
            lesson_date, lesson_title,
            s.get("student_external_ref", ""),
            s.get("student_name_hash", ""),
            s.get("thr_wallet", ""),
            s.get("tax_id", ""),
            s.get("attendance_status", "absent"),
            s.get("confirmation_method", ""),
            s.get("attestation_hash", ""),
            now,
        ))

    with _get_db() as conn:
        conn.executemany(
            """
            INSERT INTO edu_attendance_events
                (tenant_id, course_id, classroom_id, lesson_id, lesson_date,
                 lesson_title, student_ref, student_hash, thr_wallet, tax_id,
                 status, method, attestation, received_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )

    logger.info(
        "L2E EDU: recorded %d attendance rows | course=%s lesson=%s",
        len(rows), course_id, lesson_id,
    )
    return jsonify({"ok": True, "recorded": len(rows)}), 201


# ---------------------------------------------------------------------------
# POST /api/l2e/edu/complete
# Called by EduPresence when a classroom reaches its target hours.
# ---------------------------------------------------------------------------

@l2e_edu_bp.route("/complete", methods=["POST"])
@_require_api_key
def receive_completion():
    """
    Expected payload:
    {
      "tenant_id": "ministry_edu",
      "l2e_course_id": "COURSE-001",
      "classroom_id": "uuid",
      "completed_at": "2026-05-08T...",
      "students": [
        {
          "student_external_ref": "uuid",
          "student_name_hash": "abc123",
          "thr_wallet": "0x...",
          "tax_id": "123456789",
          "attendance_pct": 87.5,
          "reward_eligible": true
        }
      ]
    }
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "invalid JSON"}), 400

    required = {"tenant_id", "l2e_course_id", "classroom_id", "students"}
    missing = required - set(data.keys())
    if missing:
        return jsonify({"ok": False, "error": f"missing fields: {missing}"}), 400

    tenant_id    = data["tenant_id"]
    course_id    = data["l2e_course_id"]
    classroom_id = data["classroom_id"]
    completed_at = data.get("completed_at", datetime.now(timezone.utc).isoformat())
    students     = data["students"]
    now          = datetime.now(timezone.utc).isoformat()

    if not isinstance(students, list):
        return jsonify({"ok": False, "error": "students must be a list"}), 400

    eligible_count = 0
    cert_ids: dict[str, str] = {}

    with _get_db() as conn:
        for s in students:
            ref             = s.get("student_external_ref", "")
            name_hash       = s.get("student_name_hash", "")
            thr_wallet      = s.get("thr_wallet", "")
            tax_id          = s.get("tax_id", "")
            attendance_pct  = float(s.get("attendance_pct", 0))
            reward_eligible = bool(s.get("reward_eligible", False))
            cert_eligible   = attendance_pct >= ATTENDANCE_THRESHOLD_PCT

            cert_id = ""
            if cert_eligible:
                eligible_count += 1
                cert_id = _generate_certificate_id(
                    tenant_id, course_id, ref, completed_at
                )
                cert_ids[ref] = cert_id

            conn.execute(
                """
                INSERT INTO edu_completions
                    (tenant_id, course_id, classroom_id, student_ref,
                     student_hash, thr_wallet, tax_id, attendance_pct,
                     reward_eligible, cert_eligible, certificate_id,
                     completed_at, processed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(course_id, student_ref) DO UPDATE SET
                    attendance_pct  = excluded.attendance_pct,
                    reward_eligible = excluded.reward_eligible,
                    cert_eligible   = excluded.cert_eligible,
                    certificate_id  = excluded.certificate_id,
                    processed_at    = excluded.processed_at
                """,
                (
                    tenant_id, course_id, classroom_id, ref,
                    name_hash, thr_wallet, tax_id, attendance_pct,
                    int(reward_eligible), int(cert_eligible), cert_id,
                    completed_at, now,
                ),
            )

    logger.info(
        "L2E EDU: completion recorded | course=%s eligible=%d/%d",
        course_id, eligible_count, len(students),
    )

    return jsonify({
        "ok": True,
        "course_id": course_id,
        "students_total": len(students),
        "students_eligible": eligible_count,
        "certificates": cert_ids,
    }), 201


# ---------------------------------------------------------------------------
# GET /api/l2e/edu/course/<course_id>/completions  (admin / internal)
# ---------------------------------------------------------------------------

@l2e_edu_bp.route("/course/<course_id>/completions", methods=["GET"])
@_require_api_key
def get_course_completions(course_id: str):
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM edu_completions WHERE course_id = ? ORDER BY attendance_pct DESC",
            (course_id,),
        ).fetchall()
    return jsonify({"ok": True, "completions": [dict(r) for r in rows]})


@l2e_edu_bp.route("/course/<course_id>/attendance", methods=["GET"])
@_require_api_key
def get_course_attendance(course_id: str):
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT student_ref, student_hash, thr_wallet,
                   COUNT(*) AS total_lessons,
                   SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present_count
            FROM edu_attendance_events
            WHERE course_id = ?
            GROUP BY student_ref
            ORDER BY present_count DESC
            """,
            (course_id,),
        ).fetchall()
    return jsonify({"ok": True, "attendance": [dict(r) for r in rows]})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_certificate_id(tenant_id: str, course_id: str,
                              student_ref: str, completed_at: str) -> str:
    raw = f"{tenant_id}|{course_id}|{student_ref}|{completed_at}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:20].upper()
    return f"CERT-EDU-{digest}"
