"""Synthetic route tests for pledge lookup/migration compatibility.

No real address, credential, balance, or production file is used.
"""

import hashlib
import copy
import json

import pytest

import server_ext


SYNTHETIC_SECRET = "synthetic-wallet-pledge-secret-v1"
LEGACY_ADDRESS = "THR" + "A" * 40
CANONICAL_ADDRESS = "THR" + "B" * 40
BTC_ADDRESS = "mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn"


def _hash_variants(secret):
    sha256 = hashlib.sha256(secret.encode()).hexdigest()
    historical_sha256d_label = hashlib.sha256(sha256.encode()).hexdigest()
    hmac_label = hashlib.sha256(f"{secret}:auth".encode()).hexdigest()
    return sha256, historical_sha256d_label, hmac_label


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server_ext._srv, "PLEDGE_CHAIN", "/synthetic/pledge_chain.json")
    return server_ext.app.test_client()


@pytest.mark.parametrize("stored_hash", _hash_variants(SYNTHETIC_SECRET))
def test_pledge_lookup_accepts_each_historical_hash_variant(client, monkeypatch, stored_hash):
    pledge = {
        "send_seed_hash": stored_hash,
        "thr_address": LEGACY_ADDRESS,
        "btc_address": BTC_ADDRESS,
        "pledge_hash": "synthetic-pledge-hash",
    }
    monkeypatch.setattr(server_ext._srv, "load_json", lambda _path, _default: [pledge])

    response = client.post(
        "/api/wallet/v1/pledge-lookup", json={"send_secret": SYNTHETIC_SECRET}
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "thr_address": LEGACY_ADDRESS,
        "btc_address": BTC_ADDRESS,
        "pledge_hash": "synthetic-pledge-hash",
    }


def test_existing_pledge_migration_returns_same_canonical_wallet_idempotently(
    client, monkeypatch
):
    pledge = {
        "send_seed_hash": _hash_variants(SYNTHETIC_SECRET)[0],
        "thr_address": LEGACY_ADDRESS,
        "btc_address": BTC_ADDRESS,
        "pledge_hash": "synthetic-pledge-hash",
    }
    monkeypatch.setattr(server_ext._srv, "load_json", lambda _path, _default: [pledge])

    import wallet_v1_migration

    monkeypatch.setattr(
        wallet_v1_migration,
        "search_all_migration_sources",
        lambda **_kwargs: {"canonical_v1_address": CANONICAL_ADDRESS},
    )

    bodies = []
    for _ in range(2):
        response = client.post(
            "/api/wallet/v1/pledge-migrate",
            json={"send_secret": SYNTHETIC_SECRET, "pin": "synthetic-pin"},
        )
        assert response.status_code == 200
        bodies.append(response.get_json())

    assert bodies[0] == bodies[1]
    assert bodies[0]["canonical_v1_address"] == CANONICAL_ADDRESS
    assert bodies[0]["legacy_address"] == LEGACY_ADDRESS
    assert bodies[0]["already_migrated"] is True
    assert bodies[0]["recovery_kit"] is None
    assert bodies[0]["pdf_url"] is None


def test_forged_pledge_secret_cannot_lookup_or_migrate(client, monkeypatch):
    pledge = {
        "send_seed_hash": _hash_variants(SYNTHETIC_SECRET)[0],
        "thr_address": LEGACY_ADDRESS,
    }
    monkeypatch.setattr(server_ext._srv, "load_json", lambda _path, _default: [pledge])

    lookup = client.post(
        "/api/wallet/v1/pledge-lookup", json={"send_secret": "forged-synthetic-secret"}
    )
    migrate = client.post(
        "/api/wallet/v1/pledge-migrate",
        json={"send_secret": "forged-synthetic-secret", "pin": "synthetic-pin"},
    )
    assert lookup.status_code == 404
    assert lookup.get_json()["error"] == "pledge_not_found"
    assert migrate.status_code == 404
    assert migrate.get_json()["error"] == "pledge_not_found"


def test_fresh_synthetic_btc_pledge_reuses_the_same_wallet_on_confirmation_retry(
    client, monkeypatch
):
    server = server_ext._srv
    stores = {
        server.PLEDGE_CHAIN: [],
        server.CHAIN_FILE: [],
        server.WHITELIST_FILE: [BTC_ADDRESS],
    }

    def load_json(path, default=None):
        return copy.deepcopy(stores.get(path, default))

    def save_json(path, value):
        stores[path] = copy.deepcopy(value)

    monkeypatch.setattr(server, "load_json", load_json)
    monkeypatch.setattr(server, "save_json", save_json)
    monkeypatch.setattr(
        server,
        "create_secure_pdf_contract",
        lambda *_args, **_kwargs: "synthetic-pledge-contract.pdf",
    )

    first = client.post(
        "/pledge_submit",
        json={
            "btc_address": BTC_ADDRESS,
            "pledge_text": "Synthetic compatibility pledge",
            "passphrase": "synthetic-recovery-passphrase",
        },
    )
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body["created"] is True
    assert first_body["status"] == "newly_created"
    assert first_body["canonical_v1_address"].startswith("THR")
    recovery = json.loads(first_body["recovery_kit"])
    assert recovery["canonical_v1_address"] == first_body["canonical_v1_address"]
    assert recovery["public_key"] == stores[server.PLEDGE_CHAIN][0]["compressed_public_key"]

    repeated = client.post(
        "/pledge_submit",
        json={
            "btc_address": BTC_ADDRESS,
            "pledge_text": "Synthetic compatibility pledge",
            "passphrase": "synthetic-recovery-passphrase",
        },
    )
    assert repeated.status_code == 200
    repeated_body = repeated.get_json()
    assert repeated_body["created"] is False
    assert repeated_body["status"] == "already_has_canonical"
    assert repeated_body["canonical_v1_address"] == first_body["canonical_v1_address"]
    assert len(stores[server.PLEDGE_CHAIN]) == 1


def test_fresh_synthetic_usdt_pledge_keeps_lookup_hashes_and_rejects_duplicate_tx(
    client, monkeypatch
):
    server = server_ext._srv
    bnb_address = "0x" + "1" * 40
    bnb_txid = "0x" + "2" * 64
    thr_address = "THR" + "C" * 40
    wallet_history_file = server.WALLET_HISTORY_FILE
    stores = {
        server.PLEDGE_CHAIN: [],
        server.CHAIN_FILE: [],
        server.LEDGER_FILE: {},
        wallet_history_file: [],
    }

    def load_json(path, default=None):
        return copy.deepcopy(stores.get(path, default))

    def save_json(path, value):
        stores[path] = copy.deepcopy(value)

    def add_history(**event):
        stores[wallet_history_file].append(copy.deepcopy(event))

    monkeypatch.setattr(server, "load_json", load_json)
    monkeypatch.setattr(server, "save_json", save_json)
    monkeypatch.setattr(server, "create_secure_pdf_contract", lambda *_a, **_k: "synthetic-usdt.pdf")
    monkeypatch.setattr(server, "_seed_usdt_thr_pool", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "_update_address_bucket", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "_add_pledge_pool_floor", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "add_wallet_history_event", add_history)
    monkeypatch.setattr(server, "update_last_block", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "broadcast_tx", lambda *_a, **_k: None)

    success, result, error = server.process_usdt_pledge_credit(
        thr_address, bnb_address, server.MIN_USDT_PLEDGE, bnb_txid, source="synthetic_test"
    )
    assert success is True
    assert error is None
    assert result["thr_address"] == thr_address
    assert len(stores[server.PLEDGE_CHAIN]) == 1
    pledge = stores[server.PLEDGE_CHAIN][0]
    assert pledge["pledge_type"] == "usdt_bnb"
    assert pledge["thr_address"] == thr_address
    assert pledge["send_seed_hash"] == hashlib.sha256(pledge["send_seed"].encode()).hexdigest()
    assert pledge["send_auth_hash"] == hashlib.sha256(
        f"{pledge['send_seed']}:auth".encode()
    ).hexdigest()

    lookup = client.post(
        "/api/wallet/v1/pledge-lookup", json={"send_secret": pledge["send_seed"]}
    )
    assert lookup.status_code == 200
    assert lookup.get_json()["thr_address"] == thr_address

    duplicate_ok, _duplicate_result, duplicate_error = server.process_usdt_pledge_credit(
        thr_address, bnb_address, server.MIN_USDT_PLEDGE, bnb_txid, source="synthetic_test"
    )
    assert duplicate_ok is False
    assert duplicate_error == "duplicate_tx_already_processed"
    assert len(stores[server.PLEDGE_CHAIN]) == 1
