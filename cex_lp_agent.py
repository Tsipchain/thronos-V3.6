"""
CEX Integration Agent - Uses Liquidity Pool for THR Minting
Separated from Pledge System

Detects deposits from major CEX (Binance, MEXC, Kraken, Bybit, OKX)
and converts BTC → THR using native Liquidity Pool rates
"""

import os
import logging
import json
import threading
import queue
import time
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal

logger = logging.getLogger(__name__)

# Exchange Configuration
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")
MEXC_API_KEY = os.getenv("MEXC_API_KEY", "")
MEXC_SECRET = os.getenv("MEXC_SECRET", "")
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY", "")
KRAKEN_SECRET = os.getenv("KRAKEN_SECRET", "")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_SECRET = os.getenv("BYBIT_SECRET", "")
OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_SECRET = os.getenv("OKX_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")

# Agent Configuration
MONITORING_INTERVAL = 300  # 5 minutes
KYC_CACHE_TTL = 3600  # 1 hour
MIN_AUTO_DEPOSIT = Decimal("0.00005")  # Minimum deposit to convert (~$2)
QUEUE_MAX_SIZE = 10000
MAX_RETRY_ATTEMPTS = 5
RETRY_BACKOFF_BASE = 2  # Exponential: 2^n seconds


@dataclass
class CexDepositDetection:
    """Represents a detected CEX deposit"""
    exchange: str
    user_email: str
    deposit_id: str
    btc_amount: Decimal
    received_at: str
    kyc_status: str  # "verified", "pending", "rejected"
    thronos_address: Optional[str]  # Linked Thronos address

    def to_dict(self) -> Dict:
        return {
            "exchange": self.exchange,
            "user_email": self.user_email,
            "deposit_id": self.deposit_id,
            "btc_amount": str(self.btc_amount),
            "received_at": self.received_at,
            "kyc_status": self.kyc_status,
            "thronos_address": self.thronos_address,
        }


@dataclass
class CexConversionTask:
    """Task for converting detected CEX deposit to THR"""
    task_id: str
    exchange: str
    user_email: str
    thr_address: str
    btc_amount: Decimal
    status: str  # "pending", "processing", "completed", "failed"
    created_at: str
    kyc_verified_at: Optional[str] = None
    conversion_at: Optional[str] = None
    last_error: Optional[str] = None
    attempt_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "exchange": self.exchange,
            "user_email": self.user_email,
            "thr_address": self.thr_address,
            "btc_amount": str(self.btc_amount),
            "status": self.status,
            "created_at": self.created_at,
            "kyc_verified_at": self.kyc_verified_at,
            "conversion_at": self.conversion_at,
            "last_error": self.last_error,
            "attempt_count": self.attempt_count,
        }


class CexLpAgent:
    """Detects CEX deposits and converts to THR using Liquidity Pool"""

    def __init__(self, bridge_coordinator=None):
        """
        Initialize CEX LP Agent

        Args:
            bridge_coordinator: BridgeCoordinator instance for LP access
        """
        self.bridge_coordinator = bridge_coordinator
        self.conversion_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.task_history: List[CexConversionTask] = []
        self.kyc_cache: Dict[Tuple[str, str], Tuple[str, float]] = {}  # (exchange, email) -> (status, timestamp)

        self.monitor_thread: Optional[threading.Thread] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.is_running = False
        self._lock = threading.Lock()

        logger.info("CexLpAgent initialized")

    def start(self):
        """Start monitoring and conversion threads"""
        if self.is_running:
            logger.warning("Agent already running")
            return

        self.is_running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_exchanges_loop,
            daemon=True
        )
        self.worker_thread = threading.Thread(
            target=self._conversion_worker_loop,
            daemon=True
        )
        self.monitor_thread.start()
        self.worker_thread.start()
        logger.info("✅ CEX LP Agent started (monitor + worker threads)")

    def stop(self):
        """Stop monitoring and conversion threads"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("CEX LP Agent stopped")

    def _monitor_exchanges_loop(self):
        """Monitor all exchanges every 5 minutes for deposits"""
        while self.is_running:
            try:
                exchanges = ["binance", "mexc", "kraken", "bybit", "okx"]
                for exchange in exchanges:
                    try:
                        self._scan_exchange_deposits(exchange)
                    except Exception as e:
                        logger.error(f"Error scanning {exchange}: {e}")

                time.sleep(MONITORING_INTERVAL)
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(10)

    def _scan_exchange_deposits(self, exchange: str):
        """
        Scan exchange for deposits (simulated - integrate with real API)

        In production: Use ccxt or official exchange APIs
        """
        logger.debug(f"Scanning {exchange} for deposits...")
        # In production: Call exchange API to list deposits from last 24h
        # For each deposit:
        #   - Check if user email is linked to Thronos account
        #   - Verify user opted into auto-conversion
        #   - Queue conversion task

    def _process_detected_deposit(self, deposit: CexDepositDetection):
        """Queue a detected deposit for conversion"""
        if deposit.btc_amount < MIN_AUTO_DEPOSIT:
            logger.debug(f"Deposit too small: {deposit.btc_amount} BTC, skipping")
            return

        if not deposit.thronos_address:
            logger.debug(f"No linked Thronos address for {deposit.user_email}, skipping")
            return

        task_id = f"cex_{int(time.time())}_{hash(deposit.user_email) % 10000}"
        task = CexConversionTask(
            task_id=task_id,
            exchange=deposit.exchange,
            user_email=deposit.user_email,
            thr_address=deposit.thronos_address,
            btc_amount=deposit.btc_amount,
            status="pending",
            created_at=datetime.utcnow().isoformat() + "Z"
        )

        try:
            self.conversion_queue.put_nowait(task)
            with self._lock:
                self.task_history.append(task)
            logger.info(f"Queued CEX conversion: {task_id} ({deposit.exchange}: {deposit.btc_amount} BTC)")
        except queue.Full:
            logger.error("Conversion queue full")

    def _conversion_worker_loop(self):
        """Process conversion queue with retry logic"""
        while self.is_running:
            try:
                try:
                    task = self.conversion_queue.get(timeout=30)
                except queue.Empty:
                    continue

                success = self._process_conversion_task(task)

                if not success:
                    task.status = "failed"
                    logger.error(f"Conversion failed: {task.task_id}")
                    # TODO: Log to manual review queue

                self.conversion_queue.task_done()
            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(5)

    def _process_conversion_task(self, task: CexConversionTask) -> bool:
        """Convert detected CEX deposit to THR using Liquidity Pool"""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                task.status = "processing"
                task.attempt_count = attempt + 1

                # Step 1: Verify KYC
                kyc_verified = self._verify_kyc_on_exchange(task.exchange, task.user_email)
                if not kyc_verified:
                    raise ValueError(f"KYC not verified on {task.exchange}")
                task.kyc_verified_at = datetime.utcnow().isoformat() + "Z"

                # Step 2: Use Liquidity Pool to mint THR
                thr_minted = self._mint_thr_via_lp(task.thr_address, task.btc_amount)

                # Step 3: Success
                task.status = "completed"
                task.conversion_at = datetime.utcnow().isoformat() + "Z"
                logger.info(
                    f"Conversion completed: {task.task_id} "
                    f"({task.btc_amount} BTC → {thr_minted} THR)"
                )
                return True

            except Exception as e:
                task.last_error = str(e)
                wait_time = RETRY_BACKOFF_BASE ** attempt

                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        f"Conversion retry {attempt + 1}/{MAX_RETRY_ATTEMPTS}: "
                        f"{task.task_id} failed ({e}), waiting {wait_time}s"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Conversion {task.task_id} failed after all retries: {e}")
                    return False

        return False

    def _verify_kyc_on_exchange(self, exchange: str, user_email: str) -> bool:
        """
        Verify KYC status with 1-hour caching

        In production: Call exchange API to check KYC verification level
        """
        cache_key = (exchange, user_email)

        # Check cache
        if cache_key in self.kyc_cache:
            status, timestamp = self.kyc_cache[cache_key]
            if time.time() - timestamp < KYC_CACHE_TTL:
                logger.debug(f"KYC cache hit: {exchange} {user_email} = {status}")
                return status == "verified"

        # In production: Query exchange API
        # For now: Simulate verified
        status = "verified"
        self.kyc_cache[cache_key] = (status, time.time())

        logger.debug(f"KYC verified: {exchange} {user_email}")
        return status == "verified"

    def _mint_thr_via_lp(self, thr_address: str, btc_amount: Decimal) -> float:
        """
        Mint THR using Liquidity Pool

        Simulates: LP.swap(BTC) → THR based on current pool rates
        """
        if not self.bridge_coordinator:
            raise ValueError("Bridge coordinator not available")

        # Get BTC-THR pool
        pool_id = "bitcoin_thronos"
        pool = self.bridge_coordinator.pools.get(pool_id)

        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        # Calculate exchange rate from pool
        # In Uniswap-style: (base_reserve * paired_reserve) = constant
        exchange_rate = pool.get_exchange_rate()

        # Apply pool reserves and get output amount
        thr_amount = float(btc_amount) * (1.0 / exchange_rate) if exchange_rate > 0 else 0

        # Simulate LP update (in production: actual token swap)
        logger.debug(
            f"Minting {thr_amount} THR for {thr_address} "
            f"(LP rate: 1 BTC = {1.0/exchange_rate if exchange_rate > 0 else 0} THR)"
        )

        return thr_amount

    def _push_notification(self, thr_address: str, btc_amount: Decimal, thr_minted: float):
        """Send notification to user"""
        # In production: Email, SMS, in-app notification
        logger.info(f"Notifying {thr_address}: {btc_amount} BTC → {thr_minted} THR")

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get status of conversion task"""
        for task in self.task_history:
            if task.task_id == task_id:
                return task.to_dict()
        return None

    def get_pending_conversions(self) -> List[Dict]:
        """Get all pending conversion tasks"""
        return [
            task.to_dict()
            for task in self.task_history
            if task.status == "pending"
        ]

    def get_completed_conversions(self) -> List[Dict]:
        """Get all completed conversions"""
        return [
            task.to_dict()
            for task in self.task_history
            if task.status == "completed"
        ]

    def get_stats(self) -> Dict:
        """Get agent statistics"""
        pending = sum(1 for t in self.task_history if t.status == "pending")
        completed = sum(1 for t in self.task_history if t.status == "completed")
        failed = sum(1 for t in self.task_history if t.status == "failed")
        processing = sum(1 for t in self.task_history if t.status == "processing")

        total_btc = sum(
            t.btc_amount for t in self.task_history
            if t.status == "completed"
        )

        return {
            "queue_size": self.conversion_queue.qsize(),
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "total_btc_converted": float(total_btc),
            "agent_running": self.is_running,
        }


# Global instance
_cex_lp_agent: Optional[CexLpAgent] = None


def initialize_cex_lp_agent(bridge_coordinator=None) -> CexLpAgent:
    """Initialize global CEX LP agent"""
    global _cex_lp_agent
    _cex_lp_agent = CexLpAgent(bridge_coordinator)
    return _cex_lp_agent


def get_cex_lp_agent() -> Optional[CexLpAgent]:
    """Get global agent instance"""
    return _cex_lp_agent


def start_cex_lp_agent():
    """Start agent via global instance"""
    if not _cex_lp_agent:
        raise RuntimeError("Agent not initialized")
    _cex_lp_agent.start()


def stop_cex_lp_agent():
    """Stop agent via global instance"""
    if not _cex_lp_agent:
        return
    _cex_lp_agent.stop()
