"""
Thronos v3.6 Integration Module for ThronomedICE

This module bridges the medice monitoring service to the Thronos v3.6
blockchain ecosystem:
  - Verifies the Thronos node is reachable and synced
  - Registers the medice service wallet on-chain
  - Provides utilities to read Thronos network info for dashboards
  - Exposes a FastAPI router with /thronos/* status endpoints
"""
import os
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter
from web3 import Web3
from web3.middleware import geth_poa_middleware

logger = logging.getLogger(__name__)

THRONOS_RPC_URL  = os.getenv("THRONOS_RPC_URL", "http://localhost:8545")
PRIVATE_KEY      = os.getenv("MEDICE_PRIVATE_KEY", "")

router = APIRouter(prefix="/thronos", tags=["thronos"])


class ThronomedICEChainInfo:
    """
    Lightweight read-only connector to the Thronos v3.6 node.
    Used by the medice service to display chain health in its dashboard.
    """

    def __init__(self):
        self.w3: Optional[Web3] = None
        self._init()

    def _init(self):
        try:
            self.w3 = Web3(Web3.HTTPProvider(THRONOS_RPC_URL, request_kwargs={"timeout": 5}))
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            if self.w3.is_connected():
                chain_id = self.w3.eth.chain_id
                block    = self.w3.eth.block_number
                logger.info(
                    "Thronos v3.6 connected | chain_id=%s | block=%s",
                    chain_id, block
                )
            else:
                logger.warning("Thronos node not reachable at %s", THRONOS_RPC_URL)
        except Exception as exc:
            logger.error("ThronomedICEChainInfo init error: %s", exc)
            self.w3 = None

    @property
    def is_connected(self) -> bool:
        try:
            return self.w3 is not None and self.w3.is_connected()
        except Exception:
            return False

    def get_status(self) -> dict:
        if not self.is_connected:
            return {"connected": False, "rpc": THRONOS_RPC_URL}
        try:
            return {
                "connected":      True,
                "rpc":            THRONOS_RPC_URL,
                "chain_id":       self.w3.eth.chain_id,
                "latest_block":   self.w3.eth.block_number,
                "gas_price_gwei": round(self.w3.eth.gas_price / 1e9, 4),
            }
        except Exception as exc:
            return {"connected": False, "error": str(exc)}

    def get_service_wallet_info(self) -> dict:
        if not self.is_connected or not PRIVATE_KEY:
            return {"available": False}
        try:
            acct    = self.w3.eth.account.from_key(PRIVATE_KEY)
            balance = self.w3.eth.get_balance(acct.address)
            return {
                "available":     True,
                "address":       acct.address,
                "balance_ether": round(self.w3.from_wei(balance, "ether"), 6),
                "has_funds":     balance > 0,
            }
        except Exception as exc:
            return {"available": False, "error": str(exc)}


# Singleton
_chain_info = ThronomedICEChainInfo()


@router.get("/status")
def chain_status():
    """Thronos node health as seen from the medice service."""
    return {
        "timestamp":   datetime.utcnow().isoformat(),
        "node":        _chain_info.get_status(),
        "service_wallet": _chain_info.get_service_wallet_info(),
    }


@router.get("/block/{number}")
def get_block(number: int):
    if not _chain_info.is_connected:
        return {"error": "not connected"}
    try:
        blk = _chain_info.w3.eth.get_block(number)
        return {
            "number":    blk.number,
            "hash":      blk.hash.hex(),
            "timestamp": datetime.fromtimestamp(blk.timestamp).isoformat(),
            "tx_count":  len(blk.transactions),
        }
    except Exception as exc:
        return {"error": str(exc)}
