"""A signed intent cannot be replayed at a different wallet route."""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "wallet_v1_transfer": "internal_transfer",
    "wallet_v1_withdraw": "crosschain_withdraw",
    "wallet_v1_swap": "swap",
    "wallet_v1_add_liquidity": "pool_deposit_intent",
    "wallet_v1_create_token": "token_create",
    "wallet_v1_nfts_mint": "nft_mint",
    "wallet_v1_nfts_buy": "nft_buy",
}


def _isolated_handler(name, action):
    tree = ast.parse((ROOT / "server_ext.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list = []
    calls = []

    def verifier(*args):
        calls.append(args)
        return False, "invalid_signature", "fixture stops execution"

    scope = {
        "_request": SimpleNamespace(get_json=lambda: {
            "intent": {"action": action}, "signature": "sig", "public_key": "pub",
        }),
        "_jsonify": lambda **kwargs: kwargs,
        "_verify_wallet_action_intent": verifier,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(ROOT / "server_ext.py"), "exec"), scope)
    return scope[name], calls


@pytest.mark.parametrize("handler,expected", EXPECTED.items())
def test_wrong_action_rejected_before_nonce_check(handler, expected, monkeypatch):
    monkeypatch.setitem(sys.modules, "server", SimpleNamespace())
    fn, calls = _isolated_handler(handler, "earn_thr_stake")
    body, status = fn()
    assert status == 400
    assert body["error"] == "wrong_wallet_action"
    assert calls == []


@pytest.mark.parametrize("handler,expected", EXPECTED.items())
def test_expected_action_reaches_signature_check(handler, expected, monkeypatch):
    monkeypatch.setitem(sys.modules, "server", SimpleNamespace())
    fn, calls = _isolated_handler(handler, expected)
    body, status = fn()
    assert status == 400
    assert body["error"] == "invalid_signature"
    assert len(calls) == 1
