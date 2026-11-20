"""Runtime authorization tests for Wallet V1 full-payload V2 routes.

All balances and signatures are synthetic. No broadcaster or external chain is
reachable from this suite.
"""

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

import server
from wallet_v1_signed_request_verifier import (
    FULL_PAYLOAD_CHAIN_ID,
    FULL_PAYLOAD_DOMAIN,
    FULL_PAYLOAD_PROTOCOL_VERSION,
    FULL_PAYLOAD_SIGNATURE_FORMAT,
    canonical_signed_request_bytes,
    derive_thr_address_from_public_key_hex,
)


def _key_material(private_value):
    private_key = ec.derive_private_key(private_value, ec.SECP256K1())
    numbers = private_key.public_key().public_numbers()
    public_key = ("02" if numbers.y % 2 == 0 else "03") + f"{numbers.x:064x}"
    return private_key, public_key, derive_thr_address_from_public_key_hex(public_key)


def _signed_request(action, payload, nonce, private_value=71):
    private_key, public_key, address = _key_material(private_value)
    issued_at = int(time.time())
    envelope = {
        "signature_format": FULL_PAYLOAD_SIGNATURE_FORMAT,
        "protocol_version": FULL_PAYLOAD_PROTOCOL_VERSION,
        "domain": FULL_PAYLOAD_DOMAIN,
        "chain_id": FULL_PAYLOAD_CHAIN_ID,
        "action": action,
        "canonical_v1_address": address,
        "from": address,
        "signer_address": address,
        "bound_key_address": None,
        "public_key": public_key,
        "payload": payload,
        "issued_at": str(issued_at),
        "expires_at": str(issued_at + 120),
        "nonce": nonce,
    }
    message, _ = canonical_signed_request_bytes(envelope)
    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    envelope["signature"] = f"{r:064x}{s:064x}"
    envelope["signing_payload_hash"] = hashlib.sha256(message).hexdigest()
    return envelope


@pytest.fixture(autouse=True)
def isolated_nonce_store(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / "wallet_v1_v2_route_nonces.sqlite3"),
    )


@pytest.mark.parametrize(
    ("route", "action", "payload", "override"),
    [
        ("/api/swap/execute", "swap", {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "0.9"}, {"trader_thr": "THR" + "A" * 40}),
        ("/api/swap/execute", "swap", {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "0.9"}, {"auth_secret": "unsigned-credential"}),
        ("/api/swap/execute", "swap", {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "0.9"}, {"from": "THR" + "B" * 40}),
        ("/api/v1/pools", "create_pool", {"token_a": "THR", "token_b": "WBTC", "amount_a": "1", "amount_b": "0.1"}, {"provider_thr": "THR" + "A" * 40}),
        ("/api/v1/pools", "create_pool", {"token_a": "THR", "token_b": "WBTC", "amount_a": "1", "amount_b": "0.1"}, {"fee_bps": "999"}),
        ("/api/v1/pools/add_liquidity", "add_liquidity", {"pool_id": "pool-1", "amount_a": "1", "amount_b": "0.1"}, {"provider_thr": "THR" + "A" * 40}),
        ("/api/v1/pools/add_liquidity", "add_liquidity", {"pool_id": "pool-1", "amount_a": "1", "amount_b": "0.1"}, {"referrer": "THR" + "C" * 40}),
        ("/api/v1/pools/remove_liquidity", "remove_liquidity", {"pool_id": "pool-1", "shares": "1"}, {"provider_thr": "THR" + "A" * 40}),
        ("/api/v1/music/tip", "tip", {"track_id": "track-1", "amount": "1", "token_symbol": "THR"}, {"from_address": "THR" + "A" * 40}),
        ("/api/v1/music/tip", "tip", {"track_id": "track-1", "amount": "1", "token_symbol": "THR"}, {"token_symbol": "WBTC"}),
        ("/api/legacy/create", "create_legacy", {"heirs": [], "inactivity_days": "365"}, {"heirs": [{"address": "THR" + "A" * 40, "percentage": "100"}]}),
        ("/api/legacy/claim", "claim_legacy", {"owner_address": "THR" + "D" * 40}, {"owner_address": "THR" + "E" * 40}),
    ],
)
def test_valid_v2_signature_with_unsigned_override_is_rejected_before_verification(
    monkeypatch, route, action, payload, override
):
    signed = _signed_request(action, payload, f"override-{action}-{next(iter(override))}")
    signed.update(override)
    verification_calls = []
    real_verify = server.verify_wallet_v1_signed_request

    def tracked_verify(*args, **kwargs):
        verification_calls.append(True)
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(server, "verify_wallet_v1_signed_request", tracked_verify)
    response = server.app.test_client().post(route, json=signed)
    body = response.get_json()
    assert response.status_code == 400
    assert body["error"] in {"unsigned_top_level_fields", "sender_alias_mismatch"}
    assert verification_calls == []


def _install_synthetic_financial_state(monkeypatch, address):
    states = {
        server.LEDGER_FILE: {address: 100.0},
        server.WBTC_LEDGER_FILE: {address: 10.0},
        server.L2E_LEDGER_FILE: {},
        server.CHAIN_FILE: [],
    }
    pools = []
    token_balances = {"USDT": {address: 0.0}}

    monkeypatch.setattr(server, "load_json", lambda path, default=None: states.setdefault(path, default if default is not None else {}))
    monkeypatch.setattr(server, "save_json", lambda path, value: states.__setitem__(path, value))
    monkeypatch.setattr(server, "load_pools", lambda: pools)
    monkeypatch.setattr(server, "save_pools", lambda value: pools.__setitem__(slice(None), value))
    monkeypatch.setattr(server, "load_token_balances", lambda: token_balances)
    monkeypatch.setattr(server, "save_token_balances", lambda value: token_balances.update(value))
    monkeypatch.setattr(server, "load_custom_tokens", lambda: {})
    monkeypatch.setattr(server, "load_custom_token_ledger_by_symbol", lambda _symbol: {})
    monkeypatch.setattr(server, "save_custom_token_ledger_by_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "get_wallet_balances", lambda wallet: {
        "thr": states[server.LEDGER_FILE].get(wallet, 0),
        "wbtc": states[server.WBTC_LEDGER_FILE].get(wallet, 0),
        "l2e": 0,
        "tokens": [],
    })
    for name in ("update_last_block", "persist_normalized_tx", "broadcast_tx", "_index_transaction_event"):
        monkeypatch.setattr(server, name, lambda *_args, **_kwargs: None)
    return states, pools, token_balances


def test_real_swap_handler_executes_only_signed_values(monkeypatch):
    _, _, address = _key_material(71)
    states, pools, token_balances = _install_synthetic_financial_state(monkeypatch, address)
    pools.append({
        "id": "swap-pool", "token_a": "THR", "token_b": "USDT",
        "reserves_a": 1000.0, "reserves_b": 1000.0, "total_shares": 1000.0,
        "providers": {}, "fee_bps": 30,
    })
    monkeypatch.setattr(server, "is_swap_symbol_allowed", lambda symbol: symbol in {"THR", "USDT"})
    monkeypatch.setattr(server, "quote_swap_route", lambda *_args: ({
        "amount_out": 0.99,
        "legs": [{"pool_id": "swap-pool", "token_in": "THR", "token_out": "USDT"}],
        "route": ["THR", "USDT"],
    }, None))
    rejected = _signed_request(
        "swap",
        {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "1.01"},
        "runtime-swap-slippage",
    )
    response = server.app.test_client().post("/api/swap/execute", json=rejected)
    assert response.status_code == 400
    assert response.get_json()["error"] == "slippage_too_high"
    assert states[server.LEDGER_FILE][address] == 100.0
    assert token_balances["USDT"][address] == 0.0

    request = _signed_request(
        "swap",
        {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "0.9"},
        "runtime-swap",
    )
    response = server.app.test_client().post("/api/swap/execute", json=request)
    body = response.get_json()
    assert response.status_code == 200
    assert body["amount_in"] == 1.0
    assert states[server.LEDGER_FILE][address] == 99.0
    assert token_balances["USDT"][address] > 0
    assert states[server.CHAIN_FILE][-1]["trader"] == address
    assert states[server.CHAIN_FILE][-1]["token_in"] == "THR"


def test_concurrent_replay_is_exactly_once_with_shared_sqlite_nonce_store(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / "shared-worker-nonces.sqlite3"),
    )

    def consume(_index):
        return server._consume_wallet_v1_signed_request_nonce(
            "THR" + "7" * 40, "concurrent-sqlite", int(time.time())
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(consume, range(16)))
    assert sum(ok for ok, _error in results) == 1
    assert sum(error == "nonce_replay_detected" for ok, error in results if not ok) == 15


def test_concurrent_replay_uses_atomic_redis_nx_contract(monkeypatch):
    class AtomicRedis:
        def __init__(self):
            self.keys = set()
            self.lock = threading.Lock()

        def set(self, key, _value, *, ex, nx):
            assert ex == 600 and nx is True
            with self.lock:
                if key in self.keys:
                    return False
                self.keys.add(key)
                return True

    monkeypatch.setattr(server, "REDIS_CLIENT", AtomicRedis())

    def consume(_index):
        return server._consume_wallet_v1_signed_request_nonce(
            "THR" + "8" * 40, "concurrent-redis", int(time.time())
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(consume, range(16)))
    assert sum(ok for ok, _error in results) == 1
    assert sum(error == "nonce_replay_detected" for ok, error in results if not ok) == 15


def test_real_pool_create_add_remove_handlers_use_canonical_provider(monkeypatch):
    _, _, address = _key_material(71)
    states, pools, _ = _install_synthetic_financial_state(monkeypatch, address)
    client = server.app.test_client()

    created = client.post("/api/v1/pools", json=_signed_request(
        "create_pool",
        {"token_a": "THR", "token_b": "WBTC", "amount_a": "10", "amount_b": "1", "fee_bps": "30"},
        "runtime-pool-create",
    ))
    assert created.status_code == 201
    pool_id = created.get_json()["pool"]["id"]
    assert pools[0]["providers"].keys() == {address}
    assert states[server.LEDGER_FILE][address] == 90.0
    assert states[server.WBTC_LEDGER_FILE][address] == 9.0

    added = client.post("/api/v1/pools/add_liquidity", json=_signed_request(
        "add_liquidity",
        {"pool_id": pool_id, "amount_a": "5", "amount_b": "0.5", "referrer": ""},
        "runtime-pool-add",
    ))
    assert added.status_code == 200
    assert states[server.LEDGER_FILE][address] == 85.0
    assert states[server.WBTC_LEDGER_FILE][address] == 8.5

    removed = client.post("/api/v1/pools/remove_liquidity", json=_signed_request(
        "remove_liquidity", {"pool_id": pool_id, "shares": "1"}, "runtime-pool-remove"
    ))
    assert removed.status_code == 200
    assert removed.get_json()["shares_burned"] == 1.0
    assert address in pools[0]["providers"]


def test_real_music_tip_handler_uses_signed_sender_amount_asset_and_registry_recipient(monkeypatch):
    _, _, address = _key_material(71)
    artist = "THR" + "9" * 40
    ledger = {address: 20.0, artist: 0.0}
    chain = []
    registry = {
        "tracks": [{"id": "track-1", "title": "Synthetic", "artist_address": artist, "tips_total": 0}],
        "artists": {artist: {"total_earnings": 0, "token_earnings": {}}},
        "plays": {},
    }
    monkeypatch.setattr(server, "load_music_registry", lambda: registry)
    monkeypatch.setattr(server, "save_music_registry", lambda value: registry.update(value))
    monkeypatch.setattr(server, "load_json", lambda path, default=None: ledger if path == server.LEDGER_FILE else chain if path == server.CHAIN_FILE else (default or {}))
    monkeypatch.setattr(server, "save_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "split_and_credit_fee", lambda fee, source=None: {"agent_share": fee / 2, "burn_share": fee / 2})
    for name in ("persist_normalized_tx", "update_last_block", "_track_music_play", "emit_crosschain_event"):
        monkeypatch.setattr(server, name, lambda *_args, **_kwargs: {})
    request = _signed_request(
        "tip", {"track_id": "track-1", "amount": "2", "token_symbol": "THR"}, "runtime-tip"
    )
    response = server.app.test_client().post("/api/v1/music/tip", json=request)
    assert response.status_code == 200
    assert ledger[artist] == 2.0
    assert ledger[address] < 18.0
    assert chain[-1]["from"] == address
    assert chain[-1]["to"] == artist
    assert chain[-1]["amount"] == 2.0
    assert chain[-1]["token_symbol"] == "THR"


def test_real_digital_legacy_handlers_bind_definition_owner_heir_and_claim_amount(monkeypatch):
    _, _, owner = _key_material(71)
    _, _, heir = _key_material(72)
    _, _, second_heir = _key_material(73)
    legacies = {}
    ledger = {owner: 100.0, heir: 0.0}
    chain = []
    monkeypatch.setattr(server, "_load_legacies", lambda: legacies)
    monkeypatch.setattr(server, "_save_legacies", lambda value: legacies.update(value))
    monkeypatch.setattr(server, "load_json", lambda path, default=None: ledger if path == server.LEDGER_FILE else chain if path == server.CHAIN_FILE else (default or {}))
    monkeypatch.setattr(server, "save_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "persist_normalized_tx", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "update_last_block", lambda *_args, **_kwargs: None)
    client = server.app.test_client()

    created = client.post("/api/legacy/create", json=_signed_request(
        "create_legacy",
        {"title": "Synthetic", "description": "", "heirs": [
            {"address": heir, "name": "Heir", "percentage": "25", "relationship": "test"},
            {"address": second_heir, "name": "Second", "percentage": "75", "relationship": "test"},
        ], "inactivity_days": "1"},
        "runtime-legacy-create",
        private_value=71,
    ))
    assert created.status_code == 200
    assert legacies[owner]["owner"] == owner
    assert legacies[owner]["heirs"][0]["address"] == heir

    pinged = client.post("/api/legacy/ping", json=_signed_request(
        "legacy_ping", {}, "runtime-legacy-ping", private_value=71
    ))
    assert pinged.status_code == 200
    legacies[owner]["last_owner_activity"] = int(time.time()) - 3 * 86400

    claimed = client.post("/api/legacy/claim", json=_signed_request(
        "claim_legacy", {"owner_address": owner}, "runtime-legacy-claim", private_value=72
    ))
    assert claimed.status_code == 200
    assert ledger[owner] == 75.0
    assert ledger[heir] == 25.0

