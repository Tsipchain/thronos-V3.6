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
            return self.block_hash
        if method == "decoderawtransaction":
            return dict(self.decoded)
        if method == "getblock":
            return {
                "hash": self.block_hash,
                "height": self.height,
                "tx": [dict(self.decoded)],
            }
        raise AssertionError((method, params))


class FakeAdapter:
    def __init__(self):
        self.pushes = []

    def push_tip(self, *, height, block_hash, sequence):
        self.pushes.append((height, block_hash, sequence))


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
        "blocks": 976278,
        "pruned": True,
        "synced": True,
    }


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
