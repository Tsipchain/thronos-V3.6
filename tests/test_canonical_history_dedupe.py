"""Tests for Issue #817 — canonical multichain event identity and exactly-once
history dedup (v2: per-wallet projection, numeric chain-ids, log_index safety).

Required scenarios (user feedback):
 1. Duplicate same BSC event in same wallet → one projection
 2. Same transfer sender + receiver → two correct wallet projections,
    no global collapse
 3. Same tx different log_index → two events
 4. BSC mainnet and BSC testnet same hash → two events (numeric chain id)
 5. EVM multi-log tx without log_index → reconciliation flag, never false dedupe
 6. Concurrent duplicate delivery → exactly one projection
 7. Retry/restart → exactly one projection
 8. BSC only BSC history, Arbitrum only Arbitrum, internal THR only Thronos
 9. Pool add-liquidity duplicate regression
10. Normalized consumer output compatible with PWA/APK/web/WalletConnect
"""
import json
import os
import sys
import threading
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
# 1. Duplicate same BSC event in same wallet → one projection
# ---------------------------------------------------------------------------

def test_duplicate_bsc_event_same_wallet_one_projection(monkeypatch, tmp_path):
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
        token_standard="BEP20",
    )
    e1 = server.add_wallet_history_event(**kwargs)
    e2 = server.add_wallet_history_event(status="confirmed", **{
        k: v for k, v in kwargs.items() if k != "status"
    })

    history = _load(hfile)
    assert len(history) == 1, f"Expected 1 record, got {len(history)}"
    assert history[0]["canonical_id"] == "56:0xabc123:0"
    assert history[0]["status"] == "confirmed"
    assert "updated_at" in history[0]


# ---------------------------------------------------------------------------
# 2. Same transfer sender + receiver → two per-wallet projections
# ---------------------------------------------------------------------------

def test_same_transfer_sender_receiver_two_wallet_projections(monkeypatch, tmp_path):
    """The same on-chain event legitimately appears for sender and receiver.
    Per-wallet dedupe must NOT collapse them into one."""
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        event_type="evm_token_transfer",
        chain="bsc",
        asset="USDT",
        amount=500.0,
        status="confirmed",
        external_txid="0xtransfer_abc",
        log_index=0,
        token_standard="BEP20",
    )
    server.add_wallet_history_event(
        thr_address="THR_SENDER",
        direction="out",
        external_from="0xSenderEVM",
        external_to="0xReceiverEVM",
        **common,
    )
    server.add_wallet_history_event(
        thr_address="THR_RECEIVER",
        direction="in",
        external_from="0xSenderEVM",
        external_to="0xReceiverEVM",
        **common,
    )

    history = _load(hfile)
    assert len(history) == 2, (
        f"Expected 2 per-wallet projections, got {len(history)} — "
        "global dedupe must NOT collapse sender and receiver"
    )

    sender_evts = [e for e in history if e["thr_address"] == "THR_SENDER"]
    receiver_evts = [e for e in history if e["thr_address"] == "THR_RECEIVER"]
    assert len(sender_evts) == 1
    assert len(receiver_evts) == 1
    assert sender_evts[0]["direction"] == "out"
    assert receiver_evts[0]["direction"] == "in"
    assert sender_evts[0]["canonical_id"] == receiver_evts[0]["canonical_id"]

    server.add_wallet_history_event(
        thr_address="THR_SENDER",
        direction="out",
        external_from="0xSenderEVM",
        external_to="0xReceiverEVM",
        **common,
    )
    history = _load(hfile)
    assert len(history) == 2, "Duplicate for same wallet must be deduplicated"


# ---------------------------------------------------------------------------
# 3. Same tx different log_index → two events
# ---------------------------------------------------------------------------

def test_same_tx_different_log_index_yields_two_events(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        thr_address="THR_BOB",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=50.0,
        direction="in",
        external_txid="0xdef456",
        token_standard="BEP20",
    )
    server.add_wallet_history_event(**common, log_index=0)
    server.add_wallet_history_event(**common, log_index=1)

    history = _load(hfile)
    assert len(history) == 2
    cids = {h["canonical_id"] for h in history}
    assert "56:0xdef456:0" in cids
    assert "56:0xdef456:1" in cids


# ---------------------------------------------------------------------------
# 4. BSC mainnet (56) and BSC testnet (97) same hash → two events
# ---------------------------------------------------------------------------

def test_bsc_mainnet_testnet_same_hash_two_events(monkeypatch, tmp_path):
    """Numeric chain-id must separate mainnet from testnet even if the
    label were the same."""
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        thr_address="THR_CAROL",
        event_type="evm_token_receive",
        asset="USDT",
        amount=200.0,
        direction="in",
        external_txid="0x999aaa",
        log_index=0,
        token_standard="BEP20",
    )
    server.add_wallet_history_event(
        chain="bsc", numeric_chain_id=56, **common,
    )
    server.add_wallet_history_event(
        chain="bsc-testnet", numeric_chain_id=97, **common,
    )

    history = _load(hfile)
    assert len(history) == 2, (
        f"Expected 2 events (mainnet+testnet), got {len(history)}"
    )
    cids = {h["canonical_id"] for h in history}
    assert "56:0x999aaa:0" in cids
    assert "97:0x999aaa:0" in cids


# ---------------------------------------------------------------------------
# 5. EVM multi-log tx without log_index → reconciliation flag
# ---------------------------------------------------------------------------

def test_evm_token_event_without_log_index_flags_reconciliation(monkeypatch, tmp_path):
    """Token events (BEP20/ERC20) missing log_index must be flagged, never
    silently merged with another log from the same tx."""
    hfile = _empty_history(monkeypatch, tmp_path)

    server.add_wallet_history_event(
        thr_address="THR_DAVE",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        direction="in",
        external_txid="0xmultilog",
        log_index=None,
        token_standard="BEP20",
    )
    server.add_wallet_history_event(
        thr_address="THR_DAVE",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDC",
        amount=200.0,
        direction="in",
        external_txid="0xmultilog",
        log_index=None,
        token_standard="BEP20",
    )

    history = _load(hfile)
    flagged = [e for e in history if e.get("needs_reconciliation")]
    assert len(flagged) >= 1, "Token events without log_index must be flagged"

    for evt in flagged:
        assert evt["needs_reconciliation"] is True

    native_evt = server.add_wallet_history_event(
        thr_address="THR_DAVE",
        event_type="evm_native_receive",
        chain="bsc",
        asset="BNB",
        amount=1.0,
        direction="in",
        external_txid="0xnativetx",
        log_index=None,
        token_standard="native",
    )
    assert native_evt.get("needs_reconciliation") is not True, (
        "Native transfers without log_index should NOT be flagged"
    )


# ---------------------------------------------------------------------------
# 6. Concurrent duplicate delivery → exactly one projection
# ---------------------------------------------------------------------------

def test_concurrent_duplicate_delivery_exactly_one(monkeypatch, tmp_path):
    """Simulate multiple threads delivering the same event concurrently."""
    hfile = _empty_history(monkeypatch, tmp_path)

    kwargs = dict(
        thr_address="THR_EVE",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=300.0,
        status="confirmed",
        direction="in",
        external_txid="0xconcurrent",
        log_index=5,
        token_standard="BEP20",
    )

    results = []
    errors = []

    def deliver():
        try:
            r = server.add_wallet_history_event(**kwargs)
            results.append(r)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=deliver) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected errors: {errors}"

    history = _load(hfile)
    matching = [
        e for e in history
        if e.get("canonical_id") == "56:0xconcurrent:5"
        and e.get("thr_address") == "THR_EVE"
    ]
    assert len(matching) == 1, (
        f"Expected exactly 1 projection, got {len(matching)} — "
        "concurrent delivery must be serialised"
    )


# ---------------------------------------------------------------------------
# 7. Retry/restart → exactly one projection
# ---------------------------------------------------------------------------

def test_watcher_retry_restart_one_projection(monkeypatch, tmp_path):
    """Simulate a watcher delivering the same event 5 times (crash + restart)."""
    hfile = _empty_history(monkeypatch, tmp_path)

    kwargs = dict(
        thr_address="THR_FRANK",
        event_type="pool_external_deposit",
        chain="bsc",
        asset="USDT",
        amount=500.0,
        status="pending",
        direction="pool",
        external_txid="0xretry777",
        log_index=3,
        pool_id="POOL-BSC-USDT-001",
        token_standard="BEP20",
    )
    for i in range(5):
        server.add_wallet_history_event(**kwargs)

    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["pool_id"] == "POOL-BSC-USDT-001"
    assert history[0]["canonical_id"] == "56:0xretry777:3"

    server.add_wallet_history_event(status="confirmed", **{
        k: v for k, v in kwargs.items() if k != "status"
    })
    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["status"] == "confirmed"


# ---------------------------------------------------------------------------
# 8. Chain isolation: BSC→BSC, Arbitrum→Arbitrum, THR→Thronos
# ---------------------------------------------------------------------------

def test_chain_isolation_bsc_arbitrum_thronos(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    server.add_wallet_history_event(
        thr_address="THR_GRACE",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        direction="in",
        external_txid="0xbsctx1",
        log_index=0,
        token_standard="BEP20",
    )
    server.add_wallet_history_event(
        thr_address="THR_GRACE",
        event_type="evm_token_receive",
        chain="arbitrum",
        asset="USDC",
        amount=200.0,
        direction="in",
        external_txid="0xarbtx1",
        log_index=0,
        token_standard="ERC20",
    )
    server.add_wallet_history_event(
        thr_address="THR_GRACE",
        event_type="token_send",
        chain="thronos",
        asset="THR",
        amount=10.0,
        direction="out",
        internal_txid="TXID-INT-001",
    )

    history = _load(hfile)
    bsc = [e for e in history if e["chain"] == "bsc"]
    arb = [e for e in history if e["chain"] == "arbitrum"]
    thr = [e for e in history if e["chain"] == "thronos"]

    assert len(bsc) == 1 and bsc[0]["asset"] == "USDT"
    assert len(arb) == 1 and arb[0]["asset"] == "USDC"
    assert len(thr) == 1 and thr[0]["asset"] == "THR"

    assert bsc[0]["canonical_id"].startswith("56:")
    assert arb[0]["canonical_id"].startswith("42161:")
    assert thr[0]["canonical_id"].startswith("thronos:")


# ---------------------------------------------------------------------------
# 9. Pool add-liquidity duplicate regression
# ---------------------------------------------------------------------------

def test_pool_add_liquidity_no_duplicate(monkeypatch, tmp_path):
    """Two calls with the same external_txid+log_index for an LP mint
    must not create duplicate history entries."""
    hfile = _empty_history(monkeypatch, tmp_path)

    kwargs = dict(
        thr_address="THR_HEIDI",
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
        token_standard="BEP20",
    )
    server.add_wallet_history_event(**kwargs)
    server.add_wallet_history_event(**kwargs)

    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["lp_shares"] == 42.5
    assert history[0]["canonical_id"] == "56:0xlpmint111:0"


# ---------------------------------------------------------------------------
# 10. Normalized consumer output compatible with PWA/APK/web/WalletConnect
# ---------------------------------------------------------------------------

def test_normalized_consumer_output_format(monkeypatch, tmp_path):
    """All consumer surfaces must see the same canonical field set."""
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
        token_contract="0x55d398326f99059fF775485246999027B3197955",
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
        "lp_shares", "pair", "note", "log_index", "numeric_chain_id",
        "timestamp", "created_at",
    ]
    for field in required_fields:
        assert field in evt, f"Missing field '{field}' in consumer output"

    assert evt["canonical_id"] == "56:0xformat_check_tx:2"
    assert evt["numeric_chain_id"] == 56
    assert evt["chain"] == "bsc"
    assert evt["log_index"] == 2
    assert isinstance(evt["timestamp"], float)
    assert isinstance(evt["amount"], float)

    raw = json.dumps(evt).lower()
    forbidden = [
        "private_key", "secret_key", "api_key", "stripe_key",
        "mnemonic", "seed_phrase", "password", "payout_execute",
        "wallet_unlock", "railway_token", "admin_secret",
    ]
    for pat in forbidden:
        assert pat not in raw, f"Forbidden pattern '{pat}' found in event"


# ---------------------------------------------------------------------------
# Unit tests: canonical_event_id with numeric chain IDs
# ---------------------------------------------------------------------------

def test_canonical_event_id_uses_numeric_chain_id():
    assert server.canonical_event_id("bsc", "0xABC", 0) == "56:0xabc:0"
    assert server.canonical_event_id("bnb", "0xABC", 0) == "56:0xabc:0"
    assert server.canonical_event_id("bsc", "0xABC", 1) == "56:0xabc:1"
    assert server.canonical_event_id("bsc", "0xABC", None) == "56:0xabc:-"
    assert server.canonical_event_id("arbitrum", "0xDEF", 0) == "42161:0xdef:0"
    assert server.canonical_event_id("eth", "0xGHI", 0) == "1:0xghi:0"
    assert server.canonical_event_id("base", "0xJKL", 0) == "8453:0xjkl:0"
    assert server.canonical_event_id("thronos", "TXID-001", None) == "thronos:txid-001:-"
    assert server.canonical_event_id("btc", "btctx1", None) == "btc:btctx1:-"

    assert server.canonical_event_id(
        "bsc", "0xABC", 0, numeric_chain_id=97
    ) == "97:0xabc:0"


def test_normalize_chain_id():
    assert server.normalize_chain_id("bnb") == "bsc"
    assert server.normalize_chain_id("BNB") == "bsc"
    assert server.normalize_chain_id("arb") == "arbitrum"
    assert server.normalize_chain_id("ethereum") == "eth"
    assert server.normalize_chain_id("thr") == "thronos"
    assert server.normalize_chain_id("") == ""
    assert server.normalize_chain_id(None) == ""


def test_network_chain_id_lookup():
    assert server.network_chain_id("bsc") == 56
    assert server.network_chain_id("bsc-testnet") == 97
    assert server.network_chain_id("arbitrum") == 42161
    assert server.network_chain_id("eth") == 1
    assert server.network_chain_id("base") == 8453
    assert server.network_chain_id("thronos") is None
    assert server.network_chain_id("btc") is None


# ---------------------------------------------------------------------------
# Dry-run scanner: per-wallet collision detection
# ---------------------------------------------------------------------------

def test_dry_run_reports_per_wallet_collisions(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        direction="in",
        external_txid="0xdryrun_tx",
        log_index=0,
        token_standard="BEP20",
    )
    server.add_wallet_history_event(thr_address="THR_A", **common)
    server.add_wallet_history_event(thr_address="THR_B", **common)

    history = _load(hfile)
    assert len(history) == 2

    report = server.history_dedupe_dry_run()
    assert report["total"] == 2
    assert report["with_canonical_id"] == 2
    assert len(report["collisions"]) == 0, (
        "Two different wallets sharing canonical_id is NOT a collision"
    )


def test_dry_run_detects_reconciliation_flags(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    server.add_wallet_history_event(
        thr_address="THR_RECON",
        event_type="evm_token_receive",
        chain="bsc",
        asset="USDT",
        amount=100.0,
        direction="in",
        external_txid="0xrecon_tx",
        log_index=None,
        token_standard="BEP20",
    )

    report = server.history_dedupe_dry_run()
    assert len(report["needs_reconciliation"]) == 1
    assert report["needs_reconciliation"][0]["thr_address"] == "THR_RECON"


# ---------------------------------------------------------------------------
# Chain alias dedupe: "bnb" and "bsc" are the same chain
# ---------------------------------------------------------------------------

def test_chain_alias_dedup(monkeypatch, tmp_path):
    hfile = _empty_history(monkeypatch, tmp_path)

    common = dict(
        thr_address="THR_LOU",
        event_type="evm_token_receive",
        asset="USDT",
        amount=50.0,
        direction="in",
        external_txid="0xaliascheck",
        log_index=0,
        token_standard="BEP20",
    )
    server.add_wallet_history_event(chain="bnb", **common)
    server.add_wallet_history_event(chain="bsc", **common)

    history = _load(hfile)
    assert len(history) == 1
    assert history[0]["chain"] == "bsc"
