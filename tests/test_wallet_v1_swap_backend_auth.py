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


def signed_swap(action="swap", from_addr=TRADER, with_signature=True, amount="10", token_in="THR", token_out="WBTC"):
    tx = {
        "type": action,
        "action": action,
        "from": from_addr,
        "token_in": token_in,
        "token_out": token_out,
        "amount_in": str(amount),
        "nonce": "nonce-1",
        "timestamp": "1",
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
    monkeypatch.setattr(server, "verify_signed_swap_transaction", lambda tx: (True, "", ""))


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


def _signed_real_swap(amount="10", token_in="THR", token_out="WBTC"):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256K1())
    public_key = key.public_key()
    public_hex = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.CompressedPoint,
    ).hex()
    from_addr = wallet_v1_prod.derive_thronos_address(public_hex)
    tx = signed_swap("swap", from_addr=from_addr, with_signature=False, amount=amount, token_in=token_in, token_out=token_out)
    tx["publicKey"] = public_hex
    signature = key.sign(server.canonical_swap_signing_json(tx).encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    tx["signature"] = signature.hex()
    return from_addr, tx


def test_backend_verifies_fixture_signed_with_same_canonical_payload():
    from_addr, tx = _signed_real_swap(amount="10", token_in="THR", token_out="WBTC")
    payload = {
        "trader_thr": from_addr,
        "active_wallet_address": from_addr,
        "credential_lookup_address": from_addr,
        "public_key": tx["publicKey"],
        "signature": tx["signature"],
        "signed_tx": tx,
        "token_in": "THR",
        "token_out": "WBTC",
        "amount_in": "10",
        "action": "swap",
    }
    ok, err, wallet = server.verify_swap_wallet_v1_or_legacy(payload)
    assert ok is True
    assert err == {}
    assert wallet == from_addr


def test_backend_rejects_changed_amount_after_signing():
    from_addr, tx = _signed_real_swap(amount="10")
    payload = {"trader_thr": from_addr, "signed_tx": tx, "token_in": "THR", "token_out": "WBTC", "amount_in": "11", "action": "swap"}
    ok, err, wallet = server.verify_swap_wallet_v1_or_legacy(payload)
    assert ok is False
    assert err["error"] == "signed_payload_mismatch"
    assert err["field"] == "amount_in"


def test_backend_rejects_changed_token_after_signing():
    from_addr, tx = _signed_real_swap(token_out="WBTC")
    payload = {"trader_thr": from_addr, "signed_tx": tx, "token_in": "THR", "token_out": "7CEB", "amount_in": "10", "action": "swap"}
    ok, err, wallet = server.verify_swap_wallet_v1_or_legacy(payload)
    assert ok is False
    assert err["error"] == "signed_payload_mismatch"
    assert err["field"] == "token_out"


def test_backend_rejects_changed_from_after_signing():
    from_addr, tx = _signed_real_swap()
    payload = {"trader_thr": OTHER, "signed_tx": tx, "token_in": "THR", "token_out": "WBTC", "amount_in": "10", "action": "swap"}
    ok, err, wallet = server.verify_swap_wallet_v1_or_legacy(payload)
    assert ok is False
    assert err["error"] == "signed_from_mismatch"


def test_signature_format_detection_is_explicit():
    assert server._swap_signature_format("00" * 64) == "compact"
    assert server._swap_signature_format("3044022000") == "der"
    assert server._swap_signature_format("not-hex") == "unknown"



def test_swap_math_unchanged():
    assert server.compute_swap_out(10, 1000, 1000, 30) == pytest.approx((9.871580343970614, 0.03, 1.9674832023733324))


def test_wallet_v1_swap_never_returns_legacy_option_not_supported(accept_signature, swap_state):
    res = post_swap(v1_payload(option="stake", signed_action="swap"))
    body = res.get_json()
    assert res.status_code == 400
    assert body["error"] == "unsupported_swap_action"
    assert body["expected"] == "swap"
    assert body["got"] == "stake"
    assert "option not supported" not in str(body).lower()
    assert not swap_state["tx"]


def test_server_has_no_generic_option_not_supported_swap_return():
    server_source = Path(server.__file__).read_text()
    swap_start = server_source.index('@app.route("/api/swap/execute"')
    swap_end = server_source.index('# ─── Token Balances API', swap_start)
    assert "option not supported" not in server_source[swap_start:swap_end].lower()


def test_swap_execute_returns_structured_errors_not_generic_500(accept_signature, swap_state, monkeypatch):
    """Verify swap execute endpoint returns structured error codes, not generic server_error."""
    # Simulate an exception in the wallet verification path
    def fake_verify_fail(*args, **kwargs):
        raise ValueError("Test verification error")

    monkeypatch.setattr(server, "verify_swap_wallet_v1_or_legacy", fake_verify_fail)

    res = post_swap(v1_payload())
    body = res.get_json()

    # Should return structured error, not generic server_error
    assert "error" in body
    assert body["error"] in ("swap_execution_failed", "invalid_swap_amount", "pool_not_found")
    assert "message" in body
    # Should include exception type for debugging
    assert "exception_type" in body
    # Should not have been mutated due to try-catch catching the error
    assert not swap_state["tx"]
