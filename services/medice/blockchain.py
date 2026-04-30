import os
import json
import logging
from datetime import datetime
from typing import Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware

logger = logging.getLogger(__name__)

THRONOS_RPC_URL     = os.getenv("THRONOS_RPC_URL",     "http://localhost:8545")
PRIVATE_KEY         = os.getenv("MEDICE_PRIVATE_KEY",  "")
CONTRACT_ADDRESS    = os.getenv("FEVER_CONTRACT_ADDRESS", "")

# Minimal ABI - only the functions we call
FEVER_ABI = json.loads('['
    '{"inputs":[{"internalType":"string","name":"_patientId","type":"string"},{"internalType":"uint256","name":"_temperature","type":"uint256"},{"internalType":"uint256","name":"_timestamp","type":"uint256"},{"internalType":"bool","name":"_antipyreticGiven","type":"bool"}],"name":"recordFeverEvent","outputs":[],"stateMutability":"nonpayable","type":"function"},'
    '{"inputs":[{"internalType":"string","name":"_patientId","type":"string"},{"internalType":"uint256","name":"_feverIndex","type":"uint256"}],"name":"closeFeverEvent","outputs":[],"stateMutability":"nonpayable","type":"function"},'
    '{"inputs":[{"internalType":"string","name":"_patientId","type":"string"}],"name":"getFeverHistory","outputs":[{"components":[{"internalType":"uint256","name":"startTime","type":"uint256"},{"internalType":"uint256","name":"endTime","type":"uint256"},{"internalType":"uint256","name":"peakTemp","type":"uint256"},{"internalType":"bool","name":"antipyreticGiven","type":"bool"},{"internalType":"bool","name":"isClosed","type":"bool"}],"internalType":"struct FeverHistory.FeverEvent[]","name":"","type":"tuple[]"}],"stateMutability":"view","type":"function"},'
    '{"inputs":[{"internalType":"string","name":"_patientId","type":"string"},{"internalType":"address","name":"_hospital","type":"address"},{"internalType":"bool","name":"_grant","type":"bool"}],"name":"setHospitalAccess","outputs":[],"stateMutability":"nonpayable","type":"function"}'
']')


class BlockchainService:
    def __init__(self):
        self.w3       = None
        self.contract = None
        self.account  = None
        self._connected = False
        self._connect()

    def _connect(self):
        try:
            self.w3 = Web3(Web3.HTTPProvider(THRONOS_RPC_URL))
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            if not self.w3.is_connected():
                logger.warning("Thronos node unreachable - blockchain features disabled")
                return
            self._connected = True
            logger.info("Connected to Thronos: %s", THRONOS_RPC_URL)
            if PRIVATE_KEY:
                self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
                logger.info("Service wallet: %s", self.account.address)
            if CONTRACT_ADDRESS:
                self.contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(CONTRACT_ADDRESS),
                    abi=FEVER_ABI,
                )
                logger.info("FeverHistory contract loaded: %s", CONTRACT_ADDRESS)
        except Exception as exc:
            logger.error("Blockchain init error: %s", exc)

    # ------------------------------------------------------------------
    async def record_fever_event(
        self,
        patient_id: str,
        temperature: float,
        ts: datetime,
        antipyretic_given: bool = False,
    ) -> Optional[str]:
        if not self._ready():
            return None
        try:
            tx = self.contract.functions.recordFeverEvent(
                patient_id,
                int(temperature * 100),   # 38.50 -> 3850
                int(ts.timestamp()),
                antipyretic_given,
            ).build_transaction(self._tx_base())
            return self._sign_and_send(tx)
        except Exception as exc:
            logger.error("record_fever_event failed: %s", exc)
            return None

    async def close_fever_event(self, patient_id: str, index: int) -> Optional[str]:
        if not self._ready():
            return None
        try:
            tx = self.contract.functions.closeFeverEvent(
                patient_id, index
            ).build_transaction(self._tx_base())
            return self._sign_and_send(tx)
        except Exception as exc:
            logger.error("close_fever_event failed: %s", exc)
            return None

    async def get_fever_history(self, patient_id: str) -> list:
        if not self._ready():
            return []
        try:
            events = self.contract.functions.getFeverHistory(patient_id).call()
            return [
                {
                    "start_time": datetime.fromtimestamp(e[0]).isoformat() if e[0] else None,
                    "end_time":   datetime.fromtimestamp(e[1]).isoformat() if e[1] else None,
                    "peak_temp":  e[2] / 100.0,
                    "antipyretic_given": e[3],
                    "is_closed":  e[4],
                }
                for e in events
            ]
        except Exception as exc:
            logger.error("get_fever_history failed: %s", exc)
            return []

    async def set_hospital_access(
        self, patient_id: str, hospital_address: str, grant: bool
    ) -> Optional[str]:
        if not self._ready():
            return None
        try:
            tx = self.contract.functions.setHospitalAccess(
                patient_id,
                Web3.to_checksum_address(hospital_address),
                grant,
            ).build_transaction(self._tx_base())
            return self._sign_and_send(tx)
        except Exception as exc:
            logger.error("set_hospital_access failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    def _tx_base(self) -> dict:
        return {
            "from":     self.account.address,
            "nonce":    self.w3.eth.get_transaction_count(self.account.address),
            "gas":      200000,
            "gasPrice": self.w3.eth.gas_price,
        }

    def _sign_and_send(self, tx: dict) -> str:
        signed  = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return receipt.transactionHash.hex()

    def _ready(self) -> bool:
        return self._connected and self.contract is not None and self.account is not None

    @property
    def is_connected(self) -> bool:
        return self._connected
