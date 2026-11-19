import json
from pathlib import Path
import sqlite3

import pytest

from services.btc_deposit_outbox import BtcDepositOutbox
from services.btc_node_agent import LocalBitcoinNodeAgent, NodeAgentError, load_watch_registry
from services.btc_observer import BtcObserverStore
from services.btc_provider_revenue import (
    CONFIRMATION_PENDING,
    CONFLICT,
    MATCHED,
    OBSERVATION_PENDING,
    PURPOSE,
    REORG_REVIEW,
    REVENUE_ADDRESS,
    ProviderRevenueError,
    ProviderRevenueStore,
    MAINNET_GENESIS_HASH,
)


TXID = "11" * 32
TXID_2 = "22" * 32
BLOCK = "aa" * 32
BLOCK_2 = "bb" * 32
GENESIS = "00" * 31 + "01"


def _statement(store: ProviderRevenueStore, *, provider="cpx", txid=TXID, sats=125000):
    return store.record_statement(
        provider=provider,
        statement_id=f"{provider}-statement-2026-11",
        txid=txid,
        vout=1,
        expected_sats=sats,
        period_ref="2026-11",
        recorded_at=100,
    )


def _observe(
    observer: BtcObserverStore,
    *,
    txid=TXID,
    sats=125000,
    confirmations=6,
    block_hash=BLOCK,
    observed_at=200,
):
    return observer.upsert(
        txid=txid,
        vout=1,
        address=REVENUE_ADDRESS,
        owner_ref=PURPOSE,
        amount_sats=sats,
        confirmations=confirmations,
        block_hash=block_hash,
        block_height=900000 if block_hash else None,
        minimum_confirmations=6,
        observed_at=observed_at,
    )


def test_statement_requires_explicit_txid_vout_and_never_infers_provider(tmp_path):
    path = str(tmp_path / "observer.db")
    BtcObserverStore(path)
    revenue = ProviderRevenueStore(path)
    statement = _statement(revenue)

    assert statement.idempotency_key == f"main:{TXID}:1"
    result = revenue.reconcile(statement.idempotency_key, reviewed_at=101)
    assert result["status"] == OBSERVATION_PENDING
    assert result["credit_authorized"] is False
    assert result["delivery_authorized"] is False


def test_exact_integer_satoshi_and_six_confirmation_match(tmp_path):
    path = str(tmp_path / "observer.db")
    observer = BtcObserverStore(path)
    revenue = ProviderRevenueStore(path)
    statement = _statement(revenue)

    _observe(observer, confirmations=5)
    pending = revenue.reconcile(statement.idempotency_key, reviewed_at=201)
    assert pending["status"] == CONFIRMATION_PENDING

    _observe(observer, confirmations=6, observed_at=202)
    matched = revenue.reconcile(statement.idempotency_key, reviewed_at=203)
    assert matched["status"] == MATCHED
    assert matched["expected_sats"] == 125000
    assert matched["observed_sats"] == 125000
    assert matched["confirmations"] == 6


def test_duplicate_statement_is_idempotent_and_conflict_fails_closed(tmp_path):
    path = str(tmp_path / "observer.db")
    BtcObserverStore(path)
    revenue = ProviderRevenueStore(path)
    first = _statement(revenue)
    duplicate = _statement(revenue)
    assert duplicate == first

    with pytest.raises(ProviderRevenueError, match="identity_conflict"):
        _statement(revenue, sats=125001)


def test_amount_mismatch_is_conflict_not_credit(tmp_path):
    path = str(tmp_path / "observer.db")
    observer = BtcObserverStore(path)
    revenue = ProviderRevenueStore(path)
    statement = _statement(revenue)
    _observe(observer, sats=124999)

    result = revenue.reconcile(statement.idempotency_key)
    assert result["status"] == CONFLICT
    assert result["credit_authorized"] is False


def test_reorg_after_match_is_durably_flagged(tmp_path):
    path = str(tmp_path / "observer.db")
    observer = BtcObserverStore(path)
    revenue = ProviderRevenueStore(path)
    statement = _statement(revenue)
    _observe(observer)
    assert revenue.reconcile(statement.idempotency_key, reviewed_at=201)["status"] == MATCHED

    _observe(observer, block_hash=BLOCK_2, observed_at=202)
    reorged = revenue.reconcile(statement.idempotency_key, reviewed_at=203)
    assert reorged["status"] == REORG_REVIEW

    restarted = ProviderRevenueStore(path)
    report = restarted.read_only_report()
    assert report["counts"] == {REORG_REVIEW: 1}
    assert report["credits_applied"] == 0
    assert report["delivery_enabled"] is False


def test_provider_revenue_is_never_enqueued_to_deposit_adapter(tmp_path):
    path = str(tmp_path / "observer.db")
    observer = BtcObserverStore(path)
    ProviderRevenueStore(path)
    _observe(observer)
    observer.upsert(
        txid=TXID_2,
        vout=0,
        address="bc1qbridgeaddress000000000000000000000000000",
        owner_ref="bridge_deposit_accounting",
        amount_sats=50000,
        confirmations=6,
        block_hash=BLOCK,
        block_height=900000,
        minimum_confirmations=6,
        observed_at=200,
    )
    outbox = BtcDepositOutbox(path, network="main", genesis_hash=GENESIS)

    assert outbox.enqueue_confirmed(minimum_confirmations=6) == 1
    item = outbox.claim_next()
    assert item is not None
    assert item.idempotency_key == f"main:{TXID_2}:0"
    assert item.payload["owner_ref"] == "bridge_deposit_accounting"
    assert PURPOSE not in json.dumps(item.payload)


def test_preexisting_outbox_row_cannot_be_claimed_after_purpose_is_revenue(tmp_path):
    path = str(tmp_path / "observer.db")
    observer = BtcObserverStore(path)
    observer.upsert(
        txid=TXID,
        vout=0,
        address=REVENUE_ADDRESS,
        owner_ref="bridge_deposit_accounting",
        amount_sats=50000,
        confirmations=6,
        block_hash=BLOCK,
        block_height=900000,
        minimum_confirmations=6,
        observed_at=200,
    )
    outbox = BtcDepositOutbox(path, network="main", genesis_hash=GENESIS)
    assert outbox.enqueue_confirmed(minimum_confirmations=6) == 1
    with sqlite3.connect(path) as con:
        con.execute(
            "UPDATE btc_observer_deposits SET owner_ref=? WHERE event_id=?",
            (PURPOSE, f"{TXID}:0"),
        )
    assert outbox.claim_next() is None


def test_read_only_report_does_not_create_or_change_database_files(tmp_path):
    path = str(tmp_path / "observer.db")
    BtcObserverStore(path)
    revenue = ProviderRevenueStore(path)
    _statement(revenue)
    revenue.reconcile(f"main:{TXID}:1")
    before = {
        file.name: (file.stat().st_size, file.stat().st_mtime_ns)
        for file in tmp_path.iterdir()
    }

    report = ProviderRevenueStore.open_existing_readonly(path).read_only_report()

    after = {
        file.name: (file.stat().st_size, file.stat().st_mtime_ns)
        for file in tmp_path.iterdir()
    }
    assert report["purpose"] == PURPOSE
    assert before == after


def test_watch_registry_requires_exact_address_purpose_and_operator_verification(
    tmp_path, monkeypatch
):
    registry = tmp_path / "watch.json"
    registry.write_text(json.dumps({REVENUE_ADDRESS: PURPOSE}), encoding="utf-8")
    monkeypatch.delenv("BTC_PROVIDER_REVENUE_PAYOUT_CONFIG_VERIFIED", raising=False)
    with pytest.raises(NodeAgentError, match="payout_config_not_verified"):
        load_watch_registry(str(registry))

    monkeypatch.setenv("BTC_PROVIDER_REVENUE_PAYOUT_CONFIG_VERIFIED", "true")
    assert load_watch_registry(str(registry)) == {REVENUE_ADDRESS: PURPOSE}

    registry.write_text(json.dumps({REVENUE_ADDRESS: "bridge_deposit_accounting"}), encoding="utf-8")
    with pytest.raises(NodeAgentError, match="purpose_mismatch"):
        load_watch_registry(str(registry))

    registry.write_text(
        json.dumps({"1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": PURPOSE}),
        encoding="utf-8",
    )
    with pytest.raises(NodeAgentError, match="address_mismatch"):
        load_watch_registry(str(registry))


class _RevenueRpc:
    def __init__(self, genesis_hash):
        self.genesis_hash = genesis_hash

    def call(self, method, params):
        if method == "getblockchaininfo":
            return {
                "chain": "main",
                "blocks": 900000,
                "headers": 900000,
                "initialblockdownload": False,
                "pruned": False,
            }
        if method == "getblockhash" and params == [0]:
            return self.genesis_hash
        if method == "validateaddress":
            return {"isvalid": params == [REVENUE_ADDRESS]}
        raise AssertionError((method, params))


class _NoopAdapter:
    def push_tip(self, **_kwargs):
        raise AssertionError("not called")


def test_revenue_preflight_requires_exact_mainnet_genesis(tmp_path):
    agent = LocalBitcoinNodeAgent(
        db_path=str(tmp_path / "observer.db"),
        watch_registry={REVENUE_ADDRESS: PURPOSE},
        rpc=_RevenueRpc("00" * 32),
        adapter=_NoopAdapter(),
    )
    with pytest.raises(NodeAgentError, match="mainnet_genesis_mismatch"):
        agent.preflight()

    valid = LocalBitcoinNodeAgent(
        db_path=str(tmp_path / "observer-valid.db"),
        watch_registry={REVENUE_ADDRESS: PURPOSE},
        rpc=_RevenueRpc(MAINNET_GENESIS_HASH),
        adapter=_NoopAdapter(),
    )
    assert valid.preflight()["genesis_hash"] == MAINNET_GENESIS_HASH
