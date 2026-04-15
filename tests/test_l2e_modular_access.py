import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


def _client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def test_duplicate_enrollment_protection(monkeypatch):
    course_id = "c1"
    monkeypatch.setattr(server, "load_courses", lambda: [{"id": course_id, "teacher": "t1", "students": ["THR_DUP"]}])

    resp = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "thr",
        "student_thr": "THR_DUP",
        "auth_secret": "x",
    })
    assert resp.status_code == 409
    assert resp.get_json()["message"] == "Duplicate enrollment"


def test_stripe_student_enrollment_behavior(monkeypatch):
    course_id = "c2"
    courses = [{"id": course_id, "teacher": "teacher1", "price_thr": 10, "students": []}]
    enrollments = {}

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))

    resp = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_1",
        "stripe_payment_intent": "pi_abcdef12"
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["reward_eligible"] is False
    assert enrollments[course_id]["guest_1"]["access_only"] is True
    assert enrollments[course_id]["guest_1"]["reward_state"] == "not_eligible"


def test_duplicate_join_protection(monkeypatch):
    course_id = "c3"
    session_id = "s1"
    sessions = {course_id: [{"id": session_id, "access_type": "public", "attendance": ["learner1"], "max_seats": 0, "stream_url": "https://example.com/live"}]}

    monkeypatch.setattr(server, "load_live_sessions", lambda: sessions)
    monkeypatch.setattr(server, "save_live_sessions", lambda _: None)
    monkeypatch.setattr(server, "load_enrollments", lambda: {course_id: {"learner1": {"reward_eligible": True}}})

    resp = _client().post(f"/api/v1/courses/{course_id}/live_sessions/{session_id}/join", json={"learner_id": "learner1", "student_thr": "THR1"})
    assert resp.status_code == 409
    assert resp.get_json()["message"] == "Duplicate join"


def test_duplicate_reward_claim_protection(monkeypatch):
    course_id = "c4"
    monkeypatch.setattr(server, "load_courses", lambda: [{"id": course_id, "reward_l2e": 1.0, "reward_policy": "manual_claim"}])
    monkeypatch.setattr(server, "load_enrollments", lambda: {
        course_id: {
            "THR_CLAIMED": {"completed": True, "reward_eligible": True, "reward_claimed": True}
        }
    })

    resp = _client().post(f"/api/v1/courses/{course_id}/claim_reward", json={"learner_id": "THR_CLAIMED"})
    assert resp.status_code == 409
    assert resp.get_json()["reward_state"] == "claimed"


def test_pledge_only_session_access(monkeypatch):
    monkeypatch.setattr(server, "has_pledge_access", lambda _: True)
    allowed, reason = server._is_live_session_access_allowed(
        access_type="pledge-only",
        enrollment={"reward_eligible": True},
        learner_id="u1",
        student_thr="THR1",
        invitees=[],
    )
    assert allowed is True
    assert reason is None


def test_thr_wallet_only_session_access():
    allowed, _ = server._is_live_session_access_allowed(
        access_type="thr-wallet-only",
        enrollment={"reward_eligible": True},
        learner_id="u1",
        student_thr="THR1",
        invitees=[],
    )
    denied, reason = server._is_live_session_access_allowed(
        access_type="thr-wallet-only",
        enrollment={"reward_eligible": False},
        learner_id="u2",
        student_thr="",
        invitees=[],
    )
    assert allowed is True
    assert denied is False
    assert reason == "THR wallet required"


def test_course_completion_without_wallet(monkeypatch):
    course_id = "c5"
    courses = [{"id": course_id, "teacher": "TEACHER", "students": ["guest_2"], "reward_l2e": 5.0, "completions": {}, "completed": []}]
    enrollments = {course_id: {"guest_2": {"reward_eligible": False, "student_thr": None, "completed": False}}}

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda path, default=None: [] if path == server.CHAIN_FILE else {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "update_last_block", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "broadcast_tx", lambda *args, **kwargs: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/complete", json={
        "learner_id": "guest_2",
        "teacher_thr": "TEACHER",
        "auth_secret": "ok",
    })
    assert resp.status_code == 200
    tx = resp.get_json()["tx"]
    assert tx["status"] == "recorded"
    assert enrollments[course_id]["guest_2"]["reward_state"] == "completed_without_wallet"


def test_teacher_approval_policy_modeled_but_pending():
    enrollment = {
        "completed": True,
        "reward_eligible": True,
        "reward_claimed": False,
        "student_thr": "THR1",
    }
    course = {"reward_policy": "teacher_approval"}
    out = server._refresh_enrollment_reward_flags(enrollment, course=course)
    assert out["reward_claimability"] == "not_claimable"
    assert out["reward_policy_allows_claim"] is False
    assert "modeled but pending" in out.get("reward_policy_pending_note", "")


def test_quiz_completion_is_not_auto_reward(monkeypatch):
    course_id = "c6"
    courses = [{
        "id": course_id,
        "teacher": "TEACHER",
        "students": ["THR_STUDENT"],
        "reward_policy": "manual_claim",
        "certificate_enabled": True,
        "certificate_threshold_score": 50,
    }]
    enrollments = {course_id: {"THR_STUDENT": {"reward_eligible": True, "student_thr": "THR_STUDENT"}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [
            {"id": 1, "type": "multiple_choice", "correct": 0, "weight": 2, "options": ["a", "b"]},
            {"id": 2, "type": "multiple_choice", "correct": 1, "weight": 1, "options": ["a", "b"]},
        ],
    }

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda _: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={
        "student_thr": "THR_STUDENT",
        "answers": {"1": 0, "2": 1},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["passed"] is True
    assert body["reward_credited"] is False
    assert body["completion_status"] == "completed"
    assert body["reward_claimability"] == "claimable"
    assert body["certificate_status"] == "issuable"


def test_weighted_pass_fail_logic(monkeypatch):
    course_id = "c7"
    courses = [{"id": course_id, "teacher": "T", "students": ["S"], "reward_policy": "manual_claim", "certificate_enabled": False}]
    enrollments = {course_id: {"S": {"reward_eligible": True, "student_thr": "S"}}}
    quiz = {
        "pass_threshold_score": 60,
        "questions": [
            {"id": 1, "type": "multiple_choice", "correct": 0, "weight": 4, "options": ["a", "b"]},
            {"id": 2, "type": "multiple_choice", "correct": 1, "weight": 1, "options": ["a", "b"]},
        ],
    }
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda _: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)

    # Correct only low-weight question -> fail
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={"student_thr": "S", "answers": {"1": 1, "2": 1}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pass_fail_status"] == "fail"
    assert body["completion_status"] == "incomplete"


def test_certificate_blocked_when_threshold_not_met(monkeypatch):
    course_id = "c8"
    courses = [{
        "id": course_id,
        "teacher": "T",
        "students": ["S"],
        "reward_policy": "manual_claim",
        "certificate_enabled": True,
        "certificate_threshold_score": 101,
    }]
    enrollments = {course_id: {"S": {"reward_eligible": True, "student_thr": "S"}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda _: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={"student_thr": "S", "answers": {"1": 0}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["passed"] is True
    assert body["certificate_eligibility"] is False
    assert body["certificate_status"] == "not_enabled"  # eligible gate not satisfied


def test_certificate_pending_when_approval_mode_modeled(monkeypatch):
    course_id = "c9"
    courses = [{
        "id": course_id,
        "teacher": "T",
        "students": ["S"],
        "reward_policy": "manual_claim",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "certificate_threshold_score": 50,
    }]
    enrollments = {course_id: {"S": {"reward_eligible": True, "student_thr": "S"}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda _: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={"student_thr": "S", "answers": {"1": 0}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["certificate_eligibility"] is True
    assert body["certificate_status"] == "pending_approval"
