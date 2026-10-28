"""
Thronos L2E — EDU Bridge Blueprint (Hardened)

Receives attendance and completion events from thronos-edupresence.
All endpoints fail closed: no EDU_API_KEY = 503, unknown mapping = 403.
No automatic certificate issuance or reward minting.  Completion events
create auditable eligibility records only.

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
# Config — all defaults are fail-closed
# ---------------------------------------------------------------------------

EDU_API_KEY: str = os.environ.get("EDU_API_KEY", "")
EDU_DB_PATH: str = os.environ.get("EDU_DB_PATH", "/app/data/l2e_edu.db")
ATTENDANCE_THRESHOLD_PCT: int = int(
    os.environ.get("L2E_ATTENDANCE_THRESHOLD_PCT", "80")
)

# Allowed tenant→course→classroom mappings (JSON string).
# Format: {"tenant_id": {"course_id": ["classroom_id", ...]}}
# Empty or unparseable = reject all bridge events.
_ALLOWED_MAPPINGS_RAW: str = os.environ.get("EDU_ALLOWED_MAPPINGS", "")


def _load_allowed_mappings() -> dict[str, dict[str, list[str]]]:
    if not _ALLOWED_MAPPINGS_RAW:
        return {}
    try:
        parsed = json.loads(_ALLOWED_MAPPINGS_RAW)
        if not isinstance(parsed, dict):
            return {}
        return parsed
    except (json.JSONDecodeError, TypeError):
        logger.warning("EDU_ALLOWED_MAPPINGS is not valid JSON — rejecting all")
        return {}


ALLOWED_MAPPINGS: dict[str, dict[str, list[str]]] = _load_allowed_mappings()


def _is_mapping_allowed(tenant_id: str, course_id: str, classroom_id: str) -> bool:
    if not ALLOWED_MAPPINGS:
        return False
    tenant_courses = ALLOWED_MAPPINGS.get(tenant_id)
    if not tenant_courses or not isinstance(tenant_courses, dict):
        return False
    classrooms = tenant_courses.get(course_id)
    if classrooms is None:
        return False
    if isinstance(classrooms, list):
        return classroom_id in classrooms
    return False


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    Path(EDU_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(EDU_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
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
                status          TEXT    NOT NULL,
                method          TEXT    NOT NULL DEFAULT '',
                attestation     TEXT    NOT NULL DEFAULT '',
                received_at     TEXT    NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_edu_att_idempotent
                ON edu_attendance_events(
                    tenant_id, course_id, classroom_id,
                    lesson_id, student_ref
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
                attendance_pct  REAL    NOT NULL,
                reward_eligible INTEGER NOT NULL DEFAULT 0,
                cert_eligible   INTEGER NOT NULL DEFAULT 0,
                completed_at    TEXT    NOT NULL,
                processed_at    TEXT    NOT NULL DEFAULT ''
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_edu_comp_uniq
                ON edu_completions(course_id, student_ref);
        """)


_init_db()

# ---------------------------------------------------------------------------
# Auth — fail closed when EDU_API_KEY is empty
# ---------------------------------------------------------------------------


def _require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not EDU_API_KEY:
            logger.warning("EDU_API_KEY not configured — refusing request")
            return jsonify({"ok": False, "error": "service not configured"}), 503
        provided = request.headers.get("X-EDU-API-Key", "")
        if not provided or not hmac.compare_digest(provided, EDU_API_KEY):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# POST /api/l2e/edu/attendance
# ---------------------------------------------------------------------------


@l2e_edu_bp.route("/attendance", methods=["POST"])
@_require_api_key
def receive_attendance():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "invalid JSON"}), 400

    required = {
        "tenant_id", "l2e_course_id", "classroom_id",
        "lesson_id", "lesson_date", "students",
    }
    missing = required - set(data.keys())
    if missing:
        return jsonify({"ok": False, "error": f"missing fields: {sorted(missing)}"}), 400

    tenant_id = str(data["tenant_id"]).strip()
    course_id = str(data["l2e_course_id"]).strip()
    classroom_id = str(data["classroom_id"]).strip()
    lesson_id = str(data["lesson_id"]).strip()
    lesson_date = str(data["lesson_date"]).strip()
    lesson_title = str(data.get("lesson_title", "")).strip()
    students = data["students"]

    if not isinstance(students, list):
        return jsonify({"ok": False, "error": "students must be a list"}), 400

    if not _is_mapping_allowed(tenant_id, course_id, classroom_id):
        return jsonify({
            "ok": False,
            "error": "unknown tenant/course/classroom mapping",
        }), 403

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    skipped = 0

    with _get_db() as conn:
        for s in students:
            ref = str(s.get("student_external_ref", "")).strip()
            if not ref:
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO edu_attendance_events
                        (tenant_id, course_id, classroom_id, lesson_id,
                         lesson_date, lesson_title, student_ref, student_hash,
                         thr_wallet, status, method, attestation, received_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        tenant_id, course_id, classroom_id, lesson_id,
                        lesson_date, lesson_title,
                        ref,
                        str(s.get("student_name_hash", "")),
                        str(s.get("thr_wallet", "")),
                        str(s.get("attendance_status", "absent")),
                        str(s.get("confirmation_method", "")),
                        str(s.get("attestation_hash", "")),
                        now,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1

    logger.info(
        "L2E EDU attendance: course=%s lesson=%s inserted=%d skipped=%d",
        course_id, lesson_id, inserted, skipped,
    )
    return jsonify({"ok": True, "recorded": inserted, "duplicates_skipped": skipped}), 201


# ---------------------------------------------------------------------------
# POST /api/l2e/edu/complete
# ---------------------------------------------------------------------------


@l2e_edu_bp.route("/complete", methods=["POST"])
@_require_api_key
def receive_completion():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "invalid JSON"}), 400

    required = {"tenant_id", "l2e_course_id", "classroom_id", "students"}
    missing = required - set(data.keys())
    if missing:
        return jsonify({"ok": False, "error": f"missing fields: {sorted(missing)}"}), 400

    tenant_id = str(data["tenant_id"]).strip()
    course_id = str(data["l2e_course_id"]).strip()
    classroom_id = str(data["classroom_id"]).strip()
    completed_at = str(
        data.get("completed_at", datetime.now(timezone.utc).isoformat())
    ).strip()
    students = data["students"]
    now = datetime.now(timezone.utc).isoformat()

    if not isinstance(students, list):
        return jsonify({"ok": False, "error": "students must be a list"}), 400

    if not _is_mapping_allowed(tenant_id, course_id, classroom_id):
        return jsonify({
            "ok": False,
            "error": "unknown tenant/course/classroom mapping",
        }), 403

    eligible_count = 0

    with _get_db() as conn:
        for s in students:
            ref = str(s.get("student_external_ref", "")).strip()
            name_hash = str(s.get("student_name_hash", ""))
            thr_wallet = str(s.get("thr_wallet", ""))
            attendance_pct = float(s.get("attendance_pct", 0))
            cert_eligible = attendance_pct >= ATTENDANCE_THRESHOLD_PCT

            if cert_eligible:
                eligible_count += 1

            conn.execute(
                """
                INSERT INTO edu_completions
                    (tenant_id, course_id, classroom_id, student_ref,
                     student_hash, thr_wallet, attendance_pct,
                     reward_eligible, cert_eligible,
                     completed_at, processed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(course_id, student_ref) DO UPDATE SET
                    attendance_pct  = excluded.attendance_pct,
                    reward_eligible = 0,
                    cert_eligible   = excluded.cert_eligible,
                    processed_at    = excluded.processed_at
                """,
                (
                    tenant_id, course_id, classroom_id, ref, name_hash,
                    thr_wallet, attendance_pct,
                    0, int(cert_eligible),
                    completed_at, now,
                ),
            )

    logger.info(
        "L2E EDU completion: course=%s eligible=%d/%d",
        course_id, eligible_count, len(students),
    )

    return jsonify({
        "ok": True,
        "course_id": course_id,
        "students_total": len(students),
        "students_cert_eligible": eligible_count,
    }), 201


# ---------------------------------------------------------------------------
# GET /api/l2e/edu/course/<course_id>/completions
# GET /api/l2e/edu/course/<course_id>/attendance
#
# Returns only opaque references — no raw tax_id, no PII.
# ---------------------------------------------------------------------------


@l2e_edu_bp.route("/course/<course_id>/completions", methods=["GET"])
@_require_api_key
def get_course_completions(course_id: str):
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT student_ref, student_hash, attendance_pct,
                   cert_eligible, completed_at, processed_at
            FROM edu_completions WHERE course_id=?
            ORDER BY attendance_pct DESC
            """,
            (course_id,),
        ).fetchall()
    return jsonify({"ok": True, "completions": [dict(r) for r in rows]})


@l2e_edu_bp.route("/course/<course_id>/attendance", methods=["GET"])
@_require_api_key
def get_course_attendance(course_id: str):
    with _get_db() as conn:
        rows = conn.execute(
            """
            SELECT student_ref, student_hash,
                   COUNT(*) AS total_lessons,
                   SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present_count
            FROM edu_attendance_events WHERE course_id=?
            GROUP BY student_ref ORDER BY present_count DESC
            """,
            (course_id,),
        ).fetchall()
    return jsonify({"ok": True, "attendance": [dict(r) for r in rows]})
