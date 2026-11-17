from pathlib import Path
import tempfile

import pytest

from services.btc_node_agent import (
    LocalBitcoinNodeAgent,
    NodeAgentError,
    _https_adapter_url,
    _loopback_rpc_url,
)

TXID = "11" * 32
BLOCK = "aa" * 32
GENESIS = "00" * 31 + "01"
WATCH = "bc1qwatchaddress000000000000000000000000000"


class FakeRpc:
    def __init__(self):
        self.height = 976278
        self.block_hash = BLOCK
        self.decoded = {
            "txid": TXID,
            "vout": [
                {"n": 0, "value": "0.00100000", "scriptPubKey": {"address": WATCH}},
            ],
        }
        self.blocks = {
            self.height: {
                "hash": self.block_hash,
                "height": self.height,
                "tx": [dict(self.decoded)],
            }
        }
        self.zmq_notifications = [
            {"type": "pubhashblock", "address": "tcp://127.0.0.1:28332"},
            {"type": "pubrawtx", "address": "tcp://127.0.0.1:28333"},
            {"type": "pubsequence", "address": "tcp://127.0.0.1:28334"},
        ]

    def call(self, method, params):
        if method == "getblockchaininfo":
            return {
                "chain": "main",
                "blocks": self.height,
                "headers": self.height,
                "initialblockdownload": False,
                "pruned": True,
            }
        if method == "getblockcount":
            return self.height
        if method == "getblockhash":
            height = params[0]
            if height == 0:
                return GENESIS
            if height == self.height:
                return self.block_hash
            return f"{height:064x}"[-64:]
        if method == "decoderawtransaction":
            return dict(self.decoded)
        if method == "getrawtransaction":
            return dict(self.decoded)
        if method == "getblock":
            block_hash = params[0]
            if block_hash == self.block_hash:
                return dict(self.blocks[self.height])
            height = int(block_hash, 16)
            return {
                "hash": block_hash,
                "height": height,
                "tx": [],
            }
        if method == "getzmqnotifications":
            return list(self.zmq_notifications)
        if method == "validateaddress":
            return {"isvalid": params[0] == WATCH}
        raise AssertionError((method, params))


class FakeAdapter:
    def __init__(self):
        self.pushes = []
        self.deposits = []

    def push_tip(self, *, height, block_hash, sequence):
        self.pushes.append((height, block_hash, sequence))

    def push_deposit(self, payload):
        self.deposits.append(dict(payload))
        return "accepted"


@pytest.fixture()
def agent():
    with tempfile.TemporaryDirectory() as td:
        rpc = FakeRpc()
        adapter = FakeAdapter()
        instance = LocalBitcoinNodeAgent(
            db_path=str(Path(td) / "observer.db"),
            watch_registry={WATCH: "bridge-intent-1"},
            rpc=rpc,
            adapter=adapter,
            minimum_confirmations=3,
        )
        yield instance, rpc, adapter


def test_preflight_accepts_synced_pruned_mainnet(agent):
    instance, _rpc, _adapter = agent
    assert instance.preflight() == {
        "chain": "main",
        "genesis_hash": GENESIS,
        "blocks": 976278,
        "pruned": True,
        "synced": True,
    }
    assert instance.outbox is not None


def test_publish_tip_uses_durable_monotonic_sequence(agent):
    instance, _rpc, adapter = agent
    assert instance.publish_tip() == (976278, BLOCK, 1)
    assert instance.publish_tip() == (976278, BLOCK, 2)
    assert adapter.pushes == [
        (976278, BLOCK, 1),
        (976278, BLOCK, 2),
    ]


def test_rawtx_is_observed_without_txindex(agent):
    instance, _rpc, _adapter = agent
    assert instance.handle_rawtx(b"\x01\x02") == 1
    rows = instance.store.by_txid(TXID)
    assert len(rows) == 1
    assert rows[0].amount_sats == 100000
    assert rows[0].confirmations == 0


def test_new_block_reconciles_and_pushes_tip(agent):
    instance, _rpc, adapter = agent
    instance.handle_rawtx(b"\x01")
    matched, height, block_hash, sequence = instance.handle_new_block()
    assert matched == 1
    assert height == 976278
    assert block_hash == BLOCK
    assert sequence == 1
    row = instance.store.by_txid(TXID)[0]
    assert row.block_height == 976278
    assert row.confirmations == 1
    assert adapter.pushes[-1] == (976278, BLOCK, 1)


def test_remote_rpc_url_is_rejected():
    with pytest.raises(NodeAgentError, match="loopback"):
        _loopback_rpc_url("http://192.168.1.10:8332")


def test_public_adapter_requires_https():
    with pytest.raises(NodeAgentError, match="https"):
        _https_adapter_url("http://btc-api.thronoschain.org")


def test_sequence_remove_marks_seen_event_dropped(agent):
    instance, _rpc, _adapter = agent
    instance.handle_rawtx(b"\x01")
    body = bytes.fromhex(TXID) + b"R" + (77).to_bytes(8, "little")
    event = instance.handle_sequence(body)
    assert event["label"] == "R"
    row = instance.store.by_txid(TXID)[0]
    assert row.state == "dropped"


def test_sequence_add_recovers_watched_mempool_tx(agent):
    instance, _rpc, _adapter = agent
    body = bytes.fromhex(TXID) + b"A" + (78).to_bytes(8, "little")
    event = instance.handle_sequence(body)
    assert event["label"] == "A"
    assert event["changed"] == 1
    row = instance.store.by_txid(TXID)[0]
    assert row.state == "seen"


def test_zmq_message_sequence_gap_is_detected(agent):
    instance, _rpc, _adapter = agent
    assert instance._check_zmq_message_sequence(b"rawtx", (10).to_bytes(4, "little")) is False
    assert instance._check_zmq_message_sequence(b"rawtx", (11).to_bytes(4, "little")) is False
    assert instance._check_zmq_message_sequence(b"rawtx", (13).to_bytes(4, "little")) is True


def test_recover_from_checkpoint_backfills_missed_blocks(agent):
    instance, rpc, _adapter = agent
    old_height = rpc.height - 2
    old_hash = f"{old_height:064x}"[-64:]
    instance.store.save_checkpoint(old_height, old_hash, observed_at=1)

    blocks, matches = instance.recover_from_checkpoint()
    assert blocks == 2
    assert matches == 1


def test_recover_from_checkpoint_fails_closed_on_large_gap(agent, monkeypatch):
    instance, rpc, _adapter = agent
    old_height = rpc.height - 3
    old_hash = f"{old_height:064x}"[-64:]
    instance.store.save_checkpoint(old_height, old_hash, observed_at=1)
    monkeypatch.setenv("BTC_BACKFILL_MAX_BLOCKS", "2")

    with pytest.raises(NodeAgentError, match="gap_exceeds_backfill_limit"):
        instance.recover_from_checkpoint()
    assert instance.store.get_meta_int("observer_reconciliation_required") == 1


def test_sequence_rejects_invalid_body(agent):
    instance, _rpc, _adapter = agent
    with pytest.raises(NodeAgentError, match="invalid_zmq_sequence_body"):
        instance.handle_sequence(b"bad")



def test_preflight_rejects_wrong_network_watch_address():
    with tempfile.TemporaryDirectory() as td:
        rpc = FakeRpc()
        instance = LocalBitcoinNodeAgent(
            db_path=str(Path(td) / "observer.db"),
            watch_registry={"tb1qwrongnetwork000000000000000000000000000": "intent"},
            rpc=rpc,
            adapter=FakeAdapter(),
        )
        with pytest.raises(NodeAgentError, match="wrong_network_watch_address"):
            instance.preflight()


def test_heartbeat_does_not_advance_observer_checkpoint(agent):
    instance, rpc, _adapter = agent
    instance.preflight()
    old_height = rpc.height - 1
    old_hash = f"{old_height:064x}"[-64:]
    instance.store.save_checkpoint(old_height, old_hash, observed_at=1)

    height, block_hash, sequence = instance.publish_heartbeat()
    assert (height, block_hash, sequence) == (rpc.height, BLOCK, 1)
    checkpoint = instance.store.checkpoint()
    assert checkpoint["block_height"] == old_height
    assert checkpoint["block_hash"] == old_hash


def test_confirmed_outbox_delivery_acks_without_balance_credit(agent):
    instance, _rpc, adapter = agent
    instance.preflight()
    instance.delivery_enabled = True
    instance.store.upsert(
        txid=TXID,
        vout=0,
        address=WATCH,
        owner_ref="bridge-intent-1",
        amount_sats=100000,
        confirmations=3,
        block_hash=BLOCK,
        block_height=976278,
        minimum_confirmations=3,
        observed_at=1,
    )
    assert instance.enqueue_confirmed_deposits() == 1
    assert instance.deliver_outbox(limit=1) == 1
    assert len(adapter.deposits) == 1
    assert adapter.deposits[0]["idempotency_key"] == f"main:{TXID}:0"
    assert instance.outbox.counts() == {"acknowledged": 1}
