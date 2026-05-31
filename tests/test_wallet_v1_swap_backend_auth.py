"""Wallet V1 signed swap action normalization and auth guards."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
import wallet_v1_production_final as wallet_v1_prod


TRADER = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"
OTHER = "THRE85A3E0A09A57212CDB222A9BF5B6E07A9B820E4"


def signed_swap(action="swap", from_addr=TRADER, with_signature=True):
    tx = {
        "from": from_addr,
        "to": "WBTC",
        "amount": 10,
        "token": "THR",
        "nonce": "nonce-1",
        "timestamp": 1,
        "action": action,
        "type": action,
        "publicKey": "02" + "1" * 64,
    }
    if with_signature:
        tx["signature"] = "00"
    return tx


def v1_payload(action=None, option=None, signed_action="swap", trader=TRADER, with_signature=True):
    payload = {
        "trader_thr": trader,
        "active_wallet_address": trader,
        "credential_lookup_address": trader,
        "public_key": "02" + "1" * 64,
        "signed_tx": signed_swap(signed_action, from_addr=trader, with_signature=with_signature),
        "token_in": "THR",
        "token_out": "WBTC",
        "amount_in": 10,
        "min_amount_out": 1,
    }
    if action is not None:
        payload["action"] = action
    if option is not None:
        payload["option"] = option
    if with_signature:
        payload["signature"] = "00"
    return payload


@pytest.fixture
def accept_signature(monkeypatch):
    monkeypatch.setattr(wallet_v1_prod, "verify_signed_transaction_core", lambda tx: (True, ""))


@pytest.fixture
def swap_state(monkeypatch):
    saved = {"json": [], "token_balances": [], "pools": [], "tx": []}
    pool = {
        "id": "pool-thr-wbtc",
        "token_a": "THR",
        "token_b": "WBTC",
        "reserves_a": 1000.0,
        "reserves_b": 1000.0,
        "fee_bps": 30,
    }

    def fake_quote(token_in, token_out, amount_in):
        return {
            "amount_out": 9.0,
            "fee": 0.03,
            "fee_bps": 30,
            "price_impact": 1.0,
            "route": [{"pool_id": "pool-thr-wbtc", "in_token": "THR", "out_token": "WBTC"}],
        }, None

    def fake_load_json(path, default=None):
        if path == server.LEDGER_FILE:
            return {TRADER: 100.0}
        if path == server.WBTC_LEDGER_FILE:
            return {}
        if path == server.CHAIN_FILE:
            return []
        return copy.deepcopy(default) if default is not None else {}

    monkeypatch.setattr(server, "quote_swap_route", fake_quote)
    monkeypatch.setattr(server, "load_json", fake_load_json)
    monkeypatch.setattr(server, "load_token_balances", lambda: {"WBTC": {TRADER: 0.0}})
    monkeypatch.setattr(server, "load_pools", lambda: [copy.deepcopy(pool)])
    monkeypatch.setattr(server, "save_json", lambda path, value: saved["json"].append((path, value)))
    monkeypatch.setattr(server, "save_token_balances", lambda value: saved["token_balances"].append(value))
    monkeypatch.setattr(server, "save_pools", lambda value: saved["pools"].append(value))
    monkeypatch.setattr(server, "update_last_block", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "persist_normalized_tx", lambda tx: saved["tx"].append(tx))
    return saved


def post_swap(payload):
    return server.app.test_client().post("/api/swap/execute", json=payload)


def test_v1_signed_swap_accepted_with_action_swap(accept_signature, swap_state):
    res = post_swap(v1_payload(action="swap"))
    body = res.get_json()
    assert res.status_code == 200
    assert body["status"] == "success"
    assert swap_state["tx"]


def test_v1_signed_swap_accepted_with_option_swap(accept_signature, swap_state):
    res = post_swap(v1_payload(option="swap"))
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"


def test_execute_swap_alias_normalized(accept_signature, swap_state):
    res = post_swap(v1_payload(action="execute_swap", signed_action="execute_swap"))
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"


def test_unsupported_option_returns_clear_error(accept_signature, swap_state):
    res = post_swap(v1_payload(option="stake", signed_action="swap"))
    body = res.get_json()
    assert res.status_code == 400
    assert body == {
        "ok": False,
        "status": "error",
        "error": "unsupported_swap_action",
        "message": "unsupported_swap_action",
        "expected": "swap",
        "got": "stake",
    }
    assert not swap_state["tx"]


def test_missing_signature_rejected(swap_state):
    res = post_swap(v1_payload(action="swap", with_signature=False))
    body = res.get_json()
    assert res.status_code == 400
    assert body["error"] == "missing_signature"
    assert not swap_state["tx"]


def test_wrong_signed_action_rejected_before_mutation(accept_signature, swap_state):
    res = post_swap(v1_payload(action="swap", signed_action="mint"))
    body = res.get_json()
    assert res.status_code == 400
    assert body["error"] == "unsupported_swap_action"
    assert body["expected"] == "swap"
    assert body["got"] == "mint"
    assert not swap_state["tx"]


def test_provider_from_mismatch_rejected(accept_signature, swap_state):
    payload = v1_payload(action="swap", trader=TRADER)
    payload["signed_tx"]["from"] = OTHER
    res = post_swap(payload)
    body = res.get_json()
    assert res.status_code == 403
    assert body["error"] == "wallet_mismatch"
    assert not swap_state["tx"]


def test_legacy_path_still_uses_validate_effective_auth(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "validate_effective_auth", lambda addr, secret, passphrase: calls.append((addr, secret, passphrase)) or (True, {}, None))
    ok, err, wallet = server.verify_swap_wallet_v1_or_legacy({"trader_thr": TRADER, "auth_secret": "legacy-secret"})
    assert ok is True
    assert err == {}
    assert wallet == TRADER
    assert calls == [(TRADER, "legacy-secret", "")]


def test_legacy_path_allows_credential_lookup_address_without_v1_signature(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "validate_effective_auth", lambda addr, secret, passphrase: calls.append((addr, secret, passphrase)) or (True, {}, None))
    payload = {"trader_thr": TRADER, "credential_lookup_address": OTHER, "auth_secret": "legacy-secret"}
    ok, err, wallet = server.verify_swap_wallet_v1_or_legacy(payload)
    assert ok is True
    assert err == {}
    assert wallet == TRADER
    assert calls == [(TRADER, "legacy-secret", "")]


def test_swap_math_unchanged():
    assert server.compute_swap_out(10, 1000, 1000, 30) == pytest.approx((9.871580343970614, 0.03, 1.9674832023733324))
