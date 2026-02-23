#!/usr/bin/env python3
"""
Thronos V3.6 — Functional Smoke Test Suite

Lightweight HTTP-level checks for the most critical public endpoints.

Run locally against a running node:
  THRONOS_URL=http://localhost:5000 python tests/smoke_test.py

Run against staging/production:
  THRONOS_URL=https://api.thronoschain.org python tests/smoke_test.py

The goal is to catch obvious regressions (500s, bad JSON, empty datasets)
without doing heavy load or deep correctness proofs.
"""

import json
import os
import tempfile
import uuid

import requests

BASE_URL = os.environ.get("THRONOS_URL", "https://api.thronoschain.org")
TIMEOUT = 15


class SmokeResult:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.errors: list[tuple[str, str]] = []

    def ok(self, name: str) -> None:
        self.passed += 1
        print(f"✅ {name}")

    def fail(self, name: str, reason: str = "") -> None:
        self.failed += 1
        self.errors.append((name, reason))
        print(f"❌ {name} — {reason}")

    def summary(self) -> bool:
        total = self.passed + self.failed
        print("\n" + "=" * 60)
        print(f"SMOKE RESULTS: {self.passed}/{total} passed")
        if self.errors:
            print("FAILURES:")
            for name, reason in self.errors:
                print(f" • {name}: {reason}")
        print("=" * 60)
        return self.failed == 0


def _get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{BASE_URL}{path}", timeout=TIMEOUT, **kwargs)


def _post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{BASE_URL}{path}", timeout=TIMEOUT, **kwargs)


# ---------------------------------------------------------------------------
# FIX #1: Upload endpoint (secure_filename / degraded mode)
# ---------------------------------------------------------------------------


def test_upload_txt_file(results: SmokeResult) -> None:
    name = "Upload .txt returns 2xx"
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Smoke test content for Thronos upload")
            f.flush()
            tmp_path = f.name
        with open(tmp_path, "rb") as fh:
            r = _post("/upload", files={"file": ("smoke_test.txt", fh, "text/plain")})
        os.unlink(tmp_path)
        if 200 <= r.status_code < 300:
            results.ok(name)
        else:
            results.fail(name, f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        results.fail(name, str(exc))


def test_upload_empty_file_degraded(results: SmokeResult) -> None:
    name = "Empty upload handled without 5xx"
    try:
        from io import BytesIO

        r = _post("/upload", files={"file": ("empty.txt", BytesIO(b""), "text/plain")})
        if 200 <= r.status_code < 300:
            results.ok(name)
        else:
            results.fail(name, f"HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        results.fail(name, str(exc))


# ---------------------------------------------------------------------------
# FIX #2: Token logos served from /media/token_logos
# ---------------------------------------------------------------------------


def test_token_logo_media_route(results: SmokeResult) -> None:
    name = "Token logo /media/token_logos route exists"
    try:
        r = _get("/media/token_logos/nonexistent_smoke_test.png")
        if r.status_code in (200, 404):
            results.ok(name)
        else:
            results.fail(name, f"HTTP {r.status_code} (expected 200 or 404)")
    except Exception as exc:  # noqa: BLE001
        results.fail(name, str(exc))


# ---------------------------------------------------------------------------
# FIX #7: AI model catalog endpoint
# ---------------------------------------------------------------------------


def _load_models(results: SmokeResult, name: str) -> list[dict] | None:
    try:
        r = _get("/api/ai/models")
    except Exception as exc:  # noqa: BLE001
        results.fail(name, str(exc))
        return None

    if r.status_code != 200:
        results.fail(name, f"HTTP {r.status_code}")
        return None

    try:
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        results.fail(name, f"Invalid JSON: {exc}")
        return None

    models = data if isinstance(data, list) else data.get("models") or data.get("data")
    if not isinstance(models, list):
        results.fail(name, f"Unexpected payload type: {type(models)}")
        return None
    if not models:
        results.fail(name, "Empty model list")
        return None
    return models


def test_ai_models_basic(results: SmokeResult) -> None:
    name = "AI models endpoint returns non-empty list"
    models = _load_models(results, name)
    if models is None:
        return
    results.ok(name)


def test_ai_models_no_duplicates(results: SmokeResult) -> None:
    name = "AI models have no duplicate (provider, model_id)"
    models = _load_models(results, name)
    if models is None:
        return
    seen: set[tuple[str, str]] = set()
    dupes: list[tuple[str, str]] = []
    for m in models:
        key = (str(m.get("provider", "")), str(m.get("model_id", m.get("id", ""))))
        if key in seen:
            dupes.append(key)
        else:
            seen.add(key)
    if dupes:
        results.fail(name, f"Duplicates found: {dupes}")
    else:
        results.ok(name)


def test_ai_models_have_display_name(results: SmokeResult) -> None:
    name = "AI models expose display_name or label"
    models = _load_models(results, name)
    if models is None:
        return
    missing: list[str] = []
    for m in models:
        if not m.get("display_name") and not m.get("label"):
            missing.append(str(m.get("model_id", m.get("id", "unknown"))))
    if missing:
        results.fail(name, f"Missing display_name/label for: {missing}")
    else:
        results.ok(name)


# ---------------------------------------------------------------------------
# Chat endpoint — credits behaviour
# ---------------------------------------------------------------------------


def test_chat_no_credits_warning(results: SmokeResult) -> None:
    name = "Chat with fake wallet handled gracefully"
    payload = {
        "message": "smoke test",
        "wallet": "THR_no_credits_" + uuid.uuid4().hex[:8],
        "session_id": "smoke_" + uuid.uuid4().hex[:6],
    }
    try:
        r = _post("/api/chat", json=payload)
        if r.status_code != 200:
            results.fail(name, f"HTTP {r.status_code}")
            return
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        results.fail(name, str(exc))
        return

    status = data.get("status", "")
    credits = data.get("credits")
    if status == "no_credits" or credits == 0 or "response" in data:
        # Accept both strict no_credits and permissive modes.
        results.ok(name)
    else:
        results.fail(name, f"Unexpected response: {json.dumps(data)[:200]}")


# ---------------------------------------------------------------------------
# Learn‑to‑Earn: course + quiz persistence (light write‑path check)
# NOTE: Recommended to run this against staging or a dedicated test env.
# ---------------------------------------------------------------------------


def test_quiz_persistence_multiple_questions(results: SmokeResult) -> None:
    name = "L2E quiz with 3 questions persists all questions"
    try:
        course_r = _post("/api/v1/courses", json={
            "title": f"Smoke Test Course {uuid.uuid4().hex[:6]}",
            "description": "Automated smoke test",
            "creator_wallet": "THR_smoke_" + uuid.uuid4().hex[:8],
            "price": 0,
        })
        if course_r.status_code not in (200, 201):
            results.fail(name, f"Cannot create course: HTTP {course_r.status_code}")
            return
        course_data = course_r.json()
        course_id = (
            course_data.get("id")
            or course_data.get("course_id")
            or course_data.get("data", {}).get("id")
        )
        if not course_id:
            results.fail(name, f"No course_id in response: {json.dumps(course_data)[:200]}")
            return

        questions = [
            {
                "question": f"Smoke Q{i}?",
                "options": ["A", "B", "C", "D"],
                "correct": i % 4,
            }
            for i in range(3)
        ]
        quiz_r = _post(f"/api/v1/courses/{course_id}/quiz", json={
            "questions": questions,
            "passing_score": 66,
        })
        if quiz_r.status_code not in (200, 201):
            results.fail(name, f"Cannot create quiz: HTTP {quiz_r.status_code} {quiz_r.text[:200]}")
            return

        fetch_r = _get(f"/api/v1/courses/{course_id}/quiz")
        if fetch_r.status_code != 200:
            results.fail(name, f"Cannot fetch quiz: HTTP {fetch_r.status_code}")
            return
        quiz_data = fetch_r.json()
        stored_questions = quiz_data.get("questions", [])
        if len(stored_questions) == 3:
            results.ok(name)
        else:
            results.fail(name, f"Expected 3 questions, got {len(stored_questions)}")
    except Exception as exc:  # noqa: BLE001
        results.fail(name, str(exc))


TEST_FUNCTIONS = [
    test_upload_txt_file,
    test_upload_empty_file_degraded,
    test_token_logo_media_route,
    test_ai_models_basic,
    test_ai_models_no_duplicates,
    test_ai_models_have_display_name,
    test_chat_no_credits_warning,
    test_quiz_persistence_multiple_questions,
]


def main() -> None:
    print(f"Running Thronos functional smoke tests against {BASE_URL}\n")
    results = SmokeResult()
    for fn in TEST_FUNCTIONS:
        fn(results)
    ok = results.summary()
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
