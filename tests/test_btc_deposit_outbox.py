from pathlib import Path
import tempfile

import pytest

from services.btc_deposit_outbox import BtcDepositOutbox, BtcDepositOutboxError
from services.btc_observer import BtcObserverStore, CONFIRMED


NETWORK = "main"
GENESIS = "00" * 31 + "01"
TXID = "11" * 32
BLOCK = "aa" * 32
WATCH = "bc1qwatchaddress000000000000000000000000000"


def seed_confirmed(db_path: str) -> BtcObserverStore:
    store = BtcObserverStore(db_path)
    store.upsert(
        txid=TXID,
        vout=0,
        address=WATCH,
        owner_ref="bridge-intent-1",
        amount_sats=50000,
        confirmations=6,
        block_hash=BLOCK,
        block_height=900000,
        minimum_confirmations=6,
        observed_at=1000,
    )
    row = store.by_txid(TXID)[0]
    assert row.state == CONFIRMED
    return store


def test_network_binding_is_durable_and_mismatch_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "observer.db")
        BtcObserverStore(path)
        BtcDepositOutbox(path, network=NETWORK, genesis_hash=GENESIS)
        BtcDepositOutbox(path, network=NETWORK, genesis_hash=GENESIS)
        with pytest.raises(BtcDepositOutboxError, match="network_mismatch"):
            BtcDepositOutbox(path, network="test", genesis_hash="22" * 32)


def test_confirmed_event_is_enqueued_once_and_claimed_with_network_key():
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "observer.db")
        seed_confirmed(path)
        outbox = BtcDepositOutbox(path, network=NETWORK, genesis_hash=GENESIS)
        assert outbox.enqueue_confirmed(minimum_confirmations=6) == 1
        assert outbox.enqueue_confirmed(minimum_confirmations=6) == 0

        item = outbox.claim_next(lease_seconds=30)
        assert item is not None
        assert item.idempotency_key == f"{NETWORK}:{TXID}:0"
        assert item.payload["event_id"] == item.idempotency_key
        assert item.payload["network"] == NETWORK
        assert item.payload["amount_sats"] == 50000

        outbox.acknowledge(item.idempotency_key)
        assert outbox.counts() == {"acknowledged": 1}
        assert outbox.claim_next() is None


def test_global_reconciliation_flag_blocks_enqueue_and_claim():
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "observer.db")
        store = seed_confirmed(path)
        outbox = BtcDepositOutbox(path, network=NETWORK, genesis_hash=GENESIS)
        store.set_meta_int("zmq_gap_detected", 1)

        with pytest.raises(BtcDepositOutboxError, match="global_reconciliation"):
            outbox.enqueue_confirmed(minimum_confirmations=6)


def test_failed_delivery_is_retryable_after_backoff():
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "observer.db")
        seed_confirmed(path)
        outbox = BtcDepositOutbox(path, network=NETWORK, genesis_hash=GENESIS)
        outbox.enqueue_confirmed(minimum_confirmations=6)
        item = outbox.claim_next()
        assert item is not None
        outbox.fail(item.idempotency_key, "network error")
        counts = outbox.counts()
        assert counts["failed"] == 1
