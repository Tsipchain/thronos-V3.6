from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest

from services.btc_settlement_accounting import (
    BRIDGE_DEPOSIT_ACCOUNTING,
    BRIDGE_PLEDGE_ELIGIBILITY,
    EARN_RESERVE_SETTLEMENT,
    BtcAccountingError,
    BtcSettlementAccountingStore,
    CanonicalSettlementCommand,
)


TXID = "11" * 32
KEY = f"main:{TXID}:0"
COMMAND_ID = f"btc-settle:{KEY}"


def command(**changes):
    raw = {
        "command_id": COMMAND_ID,
        "idempotency_key": KEY,
        "event_id": KEY,
        "network": "main",
        "txid": TXID,
        "vout": 0,
        "owner_ref": "bridge-intent-42",
        "amount_sats": 12_345,
        "proof_ref": "btcp_" + "44" * 32,
        "purpose": BRIDGE_DEPOSIT_ACCOUNTING,
        "registry_version": "registry-v7",
    }
    raw.update(changes)
    return CanonicalSettlementCommand.from_mapping(raw)


def test_accounting_is_default_disabled(tmp_path):
    store = BtcSettlementAccountingStore(str(tmp_path / "accounting.db"))
    with pytest.raises(BtcAccountingError, match="btc_accounting_disabled"):
        store.consume(command())
    assert store.ledger_entry(COMMAND_ID) is None


def test_atomic_bridge_accounting_creates_inbox_ledger_and_audit(tmp_path):
    store = BtcSettlementAccountingStore(
        str(tmp_path / "accounting.db"), enabled=True, now_fn=lambda: 1_800_000_000
    )
    receipt = store.consume(command())

    assert receipt.command_id == COMMAND_ID
    assert receipt.idempotency_key == KEY
    assert receipt.state == "applied"
    assert receipt.accounting_receipt_ref.startswith("btcar_")
    ledger = store.ledger_entry(COMMAND_ID)
    assert ledger["event_id"] == KEY
    assert ledger["amount_sats"] == 12_345
    assert ledger["purpose"] == BRIDGE_DEPOSIT_ACCOUNTING
    assert ledger["state"] == "accounted"
    assert store.eligibility_evidence(COMMAND_ID) is None
    assert [row["event_type"] for row in store.audit(COMMAND_ID)] == [
        "accounting_applied"
    ]


def test_wallet_pledge_creates_evidence_but_does_not_activate_wallet(tmp_path):
    store = BtcSettlementAccountingStore(
        str(tmp_path / "accounting.db"), enabled=True
    )
    store.consume(command(purpose=BRIDGE_PLEDGE_ELIGIBILITY))

    evidence = store.eligibility_evidence(COMMAND_ID)
    assert evidence["owner_ref"] == "bridge-intent-42"
    assert evidence["state"] == "verified"
    tables = set()
    with sqlite3.connect(store.db_path) as con:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "ledger" not in tables
    assert "wallets" not in tables


def test_earn_reserve_is_btc_accounting_only(tmp_path):
    store = BtcSettlementAccountingStore(
        str(tmp_path / "accounting.db"), enabled=True
    )
    store.consume(command(purpose=EARN_RESERVE_SETTLEMENT))
    assert store.ledger_entry(COMMAND_ID)["purpose"] == EARN_RESERVE_SETTLEMENT
    assert store.eligibility_evidence(COMMAND_ID) is None


def test_exact_replay_returns_same_receipt_without_duplicate_entry(tmp_path):
    store = BtcSettlementAccountingStore(
        str(tmp_path / "accounting.db"), enabled=True
    )
    first = store.consume(command())
    second = store.consume(command())
    assert first == second
    with sqlite3.connect(store.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM btc_accounting_inbox").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM btc_accounting_ledger").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM btc_accounting_audit").fetchone()[0] == 1


def test_concurrent_duplicate_consumption_is_deterministic(tmp_path):
    path = str(tmp_path / "accounting.db")
    BtcSettlementAccountingStore(path, enabled=True)

    def consume(_index):
        return BtcSettlementAccountingStore(path, enabled=True).consume(command())

    with ThreadPoolExecutor(max_workers=16) as pool:
        receipts = list(pool.map(consume, range(32)))
    assert len({item.accounting_receipt_ref for item in receipts}) == 1
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM btc_accounting_ledger").fetchone()[0] == 1


def test_conflicting_replay_fails_closed(tmp_path):
    store = BtcSettlementAccountingStore(
        str(tmp_path / "accounting.db"), enabled=True
    )
    store.consume(command())
    with pytest.raises(BtcAccountingError, match="idempotency_conflict"):
        store.consume(command(amount_sats=12_346))
    assert store.ledger_entry(COMMAND_ID)["amount_sats"] == 12_345


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"network": "test"}, "canonical_identity_mismatch"),
        ({"vout": -1}, "vout_invalid"),
        ({"amount_sats": 0}, "amount_invalid"),
        ({"command_id": "wrong"}, "command_id_mismatch"),
        ({"purpose": "earn_cashout"}, "purpose_not_inbound"),
        ({"proof_ref": "unverified"}, "proof_ref_invalid"),
    ],
)
def test_invalid_command_boundaries_fail_closed(changes, error):
    with pytest.raises(BtcAccountingError, match=error):
        command(**changes)


def test_transaction_rolls_back_when_audit_write_fails(tmp_path):
    path = str(tmp_path / "accounting.db")
    store = BtcSettlementAccountingStore(path, enabled=True)
    with sqlite3.connect(path) as con:
        con.execute(
            """CREATE TRIGGER fail_accounting_audit
               BEFORE INSERT ON btc_accounting_audit
               BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="synthetic audit failure"):
        store.consume(command())
    assert store.ledger_entry(COMMAND_ID) is None
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM btc_accounting_inbox").fetchone()[0] == 0
    with sqlite3.connect(path) as con:
        con.execute("DROP TRIGGER fail_accounting_audit")
    assert store.consume(command()).state == "applied"


def test_restart_preserves_receipt_and_replay_idempotency(tmp_path):
    path = str(tmp_path / "accounting.db")
    first_store = BtcSettlementAccountingStore(path, enabled=True)
    first = first_store.consume(command())
    reopened = BtcSettlementAccountingStore(path, enabled=True)
    assert reopened.consume(command()) == first
    assert reopened.ledger_entry(COMMAND_ID)["amount_sats"] == 12_345


def test_reorg_holds_original_entry_without_rewriting_or_deleting_it(tmp_path):
    store = BtcSettlementAccountingStore(
        str(tmp_path / "accounting.db"), enabled=True
    )
    original = store.consume(command(purpose=BRIDGE_PLEDGE_ELIGIBILITY))
    held = store.hold_for_reorg(COMMAND_ID, reason="canonical_block_removed")

    assert held.accounting_receipt_ref == original.accounting_receipt_ref
    assert held.state == "held"
    ledger = store.ledger_entry(COMMAND_ID)
    assert ledger["amount_sats"] == 12_345
    assert ledger["state"] == "held"
    assert store.eligibility_evidence(COMMAND_ID)["state"] == "held"
    assert [row["event_type"] for row in store.audit(COMMAND_ID)] == [
        "accounting_applied",
        "reorg_hold",
    ]
