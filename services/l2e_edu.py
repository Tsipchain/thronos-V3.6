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
# Config
# ---------------------------------------------------------------------------

EDU_API_KEY: str = os.environ.get("EDU_API_KEY", "")
EDU_DB_PATH: str = os.environ.get("EDU_DB_PATH", "/app/data/l2e_edu.db")
ATTENDANCE_THRESHOLD_PCT: int = int(os.environ.get("L2E_ATTENDANCE_THRESHOLD_PCT", "80"))

# URL of the main chain's own L2E certificate API (self-referencing for auto-issue)
SELF_L2E_API_BASE: str = os.environ.get("SELF_API_BASE", "http://localhost:8000")
AUTO_ISSUE_CERTS: bool = os.environ.get("EDU_AUTO_ISSUE_CERTS", "true").lower() in {"1", "true", "yes"}

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
                l2e_cert_issued INTEGER NOT NULL DEFAULT 0,
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
# ---------------------------------------------------------------------------

@l2e_edu_bp.route("/attendance", methods=["POST"])
@_require_api_key
def receive_attendance():
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

    rows = [(
        tenant_id, course_id, classroom_id, lesson_id, lesson_date, lesson_title,
        s.get("student_external_ref", ""), s.get("student_name_hash", ""),
        s.get("thr_wallet", ""), s.get("tax_id", ""),
        s.get("attendance_status", "absent"), s.get("confirmation_method", ""),
        s.get("attestation_hash", ""), now,
    ) for s in students]

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

    logger.info("L2E EDU: recorded %d rows | course=%s lesson=%s", len(rows), course_id, lesson_id)
    return jsonify({"ok": True, "recorded": len(rows)}), 201


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
    issued_certs: list[dict] = []

    with _get_db() as conn:
        for s in students:
            ref            = s.get("student_external_ref", "")
            name_hash      = s.get("student_name_hash", "")
            thr_wallet     = s.get("thr_wallet", "")
            tax_id         = s.get("tax_id", "")
            attendance_pct = float(s.get("attendance_pct", 0))
            reward_elig    = bool(s.get("reward_eligible", False))
            cert_eligible  = attendance_pct >= ATTENDANCE_THRESHOLD_PCT

            cert_id = ""
            if cert_eligible:
                eligible_count += 1
                cert_id = _generate_certificate_id(tenant_id, course_id, ref, completed_at)
                cert_ids[ref] = cert_id
                issued_certs.append({
                    "student_ref": ref, "tax_id": tax_id, "thr_wallet": thr_wallet,
                    "course_id": course_id, "cert_id": cert_id,
                    "attendance_pct": attendance_pct,
                })

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
                (tenant_id, course_id, classroom_id, ref, name_hash, thr_wallet, tax_id,
                 attendance_pct, int(reward_elig), int(cert_eligible), cert_id,
                 completed_at, now),
            )

    logger.info("L2E EDU: completion | course=%s eligible=%d/%d", course_id, eligible_count, len(students))

    # Auto-push eligible students into the main chain L2E certificate pipeline
    if AUTO_ISSUE_CERTS and issued_certs:
        _push_to_l2e_certificate_pipeline(course_id, issued_certs)

    return jsonify({
        "ok": True,
        "course_id": course_id,
        "students_total": len(students),
        "students_eligible": eligible_count,
        "certificates": cert_ids,
    }), 201


# ---------------------------------------------------------------------------
# POST /api/l2e/edu/complete  — auto-push to existing L2E certificate pipeline
# ---------------------------------------------------------------------------

def _push_to_l2e_certificate_pipeline(course_id: str, issued_certs: list[dict]) -> None:
    """
    For each eligible student, ensure they have an L2E enrollment with
    certificate_eligibility=True, then auto-approve and issue.
    Uses the main chain's own internal REST API (loopback).
    """
    import urllib.request
    import urllib.error
    import json

    base = SELF_L2E_API_BASE.rstrip("/")
    # Use the internal admin key (same EDU_API_KEY or dedicated APP_AI_KEY)
    admin_key = os.environ.get("APP_AI_KEY", EDU_API_KEY)

    for cert in issued_certs:
        learner_id = cert["tax_id"] or cert["student_ref"]
        if not learner_id:
            continue
        try:
            # 1. Approve certificate
            _internal_post(
                f"{base}/api/v1/courses/{course_id}/certificates/{learner_id}/approve",
                {"actor_role": "system", "issuer_identity": "thronos-edupresence",
                 "approval_reason": f"Auto-approved: attendance {cert['attendance_pct']:.0f}%"},
                admin_key,
            )
            # 2. Issue certificate
            resp = _internal_post(
                f"{base}/api/v1/courses/{course_id}/certificates/{learner_id}/issue",
                {"issuer_identity": "thronos-edupresence",
                 "actor_role": "system"},
                admin_key,
            )
            issued_id = (resp or {}).get("certificate_id", "")
            if issued_id:
                # Store the issued L2E cert ID back in our DB
                with _get_db() as conn:
                    conn.execute(
                        "UPDATE edu_completions SET l2e_cert_issued=1, certificate_id=? "
                        "WHERE course_id=? AND student_ref=?",
                        (issued_id, course_id, cert["student_ref"]),
                    )
                logger.info("L2E EDU: issued cert %s for student %s course %s",
                            issued_id, learner_id, course_id)
        except Exception as exc:
            logger.warning("L2E EDU: cert auto-issue failed for %s: %s", learner_id, exc)


def _internal_post(url: str, payload: dict, api_key: str) -> dict | None:
    import urllib.request
    import json
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "X-Internal-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# GET /api/l2e/edu/course/<course_id>/completions
# GET /api/l2e/edu/course/<course_id>/attendance
# ---------------------------------------------------------------------------

@l2e_edu_bp.route("/course/<course_id>/completions", methods=["GET"])
@_require_api_key
def get_course_completions(course_id: str):
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM edu_completions WHERE course_id=? ORDER BY attendance_pct DESC",
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
            FROM edu_attendance_events WHERE course_id=?
            GROUP BY student_ref ORDER BY present_count DESC
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
