"""
Tests for cross-chain incoming history pipeline.

Covers:
  - Chain-aware event ID generation
  - Chain-aware dedup key generation
  - ERC-20 transfer log parsing
  - Transfer event building
  - Bridge event correlation
  - Transfer reconciliation
  - Filter/new-transfer detection
  - Scan state management
  - Explorer URL generation
  - Edge cases (zero amount, missing fields, duplicate logs)
"""

import json
import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from crosschain_history import (
    CHAIN_CONFIG,
    ERC20_TRANSFER_TOPIC,
    build_transfer_event,
    correlate_bridge_events,
    filter_new_transfers,
    get_explorer_url,
    load_scan_state,
    make_chain_aware_dedup_key,
    make_chain_aware_event_id,
    parse_erc20_transfer_log,
    reconcile_transfers,
    save_scan_state,
    should_scan,
    _bridge_pair_status,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_erc20_log():
    usdt_contract = "0x55d398326f99059ff775485246999027b3197955"
    from_addr = "0x" + "a1" * 20
    to_addr = "0x" + "b2" * 20
    amount_raw = 100 * (10 ** 18)
    return {
        "address": usdt_contract,
        "topics": [
            ERC20_TRANSFER_TOPIC,
            "0x" + "00" * 12 + "a1" * 20,
            "0x" + "00" * 12 + "b2" * 20,
        ],
        "data": hex(amount_raw),
        "transactionHash": "0x" + "cc" * 32,
        "logIndex": "0x1",
        "blockNumber": "0x100",
    }


@pytest.fixture
def sample_parsed_transfer():
    return {
        "chain": "bsc",
        "from_addr": "0x" + "a1" * 20,
        "to_addr": "0x" + "b2" * 20,
        "contract": "0x55d398326f99059ff775485246999027b3197955",
        "symbol": "USDT",
        "decimals": 18,
        "standard": "BEP20",
        "amount": 100.0,
        "tx_hash": "0x" + "cc" * 32,
        "log_index": 1,
        "block_number": 256,
    }


@pytest.fixture
def tmp_state_file(tmp_path):
    return str(tmp_path / "crosschain_state.json")


# ── 1. Chain-aware event ID ───────────────────────────────────────────

class TestChainAwareEventId:
    def test_deterministic(self):
        id1 = make_chain_aware_event_id("bsc", "0xabc", 1, "THR123")
        id2 = make_chain_aware_event_id("bsc", "0xabc", 1, "THR123")
        assert id1 == id2

    def test_prefix(self):
        eid = make_chain_aware_event_id("bsc", "0xabc", 1, "THR123")
        assert eid.startswith("xc_")

    def test_different_chains_differ(self):
        id_bsc = make_chain_aware_event_id("bsc", "0xabc", 1, "THR123")
        id_base = make_chain_aware_event_id("base", "0xabc", 1, "THR123")
        assert id_bsc != id_base

    def test_different_log_index_differ(self):
        id1 = make_chain_aware_event_id("bsc", "0xabc", 0, "THR123")
        id2 = make_chain_aware_event_id("bsc", "0xabc", 1, "THR123")
        assert id1 != id2

    def test_different_address_differ(self):
        id1 = make_chain_aware_event_id("bsc", "0xabc", 1, "THR111")
        id2 = make_chain_aware_event_id("bsc", "0xabc", 1, "THR222")
        assert id1 != id2


# ── 2. Chain-aware dedup key ──────────────────────────────────────────

class TestChainAwareDedupKey:
    def test_with_external_txid(self):
        key = make_chain_aware_dedup_key(
            "token_receive", "bsc", 1234.0, 50.0, external_txid="0xabc"
        )
        assert key == "bsc:0xabc"

    def test_without_external_txid(self):
        key = make_chain_aware_dedup_key(
            "token_receive", "bsc", 1234.0, 50.0
        )
        assert "bsc:" in key
        assert "token_receive" in key

    def test_different_chains_different_keys(self):
        key_bsc = make_chain_aware_dedup_key("token_receive", "bsc", 1234.0, 50.0)
        key_base = make_chain_aware_dedup_key("token_receive", "base", 1234.0, 50.0)
        assert key_bsc != key_base

    def test_same_event_same_key(self):
        k1 = make_chain_aware_dedup_key("token_receive", "bsc", 1234.0, 50.0)
        k2 = make_chain_aware_dedup_key("token_receive", "bsc", 1234.0, 50.0)
        assert k1 == k2

    def test_unknown_chain_default(self):
        key = make_chain_aware_dedup_key("token_receive", "", 1234.0, 50.0)
        assert key.startswith("unknown:")


# ── 3. ERC-20 transfer log parsing ───────────────────────────────────

class TestParseErc20TransferLog:
    def test_valid_bsc_usdt(self, sample_erc20_log):
        result = parse_erc20_transfer_log(sample_erc20_log, "bsc")
        assert result is not None
        assert result["symbol"] == "USDT"
        assert result["chain"] == "bsc"
        assert result["amount"] == 100.0
        assert result["standard"] == "BEP20"
        assert result["decimals"] == 18

    def test_wrong_topic(self, sample_erc20_log):
        sample_erc20_log["topics"][0] = "0x" + "00" * 32
        assert parse_erc20_transfer_log(sample_erc20_log, "bsc") is None

    def test_too_few_topics(self, sample_erc20_log):
        sample_erc20_log["topics"] = [ERC20_TRANSFER_TOPIC]
        assert parse_erc20_transfer_log(sample_erc20_log, "bsc") is None

    def test_unknown_contract(self, sample_erc20_log):
        sample_erc20_log["address"] = "0x" + "ff" * 20
        assert parse_erc20_transfer_log(sample_erc20_log, "bsc") is None

    def test_zero_amount(self, sample_erc20_log):
        sample_erc20_log["data"] = "0x0"
        assert parse_erc20_transfer_log(sample_erc20_log, "bsc") is None

    def test_base_usdc(self):
        usdc_contract = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
        amount_raw = 500 * (10 ** 6)
        log = {
            "address": usdc_contract,
            "topics": [
                ERC20_TRANSFER_TOPIC,
                "0x" + "00" * 12 + "a1" * 20,
                "0x" + "00" * 12 + "b2" * 20,
            ],
            "data": hex(amount_raw),
            "transactionHash": "0x" + "dd" * 32,
            "logIndex": "0x0",
            "blockNumber": "0x200",
        }
        result = parse_erc20_transfer_log(log, "base")
        assert result is not None
        assert result["symbol"] == "USDC"
        assert result["decimals"] == 6
        assert result["amount"] == 500.0
        assert result["standard"] == "ERC20"

    def test_arbitrum_usdt(self):
        usdt_arb = "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"
        amount_raw = 1000 * (10 ** 6)
        log = {
            "address": usdt_arb,
            "topics": [
                ERC20_TRANSFER_TOPIC,
                "0x" + "00" * 12 + "a1" * 20,
                "0x" + "00" * 12 + "b2" * 20,
            ],
            "data": hex(amount_raw),
            "transactionHash": "0x" + "ee" * 32,
            "logIndex": "0x3",
            "blockNumber": "0x500",
        }
        result = parse_erc20_transfer_log(log, "arbitrum")
        assert result is not None
        assert result["symbol"] == "USDT"
        assert result["decimals"] == 6
        assert result["amount"] == 1000.0

    def test_extracts_addresses(self, sample_erc20_log):
        result = parse_erc20_transfer_log(sample_erc20_log, "bsc")
        assert result["from_addr"] == "0x" + "a1" * 20
        assert result["to_addr"] == "0x" + "b2" * 20

    def test_extracts_tx_hash(self, sample_erc20_log):
        result = parse_erc20_transfer_log(sample_erc20_log, "bsc")
        assert result["tx_hash"] == "0x" + "cc" * 32

    def test_extracts_block_number(self, sample_erc20_log):
        result = parse_erc20_transfer_log(sample_erc20_log, "bsc")
        assert result["block_number"] == 256


# ── 4. Transfer event building ────────────────────────────────────────

class TestBuildTransferEvent:
    def test_basic_structure(self, sample_parsed_transfer):
        ev = build_transfer_event(sample_parsed_transfer, "THRABC123")
        assert ev["thr_address"] == "THRABC123"
        assert ev["event_type"] == "crosschain_transfer_received"
        assert ev["chain"] == "bsc"
        assert ev["asset"] == "USDT"
        assert ev["amount"] == 100.0
        assert ev["direction"] == "in"
        assert ev["status"] == "confirmed"
        assert ev["id"].startswith("xc_")

    def test_has_explorer_url(self, sample_parsed_transfer):
        ev = build_transfer_event(sample_parsed_transfer, "THRABC123")
        assert ev["explorer_url"] is not None
        assert "bscscan.com" in ev["explorer_url"]

    def test_has_transfer_scope(self, sample_parsed_transfer):
        ev = build_transfer_event(sample_parsed_transfer, "THRABC123")
        assert ev["transfer_scope"] == "cross_chain"
        assert ev["asset_origin_chain"] == "bsc"

    def test_has_timestamp(self, sample_parsed_transfer):
        ev = build_transfer_event(sample_parsed_transfer, "THRABC123")
        assert ev["timestamp"] > 0
        assert "created_at" in ev


# ── 5. Bridge event correlation ───────────────────────────────────────

class TestBridgeCorrelation:
    def test_matched_pair(self):
        events = [
            {"event_type": "bridge_in", "bridge_id": "BR1", "amount": 1.0},
            {"event_type": "bridge_out", "bridge_id": "BR1", "amount": 1.0},
        ]
        corr = correlate_bridge_events(events)
        assert len(corr) == 1
        assert corr[0]["status"] == "completed"
        assert corr[0]["bridge_in"] is not None
        assert corr[0]["bridge_out"] is not None

    def test_pending_out(self):
        events = [
            {"event_type": "bridge_in", "bridge_id": "BR2", "amount": 0.5},
        ]
        corr = correlate_bridge_events(events)
        assert len(corr) == 1
        assert corr[0]["status"] == "pending_out"

    def test_pending_in(self):
        events = [
            {"event_type": "bridge_out", "bridge_id": "BR3", "amount": 0.5},
        ]
        corr = correlate_bridge_events(events)
        assert len(corr) == 1
        assert corr[0]["status"] == "pending_in"

    def test_empty_events(self):
        assert correlate_bridge_events([]) == []

    def test_no_bridge_id(self):
        events = [
            {"event_type": "bridge_in", "amount": 1.0},
            {"event_type": "bridge_out", "amount": 1.0},
        ]
        assert correlate_bridge_events(events) == []

    def test_multiple_bridges(self):
        events = [
            {"event_type": "bridge_in", "bridge_id": "BR1", "amount": 1.0},
            {"event_type": "bridge_out", "bridge_id": "BR1", "amount": 1.0},
            {"event_type": "bridge_in", "bridge_id": "BR2", "amount": 2.0},
        ]
        corr = correlate_bridge_events(events)
        assert len(corr) == 2
        statuses = {c["bridge_id"]: c["status"] for c in corr}
        assert statuses["BR1"] == "completed"
        assert statuses["BR2"] == "pending_out"

    def test_crosschain_transfer_as_bridge_in(self):
        events = [
            {"event_type": "crosschain_transfer_received", "correlation_id": "BR4"},
            {"event_type": "bridge_out", "bridge_id": "BR4"},
        ]
        corr = correlate_bridge_events(events)
        assert len(corr) == 1
        assert corr[0]["status"] == "completed"


# ── 6. Bridge pair status helper ──────────────────────────────────────

class TestBridgePairStatus:
    def test_completed(self):
        assert _bridge_pair_status({"a": 1}, {"b": 2}) == "completed"

    def test_pending_out(self):
        assert _bridge_pair_status({"a": 1}, None) == "pending_out"

    def test_pending_in(self):
        assert _bridge_pair_status(None, {"b": 2}) == "pending_in"

    def test_unknown(self):
        assert _bridge_pair_status(None, None) == "unknown"


# ── 7. Reconciliation ────────────────────────────────────────────────

class TestReconciliation:
    def test_fully_reconciled(self):
        wallet = [{"chain": "bsc", "external_txid": "0xabc"}]
        onchain = [{"chain": "bsc", "tx_hash": "0xabc"}]
        r = reconcile_transfers(wallet, onchain)
        assert r["is_reconciled"] is True
        assert r["matched"] == 1
        assert r["missing_from_history"] == []

    def test_missing_from_history(self):
        wallet = []
        onchain = [{"chain": "bsc", "tx_hash": "0xabc"}]
        r = reconcile_transfers(wallet, onchain)
        assert r["is_reconciled"] is False
        assert "bsc:0xabc" in r["missing_from_history"]

    def test_orphaned_in_history(self):
        wallet = [{"chain": "bsc", "external_txid": "0xorphan"}]
        onchain = []
        r = reconcile_transfers(wallet, onchain)
        assert r["is_reconciled"] is True
        assert "bsc:0xorphan" in r["orphaned_in_history"]

    def test_empty_inputs(self):
        r = reconcile_transfers([], [])
        assert r["is_reconciled"] is True
        assert r["matched"] == 0

    def test_case_insensitive(self):
        wallet = [{"chain": "BSC", "external_txid": "0xABC"}]
        onchain = [{"chain": "bsc", "tx_hash": "0xabc"}]
        r = reconcile_transfers(wallet, onchain)
        assert r["is_reconciled"] is True

    def test_multiple_chains(self):
        wallet = [
            {"chain": "bsc", "external_txid": "0xaaa"},
            {"chain": "base", "external_txid": "0xbbb"},
        ]
        onchain = [
            {"chain": "bsc", "tx_hash": "0xaaa"},
            {"chain": "base", "tx_hash": "0xbbb"},
            {"chain": "arbitrum", "tx_hash": "0xccc"},
        ]
        r = reconcile_transfers(wallet, onchain)
        assert r["matched"] == 2
        assert "arbitrum:0xccc" in r["missing_from_history"]


# ── 8. Filter new transfers ──────────────────────────────────────────

class TestFilterNewTransfers:
    def test_all_new(self, sample_parsed_transfer):
        result = filter_new_transfers([sample_parsed_transfer], set(), "THRABC")
        assert len(result) == 1

    def test_already_seen(self, sample_parsed_transfer):
        eid = make_chain_aware_event_id(
            "bsc", sample_parsed_transfer["tx_hash"],
            sample_parsed_transfer["log_index"], "THRABC"
        )
        result = filter_new_transfers([sample_parsed_transfer], {eid}, "THRABC")
        assert len(result) == 0

    def test_mixed(self, sample_parsed_transfer):
        eid = make_chain_aware_event_id(
            "bsc", sample_parsed_transfer["tx_hash"],
            sample_parsed_transfer["log_index"], "THRABC"
        )
        new_transfer = dict(sample_parsed_transfer, tx_hash="0x" + "dd" * 32, log_index=5)
        result = filter_new_transfers(
            [sample_parsed_transfer, new_transfer], {eid}, "THRABC"
        )
        assert len(result) == 1
        assert result[0]["tx_hash"] == "0x" + "dd" * 32


# ── 9. Scan state persistence ────────────────────────────────────────

class TestScanState:
    def test_load_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "crosschain_history.CROSSCHAIN_HISTORY_FILE",
            str(tmp_path / "nonexistent.json"),
        )
        state = load_scan_state()
        assert state["last_scan_ts"] == 0

    def test_save_and_load(self, tmp_path, monkeypatch):
        path = str(tmp_path / "state.json")
        monkeypatch.setattr("crosschain_history.CROSSCHAIN_HISTORY_FILE", path)
        save_scan_state({"last_scan_ts": 12345, "chain_cursors": {"bsc": 100}})
        loaded = load_scan_state()
        assert loaded["last_scan_ts"] == 12345
        assert loaded["chain_cursors"]["bsc"] == 100

    def test_should_scan_disabled(self, monkeypatch):
        monkeypatch.setattr("crosschain_history.ENABLED", False)
        assert should_scan({"last_scan_ts": 0}) is False

    def test_should_scan_enabled_interval_passed(self, monkeypatch):
        monkeypatch.setattr("crosschain_history.ENABLED", True)
        monkeypatch.setattr("crosschain_history.SCAN_INTERVAL_SEC", 60)
        assert should_scan({"last_scan_ts": time.time() - 120}) is True

    def test_should_scan_enabled_interval_not_passed(self, monkeypatch):
        monkeypatch.setattr("crosschain_history.ENABLED", True)
        monkeypatch.setattr("crosschain_history.SCAN_INTERVAL_SEC", 600)
        assert should_scan({"last_scan_ts": time.time() - 10}) is False


# ── 10. Explorer URL generation ───────────────────────────────────────

class TestExplorerUrl:
    def test_bsc(self):
        url = get_explorer_url("bsc", "0xabc")
        assert "bscscan.com/tx/0xabc" in url

    def test_base(self):
        url = get_explorer_url("base", "0xdef")
        assert "basescan.org/tx/0xdef" in url

    def test_arbitrum(self):
        url = get_explorer_url("arbitrum", "0x123")
        assert "arbiscan.io/tx/0x123" in url

    def test_eth(self):
        url = get_explorer_url("eth", "0x456")
        assert "etherscan.io/tx/0x456" in url

    def test_unknown_chain(self):
        assert get_explorer_url("solana", "0xabc") is None

    def test_empty_txhash(self):
        assert get_explorer_url("bsc", "") is None


# ── 11. Chain config integrity ────────────────────────────────────────

class TestChainConfig:
    def test_all_chains_have_rpc(self):
        for chain, cfg in CHAIN_CONFIG.items():
            assert "rpc" in cfg, f"{chain} missing rpc"

    def test_all_chains_have_explorer(self):
        for chain, cfg in CHAIN_CONFIG.items():
            assert "explorer_tx" in cfg, f"{chain} missing explorer_tx"

    def test_bsc_usdt_config(self):
        bsc = CHAIN_CONFIG["bsc"]
        usdt = bsc["tokens"].get("0x55d398326f99059ff775485246999027b3197955")
        assert usdt is not None
        assert usdt["symbol"] == "USDT"
        assert usdt["decimals"] == 18

    def test_base_usdc_config(self):
        base = CHAIN_CONFIG["base"]
        usdc = base["tokens"].get("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")
        assert usdc is not None
        assert usdc["symbol"] == "USDC"
        assert usdc["decimals"] == 6


# ── 12. Edge cases ───────────────────────────────────────────────────

class TestEdgeCases:
    def test_dedup_key_zero_amount(self):
        key = make_chain_aware_dedup_key("token_receive", "bsc", 0.0, 0.0)
        assert "bsc:" in key

    def test_dedup_key_none_chain(self):
        key = make_chain_aware_dedup_key("token_receive", None, 1234.0, 50.0)
        assert key.startswith("unknown:")

    def test_parse_log_hex_block_number(self):
        log = {
            "address": "0x55d398326f99059ff775485246999027b3197955",
            "topics": [
                ERC20_TRANSFER_TOPIC,
                "0x" + "00" * 12 + "a1" * 20,
                "0x" + "00" * 12 + "b2" * 20,
            ],
            "data": hex(10 * (10 ** 18)),
            "transactionHash": "0x" + "ff" * 32,
            "logIndex": "0xa",
            "blockNumber": "0xff",
        }
        result = parse_erc20_transfer_log(log, "bsc")
        assert result["log_index"] == 10
        assert result["block_number"] == 255

    def test_build_event_preserves_external_from(self, sample_parsed_transfer):
        ev = build_transfer_event(sample_parsed_transfer, "THRXYZ")
        assert ev["external_from"] == sample_parsed_transfer["from_addr"]
        assert ev["external_to"] == sample_parsed_transfer["to_addr"]

    def test_reconcile_missing_fields(self):
        wallet = [{"chain": "", "external_txid": ""}]
        onchain = [{"chain": "", "tx_hash": ""}]
        r = reconcile_transfers(wallet, onchain)
        assert r["matched"] == 0
