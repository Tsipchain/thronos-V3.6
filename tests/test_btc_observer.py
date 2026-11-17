
from pathlib import Path
import tempfile

import pytest

from services.btc_observer import (
    BtcObserver,
    BtcObserverError,
    BtcObserverStore,
    CONFIRMED,
    CONFIRMING,
    CREDITED,
    REORGED,
    SEEN,
)

TXID = "11" * 32
BLOCK_A = "aa" * 32
BLOCK_B = "bb" * 32
TIP = "cc" * 32
WATCH = "bc1qwatchaddress000000000000000000000000000"
OTHER = "bc1qother0000000000000000000000000000"


class FakeRpc:
    def __init__(self):
        self.tx = {
            "txid": TXID,
            "confirmations": 0,
            "vout": [
                {"n": 0, "value": "0.00100000", "scriptPubKey": {"address": WATCH}},
                {"n": 1, "value": "0.00000001", "scriptPubKey": {"address": WATCH}},
                {"n": 2, "value": "0.5", "scriptPubKey": {"address": OTHER}},
            ],
        }
        self.headers = {
            BLOCK_A: {"height": 900000},
            BLOCK_B: {"height": 900001},
        }
        self.tip_height = 900010
        self.tip_hash = TIP

    def call(self, method, params):
        if method == "getrawtransaction":
            return dict(self.tx)
        if method == "getblockheader":
            return self.headers[params[0]]
        if method == "getblockcount":
            return self.tip_height
        if method == "getblockhash":
            assert params == [self.tip_height]
            return self.tip_hash
        raise AssertionError((method, params))


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as td:
        yield BtcObserverStore(str(Path(td) / "observer.db"))


def observer(store, rpc, now=1000):
    return BtcObserver(
        rpc,
        store,
        {WATCH: "bridge-intent-123"},
        minimum_confirmations=3,
        now_fn=lambda: now,
    )


def test_tracks_each_matching_vout_and_exact_satoshis(store):
    rpc = FakeRpc()
    rows = observer(store, rpc).observe_transaction(TXID)
    assert [r.event_id for r in rows] == [f"{TXID}:0", f"{TXID}:1"]
    assert [r.amount_sats for r in rows] == [100000, 1]
    assert all(r.state == SEEN for r in rows)
    assert store.by_txid(TXID) == rows


def test_repeat_observation_is_idempotent(store):
    rpc = FakeRpc()
    obs = observer(store, rpc)
    first = obs.observe_transaction(TXID)
    second = obs.observe_transaction(TXID)
    assert len(store.by_txid(TXID)) == 2
    assert [r.event_id for r in first] == [r.event_id for r in second]


def test_confirmation_state_and_explicit_credit_gate(store):
    rpc = FakeRpc()
    obs = observer(store, rpc)
    row = obs.observe_transaction(TXID)[0]
    with pytest.raises(BtcObserverError, match="event_not_final"):
        store.mark_credited(row.event_id)

    rpc.tx["confirmations"] = 2
    rpc.tx["blockhash"] = BLOCK_A
    assert obs.observe_transaction(TXID)[0].state == CONFIRMING

    rpc.tx["confirmations"] = 3
    assert obs.observe_transaction(TXID)[0].state == CONFIRMED

    credited = store.mark_credited(row.event_id, credited_at=2000)
    assert credited.state == CREDITED
    assert credited.credited_at == 2000
    assert store.mark_credited(row.event_id, credited_at=3000).credited_at == 2000


def test_reorg_after_finality_requires_manual_reconciliation(store):
    rpc = FakeRpc()
    rpc.tx["confirmations"] = 3
    rpc.tx["blockhash"] = BLOCK_A
    obs = observer(store, rpc)
    event = obs.observe_transaction(TXID)[0]
    store.mark_credited(event.event_id, credited_at=2000)

    rpc.tx["confirmations"] = 1
    rpc.tx["blockhash"] = BLOCK_B
    reorged = obs.observe_transaction(TXID)[0]
    assert reorged.state == REORGED
    assert reorged.requires_reconciliation is True
    with pytest.raises(BtcObserverError, match="reconciliation_required"):
        store.mark_credited(event.event_id)


def test_identity_conflict_fails_closed(store):
    rpc = FakeRpc()
    obs = observer(store, rpc)
    obs.observe_transaction(TXID)
    rpc.tx["vout"][0]["value"] = "0.00200000"
    with pytest.raises(BtcObserverError, match="identity_conflict"):
        obs.observe_transaction(TXID)


def test_checkpoint_is_durable(store):
    rpc = FakeRpc()
    checkpoint = observer(store, rpc).checkpoint_tip()
    assert checkpoint == {
        "block_height": 900010,
        "block_hash": TIP,
        "observed_at": 1000,
    }
    assert store.checkpoint() == checkpoint


def test_invalid_sub_satoshi_amount_fails_closed(store):
    rpc = FakeRpc()
    rpc.tx["vout"][0]["value"] = "0.000000001"
    with pytest.raises(BtcObserverError, match="below_satoshi_precision"):
        observer(store, rpc).observe_transaction(TXID)
