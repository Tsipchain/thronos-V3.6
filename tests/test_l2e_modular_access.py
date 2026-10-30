import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


def _client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def _patch_edu_token_state(monkeypatch):
    """Provide in-memory durable token state for tests that create/verify tokens."""
    state = {"nonces": {}, "revoked": []}
    def _load():
        return copy.deepcopy(state)
    def _save(new_state):
        state.clear()
        state.update(copy.deepcopy(new_state))
    monkeypatch.setattr(server, "_load_edu_token_state", _load)
    monkeypatch.setattr(server, "_save_edu_token_state", _save)
    return state


def _patch_wallet_challenges(monkeypatch):
    """Provide in-memory wallet challenge state for tests."""
    challenges = {}
    def _load():
        return copy.deepcopy(challenges)
    def _save(data):
        challenges.clear()
        challenges.update(copy.deepcopy(data))
    monkeypatch.setattr(server, "_load_wallet_challenges", _load)
    monkeypatch.setattr(server, "_save_wallet_challenges", _save)
    return challenges


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


def test_stripe_student_enrollment_blocked(monkeypatch):
    """Stripe course enrollment is deliberately blocked until a verified
    Stripe webhook flow is implemented.  The endpoint must return 503."""
    course_id = "c2"
    courses = [{"id": course_id, "teacher": "teacher1", "price_thr": 10, "students": []}]

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "load_enrollments", lambda: {})
    monkeypatch.setattr(server, "save_enrollments", lambda _: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_1",
        "stripe_payment_intent": "pi_abcdef12"
    })
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"] == "course_stripe_checkout_not_enabled"


def test_enrollment_hydration_failure_stripe_blocked(monkeypatch):
    """Stripe enrollment is blocked before hydration logic runs."""
    course_id = "c2b"
    courses = [{"id": course_id, "teacher": "teacher1", "price_thr": 10, "students": []}]

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "load_enrollments", lambda: {})
    monkeypatch.setattr(server, "save_enrollments", lambda _: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_hydration_fail",
        "stripe_payment_intent": "pi_hydrate1234",
    })
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "course_stripe_checkout_not_enabled"


def test_route_wiring_smoke_and_aliases(monkeypatch):
    course_id = "c_routes"
    learner_id = "did:thr/mainnet:wallet/alpha"
    courses = [{
        "id": course_id,
        "title": "Routing Course",
        "teacher": "teacher1",
        "price_thr": 5,
        "students": [learner_id],
        "reward_l2e": 1.0,
        "reward_policy": "manual_claim",
        "metadata": {"quiz": {"questions": [{"id": 1, "text": "Q1", "options": ["A", "B"], "correct_index": 0}]}},
    }]
    enrollments = {
        course_id: {
            learner_id: {
                "reward_eligible": False,
                "completed": False,
                "payment_method": "stripe",
            }
        }
    }
    live = {course_id: [{"id": "s1", "title": "Session 1", "attendance": []}]}

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "load_live_sessions", lambda: live)

    v1_live = _client().get(f"/api/v1/courses/{course_id}/live_sessions")
    assert v1_live.status_code == 200
    alias_live = _client().get(f"/api/courses/{course_id}/live_sessions")
    assert alias_live.status_code == 200

    v1_quiz = _client().get(f"/api/v1/courses/{course_id}/quiz")
    assert v1_quiz.status_code == 200
    alias_quiz = _client().get(f"/api/courses/{course_id}/quiz")
    assert alias_quiz.status_code == 200

    v1_enroll_status = _client().get(f"/api/v1/courses/{course_id}/enrollment/{learner_id}")
    assert v1_enroll_status.status_code == 200
    alias_enroll_status = _client().get(f"/api/courses/{course_id}/enrollment/{learner_id}")
    assert alias_enroll_status.status_code == 200

    claim_v1 = _client().post(f"/api/v1/courses/{course_id}/claim_reward", json={"learner_id": learner_id})
    assert claim_v1.status_code == 403
    claim_alias = _client().post(f"/api/courses/{course_id}/claim_reward", json={"learner_id": learner_id})
    assert claim_alias.status_code == 403


def test_stripe_second_click_also_blocked(monkeypatch):
    """Both attempts should be blocked since Stripe enrollment is not enabled."""
    course_id = "c_dup_retry"
    courses = [{"id": course_id, "teacher": "teacher1", "price_thr": 5, "students": []}]

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "load_enrollments", lambda: {})
    monkeypatch.setattr(server, "save_enrollments", lambda _: None)

    first = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_retry",
        "stripe_payment_intent": "pi_retry12345",
    })
    assert first.status_code == 503

    second = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_retry",
        "stripe_payment_intent": "pi_retry12345",
    })
    assert second.status_code == 503


def test_certificate_lifecycle_pending_states():
    enrollment = {"certificate_eligibility": True, "certificate_approved": False}
    teacher_course = {"certificate_enabled": True, "certificate_approval_mode": "teacher_approval"}
    admin_course = {"certificate_enabled": True, "certificate_approval_mode": "admin_approval"}
    manual_course = {"certificate_enabled": True, "certificate_approval_mode": "manual"}

    assert server._compute_certificate_lifecycle_state(enrollment, teacher_course) == "eligible"
    assert server._compute_certificate_lifecycle_state(enrollment, admin_course) == "eligible"
    assert server._compute_certificate_lifecycle_state(enrollment, manual_course) == "eligible"


def test_no_auto_certificate_on_quiz_pass(monkeypatch):
    course_id = "c_cert_no_auto"
    courses = [{
        "id": course_id,
        "teacher": "T",
        "students": ["S"],
        "reward_policy": "manual_claim",
        "certificate_enabled": True,
        "certificate_threshold_score": 70,
        "certificate_approval_mode": "teacher_approval",
    }]
    enrollments = {course_id: {"S": {"reward_eligible": True, "student_thr": "S"}}}
    quiz = {
        "pass_threshold_score": 60,
        "questions": [
            {"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]},
        ],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token("S", course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": "S", "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["certificate_status"] != "issued"
    assert body["result_state"]["states"]["certificate_lifecycle_state"] == "eligible"


def test_certificate_eligibility_threshold_logic(monkeypatch):
    course_id = "c_cert_threshold"
    courses = [{
        "id": course_id,
        "teacher": "T",
        "students": ["S"],
        "reward_policy": "manual_claim",
        "certificate_enabled": True,
        "certificate_threshold_score": 80,
        "certificate_approval_mode": "manual",
    }]
    enrollments = {course_id: {"S": {"reward_eligible": True, "student_thr": "S"}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [
            {"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]},
            {"id": 2, "type": "multiple_choice", "correct": 1, "weight": 1, "options": ["a", "b"]},
        ],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token("S", course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": "S", "answers": {"1": 0, "2": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["passed"] is True
    assert body["certificate_eligibility"] is False
    assert body["result_state"]["states"]["certificate_eligibility"] is False


def test_result_state_separation_and_thresholds(monkeypatch):
    course = {
        "metadata": {"quiz": {"pass_score": 60}},
        "certificate_enabled": True,
        "certificate_threshold_score": 85,
        "certificate_approval_mode": "admin_approval",
        "tenant_id": "tenant-A",
        "institution_id": "inst-A",
        "tenant_course_notes": "Owned by tenant A academic board",
        "teacher": "TEACHER",
        "reward_policy": "manual_claim",
    }
    enrollment = {
        "quiz_score": 72,
        "completed": True,
        "pass_fail_status": "pass",
        "certificate_eligibility": False,
        "reward_eligible": True,
        "reward_eligibility": "eligible",
        "reward_claimability": "claimable",
    }
    out = server._build_academic_result_state(enrollment, course)
    assert out["score"]["quiz_pass_threshold"] == 60
    assert out["score"]["certificate_threshold"] == 85
    assert out["states"]["pass_fail_status"] == "pass"
    assert out["states"]["certificate_eligibility"] is False
    assert out["states"]["reward_eligibility"] == "eligible"
    assert out["tenant"]["tenant_id"] == "tenant-A"
    assert out["tenant"]["tenant_course_notes"] == "Owned by tenant A academic board"


def test_teacher_approval_path(monkeypatch):
    course_id = "c_phase3_teacher"
    learner = "L1"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "certificate_issuer_identity": "T1",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    }]
    enrollments = {course_id: {learner: {"certificate_eligibility": True, "tenant_id": "tenantX", "institution_id": "instX"}}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())

    req = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/request_approval", json={
        "actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX"
    })
    assert req.status_code == 200
    assert req.get_json()["certificate_lifecycle_state"] == "pending_approval"

    approve = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/approve", json={
        "actor_thr": "T1", "auth_secret": "ok", "approval_reason": "met rubric", "tenant_id": "tenantX", "institution_id": "instX"
    })
    assert approve.status_code == 200
    assert approve.get_json()["certificate_lifecycle_state"] == "issuable"


def test_admin_approval_path(monkeypatch):
    course_id = "c_phase3_admin"
    learner = "L2"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "certificate_enabled": True,
        "certificate_approval_mode": "admin_approval",
        "certificate_issuer_identity": "T1",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    }]
    enrollments = {course_id: {learner: {"certificate_eligibility": True, "certificate_approval_requested": True, "tenant_id": "tenantX", "institution_id": "instX"}}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "require_admin", lambda *_: None)

    approve = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/approve", json={
        "tenant_id": "tenantX", "institution_id": "instX"
    })
    assert approve.status_code == 200
    assert approve.get_json()["certificate_lifecycle_state"] == "issuable"


def test_rejection_path(monkeypatch):
    course_id = "c_phase3_reject"
    learner = "L3"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    }]
    enrollments = {course_id: {learner: {"certificate_eligibility": True, "certificate_approval_requested": True, "tenant_id": "tenantX", "institution_id": "instX"}}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())

    reject = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/reject", json={
        "actor_thr": "T1", "auth_secret": "ok", "rejection_reason": "missing assignment", "tenant_id": "tenantX", "institution_id": "instX"
    })
    assert reject.status_code == 200
    assert reject.get_json()["certificate_lifecycle_state"] == "rejected"


def test_issuance_path(monkeypatch):
    course_id = "c_phase3_issue"
    learner = "L4"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "certificate_issuer_identity": "T1",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    }]
    enrollments = {course_id: {learner: {
        "certificate_eligibility": True,
        "certificate_approval_requested": True,
        "certificate_approved": True,
        "tenant_id": "tenantX",
        "institution_id": "instX",
    }}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())

    issued = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/issue", json={
        "actor_thr": "T1", "auth_secret": "ok", "issuer_identity": "T1", "tenant_id": "tenantX", "institution_id": "instX"
    })
    assert issued.status_code == 200
    body = issued.get_json()
    assert body["certificate_lifecycle_state"] == "issued"
    assert body["certificate_id"]
    assert body["issued_at"]


def test_tenant_ownership_mismatch_blocked(monkeypatch):
    course_id = "c_phase3_tenant_block"
    learner = "L5"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "tenant_id": "tenantA",
        "institution_id": "instA",
    }]
    enrollments = {course_id: {learner: {"certificate_eligibility": True, "tenant_id": "tenantA", "institution_id": "instA"}}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())

    blocked = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/request_approval", json={
        "actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantB", "institution_id": "instA"
    })
    assert blocked.status_code == 403
    assert "Tenant ownership mismatch" in blocked.get_json()["message"]


def test_role_based_access_blocking_student_cannot_issue(monkeypatch):
    course_id = "c_phase4_role_block"
    learner = "L6"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "certificate_issuer_identity": "T1",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    }]
    enrollments = {course_id: {learner: {"certificate_eligibility": True, "certificate_approval_requested": True, "certificate_approved": True, "tenant_id": "tenantX", "institution_id": "instX"}}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())

    denied = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/issue", json={
        "actor_thr": learner,
        "actor_role": "student",
        "issuer_identity": "T1",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    })
    assert denied.status_code == 403
    assert "Role not allowed" in denied.get_json()["message"]


def test_audit_trail_persistence_and_history_endpoints(monkeypatch):
    course_id = "c_phase4_audit"
    learner = "L7"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "certificate_issuer_identity": "T1",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    }]
    enrollments = {course_id: {learner: {"certificate_eligibility": True, "tenant_id": "tenantX", "institution_id": "instX"}}}
    audit_store = {}

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())
    monkeypatch.setattr(server, "load_certificate_audit", lambda: audit_store)
    monkeypatch.setattr(server, "save_certificate_audit", lambda a: audit_store.update(copy.deepcopy(a)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})

    _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/request_approval", json={
        "actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX", "approval_reason": "request"
    })
    _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/approve", json={
        "actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX", "approval_reason": "approved"
    })
    _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/issue", json={
        "actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX", "issuer_identity": "T1"
    })

    learner_history = _client().get(
        f"/api/v1/courses/{course_id}/certificates/{learner}/history",
        query_string={"actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX"}
    )
    assert learner_history.status_code == 200
    rows = learner_history.get_json()["history"]
    assert len(rows) >= 3
    assert {r["action"] for r in rows}.issuperset({"approval_requested", "approved", "issued"})

    course_history = _client().get(
        f"/api/v1/courses/{course_id}/certificates/history",
        query_string={"actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX"}
    )
    assert course_history.status_code == 200
    assert any(r["learner_id"] == learner for r in course_history.get_json()["history"])

    result_history = _client().get(
        f"/api/v1/courses/{course_id}/results/{learner}/history",
        query_string={"actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX"}
    )
    assert result_history.status_code == 200
    assert isinstance(result_history.get_json()["certificate_history"], list)


def test_tenant_scoped_visibility_restrictions(monkeypatch):
    courses = [
        {"id": "c_tenant_a", "teacher": "TA", "tenant_id": "tenantA", "institution_id": "instA"},
        {"id": "c_tenant_b", "teacher": "TB", "tenant_id": "tenantB", "institution_id": "instB"},
    ]
    audit_store = {
        "c_tenant_a": {"L1": [{"action": "approved", "to_state": "issuable"}]},
        "c_tenant_b": {"L2": [{"action": "approved", "to_state": "issuable"}]},
    }
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: audit_store)
    monkeypatch.setattr(server, "require_admin", lambda *_: None)

    resp = _client().get(
        "/api/v1/tenants/tenantA/audit/history",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenantA"},
    )
    assert resp.status_code == 200
    rows = resp.get_json()["history"]
    assert all(r["course_id"] == "c_tenant_a" for r in rows)

    denied = _client().get(
        "/api/v1/tenants/tenantA/audit/history",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenantB"},
    )
    assert denied.status_code == 403


def test_role_scoped_history_access_blocking(monkeypatch):
    course_id = "c_phase5_role_history"
    learner = "L8"
    courses = [{"id": course_id, "teacher": "T1", "tenant_id": "tenantX", "institution_id": "instX"}]
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: {course_id: {learner: [{"action": "approved"}]}})
    monkeypatch.setattr(server, "require_admin", lambda *_: object())

    denied = _client().get(
        f"/api/v1/courses/{course_id}/certificates/{learner}/history",
        query_string={"actor_thr": learner, "actor_role": "student"},
    )
    assert denied.status_code == 403


def test_export_ready_history_payload_correctness(monkeypatch):
    course_id = "c_phase5_export"
    courses = [{"id": course_id, "teacher": "T1", "tenant_id": "tenantX", "institution_id": "instX"}]
    audit_store = {course_id: {"L9": [{"action": "issued", "to_state": "issued"}]}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: audit_store)
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())

    resp = _client().get(
        f"/api/v1/courses/{course_id}/certificates/history/export",
        query_string={"actor_thr": "T1", "auth_secret": "ok", "tenant_id": "tenantX", "institution_id": "instX"},
    )
    assert resp.status_code == 200
    export = resp.get_json()["export"]
    assert export["schema_version"] == "l2e_cert_history_v1"
    assert export["tenant_id"] == "tenantX"
    assert len(export["rows"]) == 1


def test_delegate_operator_boundaries(monkeypatch):
    course_id = "c_phase5_delegate"
    learner = "L10"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "tenant_id": "tenantX",
        "institution_id": "instX",
        "certificate_enabled": True,
        "certificate_approval_mode": "teacher_approval",
        "delegate_operators": ["OP1"],
    }]
    enrollments = {course_id: {learner: {"certificate_eligibility": True, "tenant_id": "tenantX", "institution_id": "instX"}}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "require_admin", lambda *_: None)

    ok = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/request_approval", json={
        "actor_thr": "OP1", "actor_role": "delegate_operator", "tenant_id": "tenantX", "institution_id": "instX"
    })
    assert ok.status_code == 200

    denied = _client().post(f"/api/v1/courses/{course_id}/certificates/{learner}/request_approval", json={
        "actor_thr": "OP2", "actor_role": "delegate_operator", "tenant_id": "tenantX", "institution_id": "instX"
    })
    assert denied.status_code == 403


def test_policy_evaluation_structure_correctness(monkeypatch):
    course_id = "c_phase6_policy"
    courses = [{"id": course_id, "teacher": "T1", "tenant_id": "tenantX", "institution_id": "instX"}]
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())
    resp = _client().post(f"/api/v1/courses/{course_id}/policy/evaluate", json={
        "action": "view_history",
        "actor_thr": "T1",
        "auth_secret": "ok",
        "actor_role": "teacher",
        "tenant_id": "tenantX",
        "institution_id": "instX",
    })
    assert resp.status_code == 200
    evaluation = resp.get_json()["evaluation"]
    assert evaluation["policy_version"] == "l2e_policy_v1"
    assert "constraints" in evaluation
    assert "tenant_context" in evaluation
    assert evaluation["allowed"] is True


def test_export_report_access_restrictions(monkeypatch):
    course_id = "c_phase6_export_restrict"
    courses = [{"id": course_id, "teacher": "T1", "tenant_id": "tenantX", "institution_id": "instX"}]
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: {course_id: {"L1": [{"action": "approved"}]}})
    monkeypatch.setattr(server, "require_admin", lambda *_: object())
    denied = _client().get(
        f"/api/v1/courses/{course_id}/certificates/history/export",
        query_string={"actor_thr": "L1", "actor_role": "student", "tenant_id": "tenantX"},
    )
    assert denied.status_code == 403


def test_tenant_admin_reporting_boundaries(monkeypatch):
    courses = [{"id": "c1", "teacher": "T1", "tenant_id": "tenantA", "institution_id": "instA"}]
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: {"c1": {"L1": [{"action": "issued", "to_state": "issued"}]}})
    monkeypatch.setattr(server, "require_admin", lambda *_: None)
    ok = _client().get(
        "/api/v1/tenants/tenantA/reports/operational",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenantA"},
    )
    assert ok.status_code == 200
    denied = _client().get(
        "/api/v1/tenants/tenantA/reports/operational",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenantB"},
    )
    assert denied.status_code == 403


def test_delegate_operator_reporting_restrictions(monkeypatch):
    courses = [{"id": "c2", "teacher": "T2", "tenant_id": "tenantA", "institution_id": "instA"}]
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: {"c2": {"L2": [{"action": "issued", "to_state": "issued"}]}})
    monkeypatch.setattr(server, "require_admin", lambda *_: None)
    denied = _client().get(
        "/api/v1/tenants/tenantA/reports/operational",
        query_string={"actor_role": "delegate_operator", "tenant_id": "tenantB"},
    )
    assert denied.status_code == 403


def test_audit_report_consistency(monkeypatch):
    courses = [{"id": "c3", "teacher": "T3", "tenant_id": "tenantA", "institution_id": "instA"}]
    audit = {"c3": {"L3": [{"action": "approval_requested"}, {"action": "approved"}, {"action": "issued"}]}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: audit)
    monkeypatch.setattr(server, "require_admin", lambda *_: None)
    rep = _client().get(
        "/api/v1/tenants/tenantA/reports/operational",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenantA"},
    )
    assert rep.status_code == 200
    counts = rep.get_json()["report"]["counts"]
    assert counts["approval_requested"] == 1
    assert counts["approved"] == 1
    assert counts["issued"] == 1


def test_external_policy_compatible_evaluation_structure(monkeypatch):
    course_id = "c_phase7_policy_compat"
    courses = [{"id": course_id, "teacher": "T7", "tenant_id": "tenant7", "institution_id": "inst7"}]
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda *_: object())
    resp = _client().post(f"/api/v1/courses/{course_id}/policy/evaluate", json={
        "action": "approve",
        "actor_thr": "T7",
        "auth_secret": "ok",
        "actor_role": "teacher",
        "tenant_id": "tenant7",
        "institution_id": "inst7",
        "engine": "opa",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["external_compat"]["engine_name"] == "opa"
    assert body["external_compat"]["policy_version"] == "l2e_policy_v1"


def test_governed_report_delivery_boundaries(monkeypatch):
    monkeypatch.setattr(server, "require_admin", lambda *_: None)
    created = _client().post(
        "/api/v1/tenants/tenantZ/reports/deliveries",
        json={"actor_role": "tenant_admin", "tenant_id": "tenantZ", "report_type": "operational"},
    )
    assert created.status_code == 201

    denied = _client().post(
        "/api/v1/tenants/tenantZ/reports/deliveries",
        json={"actor_role": "tenant_admin", "tenant_id": "tenantX", "report_type": "operational"},
    )
    assert denied.status_code == 403


def test_dashboard_observability_restrictions(monkeypatch):
    course_id = "c_phase7_obs"
    courses = [{"id": course_id, "teacher": "T7", "tenant_id": "tenant7", "institution_id": "inst7"}]
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: {course_id: {"L1": [{"action": "approved", "actor_role": "teacher"}]}})
    monkeypatch.setattr(server, "require_admin", lambda *_: object())
    denied = _client().get(f"/api/v1/courses/{course_id}/observability", query_string={"actor_thr": "L1", "actor_role": "student"})
    assert denied.status_code == 403


def test_tenant_admin_delivery_separation(monkeypatch):
    monkeypatch.setattr(server, "require_admin", lambda *_: None)
    save_store = {}
    monkeypatch.setattr(server, "load_report_deliveries", lambda: save_store)
    monkeypatch.setattr(server, "save_report_deliveries", lambda d: save_store.update(copy.deepcopy(d)))
    ok = _client().post(
        "/api/v1/tenants/tenantA/reports/deliveries",
        json={"actor_role": "tenant_admin", "tenant_id": "tenantA", "report_type": "audit_history"},
    )
    assert ok.status_code == 201
    bad = _client().get(
        "/api/v1/tenants/tenantA/reports/deliveries",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenantB"},
    )
    assert bad.status_code == 403


def test_audit_and_report_integrity(monkeypatch):
    courses = [{"id": "c_phase7_int", "teacher": "T7", "tenant_id": "tenant7", "institution_id": "inst7"}]
    audit = {"c_phase7_int": {"L1": [{"action": "approval_requested"}, {"action": "issued"}]}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: audit)
    monkeypatch.setattr(server, "require_admin", lambda *_: None)
    rep = _client().get(
        "/api/v1/tenants/tenant7/reports/operational",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenant7"},
    )
    assert rep.status_code == 200
    counts = rep.get_json()["report"]["counts"]
    assert counts["approval_requested"] == 1
    assert counts["issued"] == 1


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
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token("THR_STUDENT", course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": "THR_STUDENT", "answers": {"1": 0, "2": 1}},
        headers={"X-Student-Token": token},
    )
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
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda _: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    # Correct only low-weight question -> fail
    token = server.create_edu_student_token("S", course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": "S", "answers": {"1": 1, "2": 1}},
        headers={"X-Student-Token": token},
    )
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
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda _: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token("S", course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": "S", "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
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
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda _: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token("S", course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": "S", "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["certificate_eligibility"] is True
    assert body["certificate_status"] == "pending_approval"


def test_l2e_rollout_verification_course_end_to_end_flow(monkeypatch):
    """Go-live verification flow using a dedicated rollout course and lesson."""
    courses = []
    enrollments = {}
    audit_store = {}
    deliveries_store = {}
    mempool = []
    json_store = {
        server.LEDGER_FILE: {"THR_STUDENT_ROLLOUT": 500.0, "THR_TEACHER_ROLLOUT": 0.0},
        server.CHAIN_FILE: [],
        str(Path(server.DATA_DIR) / "quiz_attempts.json"): {},
    }

    def _load_json(path, default=None):
        if path in json_store:
            return copy.deepcopy(json_store[path])
        return copy.deepcopy(default if default is not None else {})

    def _save_json(path, value):
        json_store[path] = copy.deepcopy(value)

    def _save_courses(data):
        snap = copy.deepcopy(data)
        courses.clear()
        courses.extend(snap)

    def _save_enrollments(data):
        snap = copy.deepcopy(data)
        enrollments.clear()
        enrollments.update(snap)

    def _save_audit(data):
        snap = copy.deepcopy(data)
        audit_store.clear()
        audit_store.update(snap)

    def _save_deliveries(data):
        snap = copy.deepcopy(data)
        deliveries_store.clear()
        deliveries_store.update(snap)

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", _save_courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", _save_enrollments)
    monkeypatch.setattr(server, "load_certificate_audit", lambda: audit_store)
    monkeypatch.setattr(server, "save_certificate_audit", _save_audit)
    monkeypatch.setattr(server, "load_report_deliveries", lambda: deliveries_store)
    monkeypatch.setattr(server, "save_report_deliveries", _save_deliveries)
    monkeypatch.setattr(server, "load_json", _load_json)
    monkeypatch.setattr(server, "save_json", _save_json)
    monkeypatch.setattr(server, "load_mempool", lambda: copy.deepcopy(mempool))
    monkeypatch.setattr(server, "save_mempool", lambda p: (mempool.clear(), mempool.extend(copy.deepcopy(p))))
    monkeypatch.setattr(server, "broadcast_tx", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "update_last_block", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "validate_effective_auth", lambda *_args, **_kwargs: (True, None, None))
    monkeypatch.setattr(server, "require_admin", lambda payload=None: None if (payload or {}).get("auth_secret") == "admin-ok" else "auth_required")

    # 1) Create verification course + lesson content + quiz
    create_resp = _client().post("/api/v1/courses", json={
        "title": "L2E Rollout Verification Course",
        "description": "Final go-live verification path",
        "teacher": "THR_TEACHER_ROLLOUT",
        "price_thr": 15,
        "reward_l2e": 5,
        "reward_policy": "manual_claim",
        "tenant_id": "tenant-rollout",
        "institution_id": "inst-rollout",
        "certificate_enabled": True,
        "certificate_threshold_score": 80,
        "certificate_approval_mode": "teacher_approval",
        "certificate_template_name": "L2E Rollout Completion Certificate",
        "certificate_issuer_identity": "THR_TEACHER_ROLLOUT",
        "content_type": "external",
        "content_url": "https://example.org/l2e-rollout-lesson-1",
        "quiz": {
            "title": "Rollout Quiz",
            "pass_score": 70,
            "questions": [
                {
                    "question": "What remains mandatory in L2E rollout?",
                    "options": ["Automatic issuance", "RBAC + tenant boundaries", "No policy checks", "Skip audit controls"],
                    "correct": 1,
                    "type": "multiple_choice",
                    "weight": 1,
                }
            ],
        },
        "auth_secret": "ok",
    })
    assert create_resp.status_code == 201
    created_payload = create_resp.get_json()
    course_id = created_payload.get("course_id") or (created_payload.get("course") or {}).get("id") or created_payload.get("id")
    assert course_id

    # 2) Verify THR price and confirm Stripe enrollment is blocked (503)
    course_details = _client().get(f"/api/v1/courses/{course_id}")
    assert course_details.status_code == 200
    assert float(course_details.get_json()["course"]["price_thr"]) == 15.0

    card_path = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest-rollout-card",
        "stripe_payment_intent": "pi_rollout_card_001",
    })
    assert card_path.status_code == 503
    assert card_path.get_json()["error"] == "course_stripe_checkout_not_enabled"

    # 3) Enroll THR learner for full certificate + result-state path
    enroll_thr = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "thr",
        "student_thr": "THR_STUDENT_ROLLOUT",
        "auth_secret": "ok",
    })
    assert enroll_thr.status_code == 200

    # 4) Open lesson / course
    open_lesson = _client().get(f"/api/v1/courses/{course_id}")
    assert open_lesson.status_code == 200

    # 5) Submit quiz and verify result state + completion
    student_token = server.create_edu_student_token("THR_STUDENT_ROLLOUT", course_id)
    quiz = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": "THR_STUDENT_ROLLOUT", "answers": {"1": 0}},
        headers={"X-Student-Token": student_token},
    )
    assert quiz.status_code == 200
    quiz_body = quiz.get_json()
    assert quiz_body["passed"] is True
    assert quiz_body["completion_status"] == "completed"
    assert quiz_body["result_state"]["states"]["pass_fail_status"] == "pass"
    assert quiz_body["result_state"]["states"]["certificate_eligibility"] is True

    # Ensure no automatic reward/certificate behavior
    assert quiz_body["reward_credited"] is False
    assert quiz_body["certificate_status"] != "issued"

    # 6) Certificate lifecycle: request -> approve -> issue (manual)
    req = _client().post(f"/api/v1/courses/{course_id}/certificates/THR_STUDENT_ROLLOUT/request_approval", json={
        "actor_thr": "THR_TEACHER_ROLLOUT",
        "auth_secret": "ok",
        "tenant_id": "tenant-rollout",
        "institution_id": "inst-rollout",
    })
    assert req.status_code == 200

    approve = _client().post(f"/api/v1/courses/{course_id}/certificates/THR_STUDENT_ROLLOUT/approve", json={
        "actor_thr": "THR_TEACHER_ROLLOUT",
        "auth_secret": "ok",
        "tenant_id": "tenant-rollout",
        "institution_id": "inst-rollout",
        "approval_reason": "rollout verification pass",
    })
    assert approve.status_code == 200
    assert approve.get_json()["certificate_lifecycle_state"] == "issuable"

    issue = _client().post(f"/api/v1/courses/{course_id}/certificates/THR_STUDENT_ROLLOUT/issue", json={
        "actor_thr": "THR_TEACHER_ROLLOUT",
        "auth_secret": "ok",
        "tenant_id": "tenant-rollout",
        "institution_id": "inst-rollout",
        "issuer_identity": "THR_TEACHER_ROLLOUT",
    })
    assert issue.status_code == 200
    assert issue.get_json()["certificate_lifecycle_state"] == "issued"

    # 7) Verify audit trail and dashboard/report visibility
    history = _client().get(
        f"/api/v1/courses/{course_id}/certificates/THR_STUDENT_ROLLOUT/history",
        query_string={
            "actor_thr": "THR_TEACHER_ROLLOUT",
            "auth_secret": "ok",
            "tenant_id": "tenant-rollout",
            "institution_id": "inst-rollout",
        },
    )
    assert history.status_code == 200
    actions = {r["action"] for r in history.get_json()["history"]}
    assert {"approval_requested", "approved", "issued"}.issubset(actions)

    report = _client().get(
        "/api/v1/tenants/tenant-rollout/reports/operational",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenant-rollout"},
    )
    assert report.status_code == 200

    observability = _client().get(
        "/api/v1/tenants/tenant-rollout/observability",
        query_string={"actor_role": "tenant_admin", "tenant_id": "tenant-rollout"},
    )
    assert observability.status_code == 200


# ── Wallet-less learner quiz submission ─────────────────────────────────


def test_walletless_learner_can_submit_quiz(monkeypatch):
    """Learners with only an earn-account (learner_id, no THR wallet) must be
    able to submit quizzes with a valid X-Student-Token.  Reward eligibility must be False."""
    course_id = "c_walletless_quiz"
    learner = "earn_user_abc"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "students": [learner],
        "reward_policy": "manual_claim",
        "certificate_enabled": False,
    }]
    enrollments = {course_id: {learner: {"reward_eligible": False, "completed": False}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [
            {"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]},
        ],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token(learner, course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": learner, "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["passed"] is True
    assert body["reward_eligibility"] is False


def test_walletless_submit_rejected_without_token(monkeypatch):
    """Wallet-less learner_id submission without X-Student-Token must be rejected."""
    course_id = "c_no_token"
    learner = "earn_user_no_tok"
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={
        "learner_id": learner,
        "answers": {"1": 0},
    })
    assert resp.status_code == 401
    assert "token" in resp.get_json()["message"].lower()


def test_user_a_cannot_submit_quiz_as_user_b(monkeypatch):
    """A signed token for user A must not allow submitting as user B."""
    course_id = "c_cross_user"
    user_a = "learner_alice"
    user_b = "learner_bob"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "students": [user_a, user_b],
        "reward_policy": "manual_claim",
        "certificate_enabled": False,
    }]
    enrollments = {course_id: {
        user_a: {"reward_eligible": False, "completed": False},
        user_b: {"reward_eligible": False, "completed": False},
    }}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token_a = server.create_edu_student_token(user_a, course_id)

    # user A's token + user B's learner_id => identity mismatch
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": user_b, "answers": {"1": 0}},
        headers={"X-Student-Token": token_a},
    )
    assert resp.status_code == 403
    assert "mismatch" in resp.get_json()["message"].lower()

    # user A's token with matching identity => success
    resp_ok = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": user_a, "answers": {"1": 0}},
        headers={"X-Student-Token": token_a},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.get_json()["passed"] is True


def test_expired_student_token_rejected(monkeypatch):
    """An expired student token must be rejected."""
    import time as _time
    learner = "learner_expired"
    course_id = "c_expired"
    sec = "test-secret"
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", sec)
    state = _patch_edu_token_state(monkeypatch)
    import hmac as _hmac, hashlib as _hashlib, uuid as _uuid
    expiry = int(_time.time()) - 10
    nonce = _uuid.uuid4().hex
    payload = f"{learner}:{course_id}:{expiry}:{nonce}"
    sig = _hmac.new(sec.encode(), payload.encode(), _hashlib.sha256).hexdigest()
    expired_token = f"{learner}:{course_id}:{expiry}:{nonce}:{sig}"
    state["nonces"][nonce] = expiry

    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": learner, "answers": {"1": 0}},
        headers={"X-Student-Token": expired_token},
    )
    assert resp.status_code == 401


def test_forged_student_token_rejected(monkeypatch):
    """A token with a tampered signature must be rejected."""
    learner = "learner_forge"
    course_id = "c_forged"
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    _patch_edu_token_state(monkeypatch)
    token = server.create_edu_student_token(learner, course_id)
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")

    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": learner, "answers": {"1": 0}},
        headers={"X-Student-Token": forged},
    )
    assert resp.status_code == 401


def test_quiz_submit_requires_some_identifier(monkeypatch):
    """Quiz submission without a token is rejected before the identifier check."""
    course_id = "c_no_id_quiz"
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={
        "answers": {"1": 0},
    })
    assert resp.status_code == 401
    assert "token" in resp.get_json()["message"].lower()


def test_reward_claim_requires_wallet(monkeypatch):
    """Reward claim must require a THR wallet — wallet-less learners cannot claim."""
    course_id = "c_claim_wallet"
    learner = "earn_user_noreward"
    courses = [{"id": course_id, "teacher": "T1", "reward_l2e": 5.0, "reward_policy": "manual_claim"}]
    enrollments = {course_id: {learner: {
        "reward_eligible": False,
        "completed": True,
        "reward_claimed": False,
    }}}
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)

    resp = _client().post(f"/api/v1/courses/{course_id}/claim_reward", json={"learner_id": learner})
    assert resp.status_code == 403
    assert "not claimable" in resp.get_json()["message"].lower() or "wallet" in resp.get_json()["message"].lower()


# ── Negative security tests ──────────────────────────────────────────────


def test_non_enrolled_learner_rejected(monkeypatch):
    """A valid token for a learner NOT enrolled in the course must be rejected (403)."""
    course_id = "c_not_enrolled"
    outsider = "learner_outsider"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "students": ["enrolled_student"],
        "reward_policy": "manual_claim",
        "certificate_enabled": False,
    }]
    enrollments = {course_id: {"enrolled_student": {"reward_eligible": False, "completed": False}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda *_: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token(outsider, course_id)
    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": outsider, "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp.status_code == 403
    assert "not enrolled" in resp.get_json()["message"].lower()


def test_wallet_identity_without_token_rejected(monkeypatch):
    """Submitting with student_thr (wallet address) but no X-Student-Token must be rejected."""
    course_id = "c_wallet_no_token"
    wallet = "THR_WALLET_FAKE"
    courses = [{
        "id": course_id,
        "teacher": "T1",
        "students": [wallet],
        "reward_policy": "manual_claim",
        "certificate_enabled": False,
    }]
    enrollments = {course_id: {wallet: {"reward_eligible": True, "student_thr": wallet}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda *_: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"student_thr": wallet, "answers": {"1": 0}},
    )
    assert resp.status_code == 401
    assert "token" in resp.get_json()["message"].lower()


def test_token_for_wrong_course_rejected(monkeypatch):
    """A course-scoped token for course A must not work on course B."""
    course_a = "course_alpha"
    course_b = "course_beta"
    student = "learner_scoped"
    courses = [
        {"id": course_a, "teacher": "T1", "students": [student], "reward_policy": "manual_claim", "certificate_enabled": False},
        {"id": course_b, "teacher": "T1", "students": [student], "reward_policy": "manual_claim", "certificate_enabled": False},
    ]
    enrollments = {
        course_a: {student: {"reward_eligible": False, "completed": False}},
        course_b: {student: {"reward_eligible": False, "completed": False}},
    }
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda *_: None)
    _patch_edu_token_state(monkeypatch)

    token_for_a = server.create_edu_student_token(student, course_a)
    resp = _client().post(f"/api/v1/courses/{course_b}/quiz/submit",
        json={"learner_id": student, "answers": {"1": 0}},
        headers={"X-Student-Token": token_for_a},
    )
    assert resp.status_code == 401
    assert "wrong-course" in resp.get_json()["message"].lower() or "invalid" in resp.get_json()["message"].lower()


# ── Token issuance hardening tests ─────────────────────────────────────


def test_token_issuance_without_enrollment_rejected(monkeypatch):
    """Calling the token issuance endpoint for a non-enrolled student must be rejected."""
    course_id = "c_issue_no_enroll"
    courses = [{"id": course_id, "teacher": "T1", "students": ["enrolled_only"]}]
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "ADMIN_SECRET", "admin-test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    _patch_edu_token_state(monkeypatch)

    resp = _client().post(f"/api/v1/courses/{course_id}/token/issue", json={
        "learner_id": "outsider_learner",
    }, headers={"X-Admin-Secret": "admin-test-secret"})
    assert resp.status_code == 403
    assert "not enrolled" in resp.get_json()["message"].lower()


def test_token_issuance_wallet_proof_mismatch_rejected(monkeypatch):
    """wallet_proof.from must match the claimed student identity."""
    import time as _time, uuid as _uuid
    course_id = "c_issue_wallet_mismatch"
    student = "THR_REAL_STUDENT"
    courses = [{"id": course_id, "teacher": "T1", "students": [student]}]
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    _patch_edu_token_state(monkeypatch)
    challenges = _patch_wallet_challenges(monkeypatch)
    nonce = _uuid.uuid4().hex
    challenges[nonce] = {
        "purpose": "token_issuance",
        "wallet_address": student,
        "course_id": course_id,
        "expiry": int(_time.time()) + 300,
        "consumed": False,
    }

    resp = _client().post(f"/api/v1/courses/{course_id}/token/issue", json={
        "student_thr": student,
        "wallet_proof": {"from": "THR_DIFFERENT_WALLET", "challenge_nonce": nonce},
    })
    assert resp.status_code == 403
    assert "does not match" in resp.get_json()["message"].lower()


def test_token_revocation_and_reuse_rejected(monkeypatch):
    """A revoked token must be rejected when used for quiz submission."""
    course_id = "c_revoke_test"
    student = "learner_revoke"
    courses = [{"id": course_id, "teacher": "T1", "students": [student]}]
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0, "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "ADMIN_SECRET", "admin-test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: {course_id: {student: {}}})
    monkeypatch.setattr(server, "save_enrollments", lambda *_: None)
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token(student, course_id)
    nonce = token.split(":")[3]

    revoke_resp = _client().post("/api/v1/edu/token/revoke",
        json={"nonce": nonce},
        headers={"X-Admin-Secret": "admin-test-secret"},
    )
    assert revoke_resp.status_code == 200

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": student, "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp.status_code == 401


def test_teacher_cross_course_token_rejected(monkeypatch):
    """A teacher token for course A must not work on course B."""
    course_a = "teacher_course_a"
    course_b = "teacher_course_b"
    teacher = "T_CROSS"
    courses = [
        {"id": course_a, "teacher": teacher, "students": []},
        {"id": course_b, "teacher": "T_OTHER", "students": []},
    ]
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    _patch_edu_token_state(monkeypatch)

    token_a = server.create_edu_teacher_token(teacher, course_a)
    verified = server.verify_edu_teacher_token(token_a, expected_course_id=course_b)
    assert verified is None


def test_wildcard_student_token_rejected(monkeypatch):
    """Tokens with wildcard '*' course_id must be rejected."""
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    _patch_edu_token_state(monkeypatch)
    token = server.create_edu_student_token("any_student", "*")
    assert token is None


def test_wildcard_teacher_token_rejected(monkeypatch):
    """Teacher tokens with wildcard '*' course_id must be rejected."""
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    _patch_edu_token_state(monkeypatch)
    token = server.create_edu_teacher_token("any_teacher", "*")
    assert token is None


def test_teacher_token_issuance_wrong_owner_rejected(monkeypatch):
    """Teacher token issuance for a course they don't own must be rejected."""
    import time as _time, uuid as _uuid
    course_id = "c_teacher_not_owner"
    courses = [{"id": course_id, "teacher": "T_REAL_OWNER", "students": []}]
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    _patch_edu_token_state(monkeypatch)
    challenges = _patch_wallet_challenges(monkeypatch)
    nonce = _uuid.uuid4().hex
    challenges[nonce] = {
        "purpose": "teacher_token",
        "wallet_address": "T_IMPOSTER",
        "course_id": course_id,
        "expiry": int(_time.time()) + 300,
        "consumed": False,
    }

    resp = _client().post(f"/api/v1/courses/{course_id}/teacher-token/issue", json={
        "teacher_thr": "T_IMPOSTER",
        "wallet_proof": {"from": "T_IMPOSTER", "challenge_nonce": nonce},
    })
    assert resp.status_code in (401, 403, 503)


def test_token_issuance_requires_secret(monkeypatch):
    """Token issuance endpoint must return 503 when EDU_QUIZ_SECRET is not set."""
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "")
    resp = _client().post("/api/v1/courses/any_course/token/issue", json={
        "learner_id": "anyone",
    })
    assert resp.status_code == 503


# ── Durable state / restart / replay hardening tests ──────────────────────


def test_token_nonce_survives_state_reload(monkeypatch):
    """Token nonce persisted durably must survive a simulated state reload."""
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    state = _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token("learner_persist", "c_persist")
    assert token is not None
    nonce = token.split(":")[3]

    # Nonce must be in durable state
    assert nonce in state["nonces"]

    # Simulate process restart: reload state (the mock is backed by the same dict)
    loaded = server._load_edu_token_state()
    assert nonce in loaded["nonces"]

    # Token must still verify
    verified = server.verify_edu_student_token(token, expected_course_id="c_persist")
    assert verified == "learner_persist"


def test_token_consumed_after_quiz_replay_rejected(monkeypatch):
    """After a quiz submission consumes a token, replaying it must be rejected."""
    course_id = "c_replay"
    student = "learner_replay"
    courses = [{"id": course_id, "teacher": "T1", "students": [student],
                "reward_policy": "manual_claim", "certificate_enabled": False}]
    enrollments = {course_id: {student: {"reward_eligible": False}}}
    quiz = {
        "pass_threshold_score": 50,
        "questions": [{"id": 1, "type": "multiple_choice", "correct": 0,
                       "weight": 1, "options": ["a", "b"]}],
    }
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)
    _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token(student, course_id)

    # First submission succeeds
    resp1 = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": student, "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp1.status_code == 200

    # Replay of the same token must be rejected (consumed)
    resp2 = _client().post(f"/api/v1/courses/{course_id}/quiz/submit",
        json={"learner_id": student, "answers": {"1": 0}},
        headers={"X-Student-Token": token},
    )
    assert resp2.status_code == 401


def test_revoked_token_persists_across_reload(monkeypatch):
    """A revoked nonce must remain revoked after state reload."""
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "ADMIN_SECRET", "admin-test-secret")
    state = _patch_edu_token_state(monkeypatch)

    token = server.create_edu_student_token("learner_rev", "c_rev")
    nonce = token.split(":")[3]

    # Revoke via API
    resp = _client().post("/api/v1/edu/token/revoke",
        json={"nonce": nonce},
        headers={"X-Admin-Secret": "admin-test-secret"},
    )
    assert resp.status_code == 200

    # After revocation, nonce must be in revoked list
    loaded = server._load_edu_token_state()
    assert nonce in loaded["revoked"]

    # Token must fail verification (revoked)
    verified = server.verify_edu_student_token(token, expected_course_id="c_rev")
    assert verified is None


def test_empty_admin_secret_fails_closed(monkeypatch):
    """When ADMIN_SECRET is empty, admin bypass in _require_teacher_or_admin must fail."""
    monkeypatch.setattr(server, "ADMIN_SECRET", "")
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")

    class FakeRequest:
        headers = {"X-Admin-Secret": "anything", "X-Teacher-Token": ""}

    course = {"id": "c_admin_bypass", "teacher": "T1"}
    with server.app.test_request_context():
        tid, err = server._require_teacher_or_admin(course, FakeRequest())
        assert err is not None
        assert tid is None


def test_empty_admin_secret_revoke_fails(monkeypatch):
    """Revoke endpoint must return 503 when ADMIN_SECRET is empty (fail-closed)."""
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "ADMIN_SECRET", "")
    _patch_edu_token_state(monkeypatch)

    resp = _client().post("/api/v1/edu/token/revoke",
        json={"nonce": "any_nonce"},
        headers={"X-Admin-Secret": "anything"},
    )
    assert resp.status_code == 503


def test_wallet_challenge_consumed_after_use(monkeypatch):
    """A wallet challenge must be marked consumed after token issuance and rejected on reuse."""
    import time as _time, uuid as _uuid
    course_id = "c_challenge_reuse"
    wallet = "THR_CHALLENGE_STUDENT"
    courses = [{"id": course_id, "teacher": "T1", "students": [wallet]}]
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    _patch_edu_token_state(monkeypatch)
    challenges = _patch_wallet_challenges(monkeypatch)

    # Create a valid challenge
    nonce = _uuid.uuid4().hex
    challenges[nonce] = {
        "purpose": "token_issuance",
        "wallet_address": wallet,
        "course_id": course_id,
        "expiry": int(_time.time()) + 300,
        "consumed": False,
    }

    # Mock wallet verification to always pass
    import types
    fake_wallet = types.ModuleType("wallet_v1_production_final")
    fake_wallet.verify_required_fields = lambda p: (True, None)
    fake_wallet.verify_no_forbidden_fields = lambda p: (True, None)
    fake_wallet.verify_ecdsa_signature = lambda p: (True, None)
    fake_wallet.verify_publickey_matches_address = lambda p: (True, None)
    fake_wallet.verify_timestamp = lambda t: (True, None)
    import sys as _sys
    _sys.modules["wallet_v1_production_final"] = fake_wallet

    try:
        resp1 = _client().post(f"/api/v1/courses/{course_id}/token/issue", json={
            "student_thr": wallet,
            "wallet_proof": {"from": wallet, "challenge_nonce": nonce},
        })
        assert resp1.status_code == 200

        # Challenge must be consumed
        loaded = server._load_wallet_challenges()
        assert loaded[nonce]["consumed"] is True

        # Reusing the same challenge must fail
        resp2 = _client().post(f"/api/v1/courses/{course_id}/token/issue", json={
            "student_thr": wallet,
            "wallet_proof": {"from": wallet, "challenge_nonce": nonce},
        })
        assert resp2.status_code == 401
        assert "already used" in resp2.get_json()["message"].lower()
    finally:
        _sys.modules.pop("wallet_v1_production_final", None)


def test_auth_secret_body_param_removed(monkeypatch):
    """Sending auth_secret in the request body must NOT issue a token for email learners."""
    course_id = "c_no_auth_secret"
    learner = "email_learner_abc"
    courses = [{"id": course_id, "teacher": "T1", "students": [learner]}]
    monkeypatch.setattr(server, "EDU_QUIZ_SECRET", "test-secret")
    monkeypatch.setattr(server, "ADMIN_SECRET", "admin-test-secret")
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    _patch_edu_token_state(monkeypatch)

    # Sending auth_secret in body (old method) without X-Admin-Secret header
    resp = _client().post(f"/api/v1/courses/{course_id}/token/issue", json={
        "learner_id": learner,
        "auth_secret": "any-value",
    })
    assert resp.status_code == 401
    assert "x-admin-secret" in resp.get_json()["message"].lower()

    # Proper method: X-Admin-Secret header
    resp_ok = _client().post(f"/api/v1/courses/{course_id}/token/issue", json={
        "learner_id": learner,
    }, headers={"X-Admin-Secret": "admin-test-secret"})
    assert resp_ok.status_code == 200
    assert "token" in resp_ok.get_json()
