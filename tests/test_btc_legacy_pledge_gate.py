"""Fail-closed tests for the legacy BTC pledge direct-credit endpoint."""

import os
import tempfile

os.environ.setdefault("SCHEDULER_ENABLED", "0")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="btc_legacy_gate_"))
os.environ.setdefault("EDU_DB_PATH", os.path.join(os.environ["DATA_DIR"], "l2e_edu.db"))

import server


def test_authenticated_legacy_pledge_cannot_credit_when_gate_is_off(monkeypatch):
    monkeypatch.setattr(server, "BTC_LEGACY_PLEDGE_CREDIT_ENABLED", False)
    ledger_writes = []
    monkeypatch.setattr(server, "load_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(server, "save_json", lambda *args, **kwargs: ledger_writes.append(args))

    response = server.app.test_client().post(
        "/api/btc/pledge",
        json={
            "secret": server.ADMIN_SECRET,
            "thr_address": "THR_TEST_DESTINATION",
            "btc_address": "bc1qtestsource",
            "btc_amount": 0.001,
            "thr_amount": 1.0,
            "btc_txid": "a" * 64,
        },
    )

    assert response.status_code == 503
    assert response.get_json() == {
        "ok": False,
        "error": "Legacy BTC pledge credit disabled",
    }
    assert ledger_writes == []


def test_legacy_gate_does_not_disclose_state_to_unauthenticated_callers(monkeypatch):
    monkeypatch.setattr(server, "BTC_LEGACY_PLEDGE_CREDIT_ENABLED", False)

    response = server.app.test_client().post(
        "/api/btc/pledge",
        json={"secret": "wrong"},
    )

    assert response.status_code == 403
    assert response.get_json() == {"ok": False, "error": "Unauthorized"}
