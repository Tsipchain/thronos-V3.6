"""
Node Heartbeat & Registration Service

Run this on EVERY node replica that wants to participate in the reward pool:
  - Thronos chain nodes
  - ThronomedICE API replicas (Railway)
  - ASIC miners (runs on Stratum server)
  - IoT device nodes

The service:
  1. Registers the node on-chain (once, idempotent)
  2. Sends on-chain heartbeat every 12h (well within the 24h expiry)
  3. Reports ASIC hashrate every epoch (ASICs only)
  4. Claims accumulated rewards when above threshold

Usage:
  export NODE_ID=medice-api-railway-0
  export NODE_TYPE=api_node_medice      # chain_node | api_node_medice | asic_miner | iot_miner
  export THR_REWARD_ADDRESS=0x...       # wallet to receive rewards
  export MEDICE_PRIVATE_KEY=0x...
  export THRONOS_RPC_URL=http://...
  export NODE_REWARD_POOL_ADDRESS=0x...
  python node_heartbeat.py
"""
import os
import time
import json
import logging
import asyncio
from datetime import datetime
from web3 import Web3
from web3.middleware import geth_poa_middleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RPC_URL          = os.environ.get("THRONOS_RPC_URL",        "http://localhost:8545")
PRIVATE_KEY      = os.environ.get("MEDICE_PRIVATE_KEY",    "")
POOL_ADDRESS     = os.environ.get("NODE_REWARD_POOL_ADDRESS", "")
NODE_ID          = os.environ.get("NODE_ID",               "medice-api-node-0")
NODE_TYPE_STR    = os.environ.get("NODE_TYPE",             "api_node_medice")
HEARTBEAT_EVERY  = int(os.environ.get("HEARTBEAT_EVERY_S",  str(12 * 3600)))  # 12h
CLAIM_THRESHOLD  = int(os.environ.get("CLAIM_THRESHOLD_WEI", str(10**16)))     # 0.01 THR
STRATUM_STATS    = os.environ.get("STRATUM_STATS_URL",     "")  # for ASIC hashrate

NODE_TYPE_MAP = {
    "chain_node":      0,
    "api_node_medice": 1,
    "asic_miner":      2,
    "iot_miner":       3,
}

# Minimal ABI
POOL_ABI = json.loads('['
    '{"inputs":[{"internalType":"string","name":"nodeId","type":"string"},{"internalType":"uint8","name":"nodeType","type":"uint8"},{"internalType":"uint256","name":"hashrate","type":"uint256"}],"name":"registerNode","outputs":[],"stateMutability":"nonpayable","type":"function"},'
    '{"inputs":[{"internalType":"string","name":"nodeId","type":"string"}],"name":"serviceHeartbeat","outputs":[],"stateMutability":"nonpayable","type":"function"},'
    '{"inputs":[{"internalType":"address","name":"node","type":"address"},{"internalType":"uint256","name":"newHashrate","type":"uint256"}],"name":"updateHashrate","outputs":[],"stateMutability":"nonpayable","type":"function"},'
    '{"inputs":[],"name":"claimRewards","outputs":[],"stateMutability":"nonpayable","type":"function"},'
    '{"inputs":[{"internalType":"address","name":"node","type":"address"}],"name":"getPendingReward","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},'
    '{"inputs":[{"internalType":"string","name":"nodeId","type":"string"}],"name":"getNodeInfo","outputs":[{"components":[{"internalType":"address","name":"thrAddress","type":"address"},{"internalType":"uint8","name":"nodeType","type":"uint8"},{"internalType":"uint256","name":"registeredAt","type":"uint256"},{"internalType":"uint256","name":"lastHeartbeat","type":"uint256"},{"internalType":"uint256","name":"hashrate","type":"uint256"},{"internalType":"bool","name":"isActive","type":"bool"},{"internalType":"string","name":"nodeId","type":"string"},{"internalType":"uint256","name":"totalEarned","type":"uint256"}],"internalType":"struct NodeRewardPool.NodeInfo","name":"","type":"tuple"}],"stateMutability":"view","type":"function"}'
']')


class NodeHeartbeatService:
    def __init__(self):
        self.w3      = None
        self.contract = None
        self.account  = None
        self._registered = False

    def connect(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 10}))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to Thronos node: {RPC_URL}")
        if PRIVATE_KEY:
            self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
            log.info("Wallet: %s", self.account.address)
        if POOL_ADDRESS:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(POOL_ADDRESS),
                abi=POOL_ABI,
            )
            log.info("NodeRewardPool: %s", POOL_ADDRESS)

    def _tx_base(self) -> dict:
        return {
            "from":     self.account.address,
            "nonce":    self.w3.eth.get_transaction_count(self.account.address),
            "gas":      150_000,
            "gasPrice": self.w3.eth.gas_price,
        }

    def _send(self, fn) -> str:
        tx     = fn.build_transaction(self._tx_base())
        signed = self.account.sign_transaction(tx)
        h      = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        r      = self.w3.eth.wait_for_transaction_receipt(h, timeout=60)
        return r.transactionHash.hex()

    def ensure_registered(self):
        if self._registered:
            return
        try:
            info = self.contract.functions.getNodeInfo(NODE_ID).call()
            if info[5]:  # isActive
                self._registered = True
                log.info("Already registered: %s", NODE_ID)
                return
        except Exception:
            pass

        node_type = NODE_TYPE_MAP.get(NODE_TYPE_STR, 1)
        hashrate  = self._get_hashrate() if NODE_TYPE_STR == "asic_miner" else 0
        tx = self._send(
            self.contract.functions.registerNode(NODE_ID, node_type, hashrate)
        )
        self._registered = True
        log.info("Registered node %s (type=%s) tx=%s", NODE_ID, NODE_TYPE_STR, tx)

    def send_heartbeat(self):
        tx = self._send(self.contract.functions.serviceHeartbeat(NODE_ID))
        log.info("Heartbeat sent tx=%s", tx)

    def maybe_claim(self):
        pending = self.contract.functions.getPendingReward(self.account.address).call()
        thr = pending / 1e18
        log.info("Pending rewards: %.6f THR", thr)
        if pending >= CLAIM_THRESHOLD:
            tx = self._send(self.contract.functions.claimRewards())
            log.info("Claimed %.6f THR tx=%s", thr, tx)

    def maybe_update_hashrate(self):
        if NODE_TYPE_STR != "asic_miner":
            return
        hr = self._get_hashrate()
        if hr > 0:
            tx = self._send(
                self.contract.functions.updateHashrate(self.account.address, hr)
            )
            log.info("Hashrate updated: %d H/s tx=%s", hr, tx)

    def _get_hashrate(self) -> int:
        """Fetch current hashrate from Stratum stats endpoint."""
        if not STRATUM_STATS:
            return 0
        try:
            import httpx
            r = httpx.get(STRATUM_STATS, timeout=5)
            data = r.json()
            return int(data.get("hashrate", 0))
        except Exception as exc:
            log.warning("Cannot fetch hashrate: %s", exc)
            return 0

    def run(self):
        if not PRIVATE_KEY or not POOL_ADDRESS:
            log.warning("NODE_REWARD_POOL_ADDRESS or MEDICE_PRIVATE_KEY not set — reward pool disabled")
            return
        self.connect()
        self.ensure_registered()
        log.info("Heartbeat loop started (every %ds)", HEARTBEAT_EVERY)
        while True:
            try:
                self.send_heartbeat()
                self.maybe_update_hashrate()
                self.maybe_claim()
            except Exception as exc:
                log.error("Heartbeat cycle error: %s", exc)
            time.sleep(HEARTBEAT_EVERY)


if __name__ == "__main__":
    NodeHeartbeatService().run()
