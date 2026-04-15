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


def test_enrollment_hydration_failure_is_non_fatal(monkeypatch):
    course_id = "c2b"
    courses = [{"id": course_id, "teacher": "teacher1", "price_thr": 10, "students": []}]
    enrollments = {}

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "_refresh_enrollment_reward_flags", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    resp = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_hydration_fail",
        "stripe_payment_intent": "pi_hydrate1234",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert enrollments[course_id]["guest_hydration_fail"]["reward_state"] == "not_eligible"
    assert enrollments[course_id]["guest_hydration_fail"]["reward_claimability"] == "not_claimable"


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


def test_stripe_second_click_returns_clean_409(monkeypatch):
    course_id = "c_dup_retry"
    courses = [{"id": course_id, "teacher": "teacher1", "price_thr": 5, "students": []}]
    enrollments = {}

    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda _: None)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))

    first = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_retry",
        "stripe_payment_intent": "pi_retry12345",
    })
    assert first.status_code == 200

    second = _client().post(f"/api/v1/courses/{course_id}/enroll", json={
        "payment_method": "stripe",
        "learner_id": "guest_retry",
        "stripe_payment_intent": "pi_retry12345",
    })
    assert second.status_code == 409
    assert second.get_json()["message"] == "Duplicate enrollment"


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
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={"student_thr": "S", "answers": {"1": 0}})
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
    monkeypatch.setattr(server, "load_courses", lambda: courses)
    monkeypatch.setattr(server, "save_courses", lambda *_: None)
    monkeypatch.setattr(server, "get_course_quiz", lambda *_: quiz)
    monkeypatch.setattr(server, "load_enrollments", lambda: enrollments)
    monkeypatch.setattr(server, "save_enrollments", lambda e: enrollments.update(copy.deepcopy(e)))
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: None)

    resp = _client().post(f"/api/v1/courses/{course_id}/quiz/submit", json={"student_thr": "S", "answers": {"1": 0, "2": 0}})
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
