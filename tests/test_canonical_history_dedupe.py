"""Tests for Issue #817 — canonical multichain event identity and exactly-once history dedup.

Tests required per the issue:
 1. Same BSC chain_id+tx_hash+log_index written twice → one record.
 2. Same tx hash with different log indexes → two records.
 3. Same hash on different chain IDs → two records.
 4. Retry/restart path → still one record.
 5. Pool add-liquidity duplicate regression.
 6. External BSC USDT send visible in BSC history.
 7. Arbitrum USDC event visible only in Arbitrum history.
 8. Internal THR transfer visible only in Thronos history.
 9. Normalized output parity for PWA/web/APK consumer format.
10. No wallet keys, secrets, payout code, or economic changes.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_history(monkeypatch, tmp_path):
    """Point WALLET_HISTORY_FILE at a fresh temp file; return its path."""
    hfile = str(tmp_path / "wallet_history.json")
    monkeypatch.setattr(server, "WALLET_HISTORY_FILE", hfile)
    server.save_json(hfile, [])
    return hfile


def _load(hfile):
    return server.load_json(hfile, [])


# ---------------------------------------------------------------------------
# 1. Same BSC chain_id+tx_hash+log_index written twice → one record
# ---------------------------------------------------------------------------

def test_same_bsc_event_written_twice_yields_one_record(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    kwargs = dict(
        thr_address="THR_ALICE",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        status="pending",
        direction="in",
        external_txid="0xabc123",
        log_index=0,
    )
    e1 = server.add_wallet_history_event(**kwargs)
    e2 = server.add_wallet_history_event(**kwargs)

    history = _load(hfile)
    assert len(history) == 1, f"Expected 1 record, got {len(history)}"
    assert history[0]["canonical_id"] == "bsc:0xabc123:0"


# ---------------------------------------------------------------------------
# 2. Same tx hash with different log indexes → two records
# ---------------------------------------------------------------------------

def test_same_tx_hash_different_log_index_yields_two_records(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        thr_address="THR_BOB",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=50.0,
        direction="in",
        external_txid="0xdef456",
    )
    server.add_wallet_history_event(**common, log_index=0)
    server.add_wallet_history_event(**common, log_index=1)

    history = _load(hfile)
    assert len(history) == 2
    cids = {h["canonical_id"] for h in history}
    assert "bsc:0xdef456:0" in cids
    assert "bsc:0xdef456:1" in cids


# ---------------------------------------------------------------------------
# 3. Same hash on different chain IDs → two records
# ---------------------------------------------------------------------------

def test_same_hash_different_chains_yields_two_records(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        thr_address="THR_CAROL",
        event_type="evm_token_receive",
        asset="USDC",
        amount=200.0,
        direction="in",
        external_txid="0x999aaa",
        log_index=0,
    )
    server.add_wallet_history_event(chain="bsc", **common)
    server.add_wallet_history_event(chain="arbitrum", **common)

    history = _load(hfile)
    assert len(history) == 2
    chains = {h["chain"] for h in history}
    assert chains == {"bsc", "arbitrum"}


# ---------------------------------------------------------------------------
# 4. Retry/restart path → still one record
# ---------------------------------------------------------------------------

def test_watcher_retry_restart_still_one_record(monkeypatch, tmp_path):
    """Simulate a watcher delivering the same event 5 times (restart/retry)."""
    hfile = _empty_history(monkeypatch, tmp_path)

    kwargs = dict(
        thr_address="THR_DAVE",
        event_type="pool_external_deposit",
        chain="bsc",
        asset="USDT",
        amount=500.0,
        status="pending",
        direction="pool",
        external_txid="0xretry777",
        log_index=3,
        pool_id="POOL-BSC-USDT-001",
    )
    for _ in range(5):
        server.add_wallet_history_event(**kwargs)

    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["pool_id"] == "POOL-BSC-USDT-001"


# ---------------------------------------------------------------------------
# 5. Pool add-liquidity duplicate regression
# ---------------------------------------------------------------------------

def test_pool_add_liquidity_no_duplicate(monkeypatch, tmp_path):
    """Two calls with the same external_txid+log_index for an LP mint must not duplicate."""
    hfile = _empty_history(monkeypatch, tmp_path)

    kwargs = dict(
        thr_address="THR_EVE",
        event_type="pool_add_liquidity_lp_minted",
        chain="bsc",
        asset="USDT",
        amount=1000.0,
        status="confirmed",
        direction="pool",
        external_txid="0xlpmint111",
        log_index=0,
        pool_id="POOL-BSC-USDT-001",
        lp_shares=42.5,
        pair="THR/USDT",
    )
    server.add_wallet_history_event(**kwargs)
    server.add_wallet_history_event(**kwargs)

    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["lp_shares"] == 42.5


# ---------------------------------------------------------------------------
# 6. External BSC USDT send visible in BSC history
# ---------------------------------------------------------------------------

def test_external_bsc_usdt_send_in_bsc_history(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    real_tx_hash = "0xbscrealtx123456789abcdef"
    server.add_wallet_history_event(
        thr_address="THR_FRANK",
        event_type="evm_token_send",
        chain="bsc",
        asset="USDT",
        amount=250.0,
        status="confirmed",
        direction="out",
        external_txid=real_tx_hash,
        log_index=0,
        token_standard="BEP20",
        external_from="0xSenderAddr",
        external_to="0xReceiverAddr",
    )

    history = _load(hfile)
    assert len(history) == 1
    evt = history[0]
    assert evt["chain"] == "bsc"
    assert evt["external_txid"] == real_tx_hash
    assert evt["external_txid"] != "", "Must have real on-chain tx hash, not empty"
    assert "simulated" not in evt["external_txid"].lower()
    assert evt["asset"] == "USDT"
    assert evt["token_standard"] == "BEP20"

    bsc_events = [e for e in history if e["chain"] == "bsc"]
    assert len(bsc_events) == 1


# ---------------------------------------------------------------------------
# 7. Arbitrum USDC event visible only in Arbitrum history
# ---------------------------------------------------------------------------

def test_arbitrum_usdc_only_in_arbitrum_history(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    server.add_wallet_history_event(
        thr_address="THR_GRACE",
        event_type="evm_token_receive",
        chain="arbitrum",
        asset="USDC",
        amount=300.0,
        status="confirmed",
        direction="in",
        external_txid="0xarb_usdc_tx_001",
        log_index=0,
    )
    server.add_wallet_history_event(
        thr_address="THR_GRACE",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        status="confirmed",
        direction="in",
        external_txid="0xbsc_usdt_tx_002",
        log_index=0,
    )

    history = _load(hfile)
    arb_events = [e for e in history if e["chain"] == "arbitrum"]
    bsc_events = [e for e in history if e["chain"] == "bsc"]

    assert len(arb_events) == 1
    assert arb_events[0]["asset"] == "USDC"
    assert len(bsc_events) == 1
    assert bsc_events[0]["asset"] == "USDT"


# ---------------------------------------------------------------------------
# 8. Internal THR transfer visible only in Thronos history
# ---------------------------------------------------------------------------

def test_internal_thr_only_in_thronos_history(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    server.add_wallet_history_event(
        thr_address="THR_HEIDI",
        event_type="token_send",
        chain="thronos",
        asset="THR",
        amount=10.0,
        status="confirmed",
        direction="out",
        internal_txid="TXID-INT-001",
    )
    server.add_wallet_history_event(
        thr_address="THR_HEIDI",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=50.0,
        status="confirmed",
        direction="in",
        external_txid="0xbscexternal999",
        log_index=0,
    )

    history = _load(hfile)
    thr_events = [e for e in history if e["chain"] == "thronos"]
    bsc_events = [e for e in history if e["chain"] == "bsc"]

    assert len(thr_events) == 1
    assert thr_events[0]["internal_txid"] == "TXID-INT-001"
    assert thr_events[0]["asset"] == "THR"
    assert len(bsc_events) == 1
    assert bsc_events[0]["chain"] == "bsc"


# ---------------------------------------------------------------------------
# 9. Normalized output parity for PWA/web/APK consumer format
# ---------------------------------------------------------------------------

def test_normalized_output_consumer_format(monkeypatch, tmp_path):
    """All consumer surfaces must see the same fields from the backend record."""
    hfile = _empty_history(monkeypatch, tmp_path)

    server.add_wallet_history_event(
        thr_address="THR_IVAN",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        status="confirmed",
        direction="in",
        external_txid="0xformat_check_tx",
        log_index=2,
        token_standard="BEP20",
        token_contract="0xContractAddr",
        network_label="BSC Mainnet",
        external_from="0xSender",
        external_to="0xReceiver",
    )

    history = _load(hfile)
    assert len(history) == 1
    evt = history[0]

    required_fields = [
        "id", "canonical_id", "thr_address", "event_type", "chain",
        "network_label", "asset", "token_standard", "token_contract",
        "amount", "status", "direction", "internal_txid", "external_txid",
        "external_from", "external_to", "explorer_url", "pool_id",
        "lp_shares", "pair", "note", "log_index", "timestamp", "created_at",
    ]
    for field in required_fields:
        assert field in evt, f"Missing field '{field}' in consumer output"

    assert evt["canonical_id"] == "bsc:0xformat_check_tx:2"
    assert evt["chain"] == "bsc"
    assert evt["log_index"] == 2
    assert isinstance(evt["timestamp"], float)
    assert isinstance(evt["amount"], float)


# ---------------------------------------------------------------------------
# 10. No wallet keys, secrets, payout code, or economic changes
# ---------------------------------------------------------------------------

def test_no_secrets_or_economic_side_effects(monkeypatch, tmp_path):
    """Verify add_wallet_history_event does not leak secrets or touch economics."""
    hfile = _empty_history(monkeypatch, tmp_path)

    server.add_wallet_history_event(
        thr_address="THR_JUDY",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=999.0,
        status="confirmed",
        direction="in",
        external_txid="0xseccheck",
        log_index=0,
    )

    history = _load(hfile)
    evt = history[0]

    raw = json.dumps(evt).lower()
    forbidden_patterns = [
        "private_key", "secret_key", "api_key", "stripe_key",
        "mnemonic", "seed_phrase", "password", "payout_execute",
        "wallet_unlock", "railway_token", "admin_secret",
    ]
    for pat in forbidden_patterns:
        assert pat not in raw, f"Forbidden pattern '{pat}' found in event record"

    assert evt["amount"] == 999.0
    assert evt["status"] == "confirmed"


# ---------------------------------------------------------------------------
# Bonus: status transition updates existing record
# ---------------------------------------------------------------------------

def test_status_transition_updates_existing_record(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        thr_address="THR_KATE",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        direction="in",
        external_txid="0xstatustx",
        log_index=0,
    )
    server.add_wallet_history_event(status="pending", **common)
    server.add_wallet_history_event(status="confirmed", **common)

    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["status"] == "confirmed"
    assert "updated_at" in history[0]


# ---------------------------------------------------------------------------
# Bonus: chain alias normalization
# ---------------------------------------------------------------------------

def test_chain_alias_normalization(monkeypatch, tmp_path):
    """bnb and bsc refer to the same chain; dedup must treat them as equal."""
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        thr_address="THR_LOU",
        event_type="evm_token_receive",
        asset="USDT",
        amount=50.0,
        direction="in",
        external_txid="0xaliascheck",
        log_index=0,
    )
    server.add_wallet_history_event(chain="bnb", **common)
    server.add_wallet_history_event(chain="bsc", **common)

    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["chain"] == "bsc"


def test_normalize_chain_id_unit():
    assert server.normalize_chain_id("bnb") == "bsc"
    assert server.normalize_chain_id("BNB") == "bsc"
    assert server.normalize_chain_id("bsc") == "bsc"
    assert server.normalize_chain_id("arb") == "arbitrum"
    assert server.normalize_chain_id("arbitrum-one") == "arbitrum"
    assert server.normalize_chain_id("ethereum") == "eth"
    assert server.normalize_chain_id("thr") == "thronos"
    assert server.normalize_chain_id("bitcoin") == "btc"
    assert server.normalize_chain_id("base") == "base"
    assert server.normalize_chain_id("") == ""
    assert server.normalize_chain_id(None) == ""


def test_canonical_event_id_unit():
    assert server.canonical_event_id("bsc", "0xABC", 0) == "bsc:0xabc:0"
    assert server.canonical_event_id("bnb", "0xABC", 0) == "bsc:0xabc:0"
    assert server.canonical_event_id("bsc", "0xABC", 1) == "bsc:0xabc:1"
    assert server.canonical_event_id("bsc", "0xABC", None) == "bsc:0xabc:-"
    assert server.canonical_event_id("arbitrum", "0xDEF", 0) == "arbitrum:0xdef:0"
    assert server.canonical_event_id("thronos", "TXID-INT-001", None) == "thronos:txid-int-001:-"
