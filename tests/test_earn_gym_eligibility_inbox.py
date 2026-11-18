import hashlib
import hmac
import io
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

import pytest

from services.earn_gym_eligibility_inbox import (
    GymEligibilityExportClient,
    GymEligibilityInbox,
    GymExportError,
    GymInboxError,
    reconcile_gym_eligibility,
)

SECRET = "gym-export-secret-that-is-at-least-32-bytes"
USER = "earn_user_1"


def signed_receipt(**changes):
    payload = {
        "event_id": "gym_" + "a" * 32,
        "earn_user_ref": USER,
        "tenant_id": "gym_tenant_1",
        "challenge_id": "challenge_1",
        "reward_t2e": "5",
        "completed_at": 1_800_000_000,
        "status": "eligible",
        "source": "gym_verified_challenge",
    }
    payload.update(changes)
    signature = hmac.new(
        SECRET.encode(),
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    return {**payload, "signature": signature}


@pytest.fixture
def inbox(tmp_path):
    return GymEligibilityInbox(tmp_path / "gym-inbox.db", SECRET)


def test_verified_receipt_is_stored_as_eligibility_only(inbox):
    result = inbox.ingest(signed_receipt(), expected_earn_user_ref=USER)
    assert result["state"] == "verified_eligibility_only"
    assert result["credit_authorized"] is False
    assert result["payout_enabled"] is False
    assert "thc_amount" not in result
    assert "signature" not in result


def test_same_receipt_is_idempotent_and_persists_across_restart(tmp_path):
    path = tmp_path / "gym-inbox.db"
    first = GymEligibilityInbox(path, SECRET)
    assert first.ingest(signed_receipt(), expected_earn_user_ref=USER)["idempotent"] is False
    reopened = GymEligibilityInbox(path, SECRET)
    assert reopened.ingest(signed_receipt(), expected_earn_user_ref=USER)["idempotent"] is True
    assert len(reopened.for_user(USER)) == 1


def test_tampering_and_wrong_account_fail_without_storage(inbox):
    tampered = signed_receipt()
    tampered["reward_t2e"] = "999"
    with pytest.raises(GymInboxError, match="invalid_gym_signature"):
        inbox.ingest(tampered, expected_earn_user_ref=USER)
    with pytest.raises(GymInboxError, match="wrong_earn_account"):
        inbox.ingest(signed_receipt(), expected_earn_user_ref="earn_other")
    assert inbox.for_user(USER) == []


def test_challenge_scope_cannot_create_duplicate_eligibility(inbox):
    inbox.ingest(signed_receipt(), expected_earn_user_ref=USER)
    duplicate_scope = signed_receipt(event_id="gym_" + "b" * 32)
    with pytest.raises(GymInboxError, match="gym_eligibility_scope_conflict"):
        inbox.ingest(duplicate_scope, expected_earn_user_ref=USER)
    assert len(inbox.for_user(USER)) == 1


def test_tenant_and_account_queries_are_isolated(inbox):
    inbox.ingest(signed_receipt(), expected_earn_user_ref=USER)
    other = signed_receipt(
        event_id="gym_" + "c" * 32,
        earn_user_ref="earn_user_2",
        tenant_id="gym_tenant_2",
        challenge_id="challenge_2",
    )
    inbox.ingest(other, expected_earn_user_ref="earn_user_2")
    assert [row["tenant_id"] for row in inbox.for_user(USER)] == ["gym_tenant_1"]
    assert [row["tenant_id"] for row in inbox.for_user("earn_user_2")] == ["gym_tenant_2"]


def test_concurrent_duplicate_delivery_stores_once(inbox):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: inbox.ingest(signed_receipt(), expected_earn_user_ref=USER),
            range(8),
        ))
    assert sum(not result["idempotent"] for result in results) == 1
    assert len(inbox.for_user(USER)) == 1


class Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, limit=-1):
        return json.dumps(self._payload).encode()[:limit]


def test_export_client_uses_server_only_authentication():
    captured = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["secret"] = request.get_header("X-t2e-earn-export-key")
        captured["timeout"] = timeout
        return Response({
            "ok": True,
            "reward_currency": "T2E_ELIGIBILITY_ONLY",
            "receipts": [signed_receipt()],
        })

    client = GymEligibilityExportClient(
        "https://gym.example", SECRET, opener=opener,
    )
    assert client.fetch_eligibility(USER) == [signed_receipt()]
    assert captured == {
        "url": f"https://gym.example/api/internal/earn/eligibility/{USER}",
        "secret": SECRET,
        "timeout": 5.0,
    }


@pytest.mark.parametrize("url,secret,error", [
    ("http://gym.example", SECRET, "gym_export_https_required"),
    ("https://gym.example", "short", "gym_export_not_configured"),
])
def test_export_client_fails_closed_on_unsafe_configuration(url, secret, error):
    with pytest.raises(GymExportError, match=error):
        GymEligibilityExportClient(url, secret)


def test_export_client_fails_closed_on_http_or_contract_error():
    def unavailable(request, *, timeout):
        raise HTTPError(request.full_url, 403, "denied", {}, io.BytesIO())

    client = GymEligibilityExportClient(
        "https://gym.example", SECRET, opener=unavailable,
    )
    with pytest.raises(GymExportError, match="gym_export_unavailable"):
        client.fetch_eligibility(USER)

    invalid = GymEligibilityExportClient(
        "https://gym.example", SECRET,
        opener=lambda request, timeout: Response({
            "ok": True, "reward_currency": "THC", "receipts": [],
        }),
    )
    with pytest.raises(GymExportError, match="invalid_gym_export_response"):
        invalid.fetch_eligibility(USER)


def test_export_client_encodes_identity_and_limits_response_size():
    captured = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        return Response({
            "ok": True, "reward_currency": "T2E_ELIGIBILITY_ONLY", "receipts": [],
        })

    client = GymEligibilityExportClient("https://gym.example", SECRET, opener=opener)
    client.fetch_eligibility("earn/user")
    assert captured["url"].endswith("/earn%2Fuser")

    class Oversized(Response):
        def read(self, limit=-1):
            return b"x" * limit

    oversized = GymEligibilityExportClient(
        "https://gym.example", SECRET,
        opener=lambda request, timeout: Oversized({}),
    )
    with pytest.raises(GymExportError, match="gym_export_response_too_large"):
        oversized.fetch_eligibility(USER)


def test_reconciliation_is_read_only_and_retry_safe(inbox):
    class Source:
        def fetch_eligibility(self, earn_user_ref):
            assert earn_user_ref == USER
            return [signed_receipt()]

    first = reconcile_gym_eligibility(inbox, Source(), earn_user_ref=USER)
    second = reconcile_gym_eligibility(inbox, Source(), earn_user_ref=USER)
    assert first.public_dict() == {
        "earn_user_ref": USER,
        "received": 1,
        "stored": 1,
        "idempotent": 0,
        "credit_authorized": False,
        "payout_enabled": False,
    }
    assert second.stored == 0
    assert second.idempotent == 1


def test_module_has_no_earn_ledger_or_payout_dependency():
    import inspect

    import services.earn_gym_eligibility_inbox as module

    source = inspect.getsource(module)
    assert "record_thc_credit" not in source
    assert "earn_account" not in source
    assert "broadcast" not in source
