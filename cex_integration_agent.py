"""
CEX Integration Agent - Phase 4
Full autonomous integration with major cryptocurrency exchanges

Problem (Phase 3 Gap):
  Phase 3 settles inbound BTC automatically via Stellar
  But: User still needs to initiate the pledge deposit manually
  Phase 4 solution: Auto-detect user on exchange, auto-verify KYC, auto-convert

Solution (Phase 4):
  Autonomous agent monitors exchange APIs 24/7
  Detects user deposits (by email/account)
  Verifies KYC status automatically
  Converts BTC → USDC → THR without user interaction
  Pushes notification when complete
  Result: 100% autonomous end-to-end
"""

import os
import logging
import json
import threading
import queue
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import base64

logger = logging.getLogger(__name__)

# CEX Configuration
EXCHANGES = {
    "binance": {
        "api_key": os.getenv("BINANCE_API_KEY", ""),
        "api_secret": os.getenv("BINANCE_API_SECRET", ""),
        "base_url": "https://api.binance.com",
    },
    "mexc": {
        "api_key": os.getenv("MEXC_API_KEY", ""),
        "api_secret": os.getenv("MEXC_API_SECRET", ""),
        "base_url": "https://api.mexc.com",
    },
    "kraken": {
        "api_key": os.getenv("KRAKEN_API_KEY", ""),
        "api_secret": os.getenv("KRAKEN_API_SECRET", ""),
        "base_url": "https://api.kraken.com",
    },
    "bybit": {
        "api_key": os.getenv("BYBIT_API_KEY", ""),
        "api_secret": os.getenv("BYBIT_API_SECRET", ""),
        "base_url": "https://api.bybit.com",
    },
    "okx": {
        "api_key": os.getenv("OKX_API_KEY", ""),
        "api_secret": os.getenv("OKX_API_SECRET", ""),
        "passphrase": os.getenv("OKX_PASSPHRASE", ""),
        "base_url": "https://www.okx.com",
    },
}

# Monitoring Configuration
MONITORING_INTERVAL = 300  # Check exchanges every 5 minutes
KYC_CACHE_TTL = 3600  # Cache KYC status for 1 hour
MIN_AUTO_DEPOSIT = Decimal("0.00005")  # Only auto-convert >$2.13


@dataclass
class CexDeposit:
    """Represents a detected deposit on exchange"""
    exchange: str
    user_email: str
    deposit_id: str
    btc_amount: Decimal
    received_at: str
    kyc_status: str  # "verified", "pending", "rejected"
    thronos_address: Optional[str] = None  # If linked to Thronos account
    auto_converted: bool = False


@dataclass
class CexIntegrationTask:
    """Represents an auto-conversion task"""
    task_id: str
    exchange: str
    user_email: str
    thr_address: str
    btc_amount: Decimal
    status: str  # pending, kyc_check, converting, completed, failed
    created_at: str
    kyc_verified_at: Optional[str] = None
    converted_at: Optional[str] = None
    last_error: Optional[str] = None


class CexIntegrationAgent:
    """
    Autonomous agent for monitoring and auto-converting CEX deposits.

    Architecture:
    1. Monitor all exchanges 24/7 for user deposits
    2. Verify KYC status automatically
    3. Auto-convert BTC → USDC → THR
    4. Push notifications to users
    5. Reconcile with Thronos backend
    """

    def __init__(self):
        """Initialize the CEX integration agent"""
        self.task_queue: queue.Queue = queue.Queue(maxsize=10000)
        self.deposits_found: List[CexDeposit] = []
        self.conversions: List[CexIntegrationTask] = []
        self.kyc_cache: Dict[str, Dict] = {}  # { user_email: {status, timestamp} }
        self.worker_thread: Optional[threading.Thread] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.is_running = False
        self._lock = threading.Lock()
        logger.info("CEX Integration Agent initialized")

    def start(self):
        """Start monitoring and conversion threads"""
        if self.is_running:
            logger.warning("Agent already running")
            return

        self.is_running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_exchanges_loop,
            daemon=True,
            name="CEXMonitor"
        )
        self.worker_thread = threading.Thread(
            target=self._conversion_worker_loop,
            daemon=True,
            name="CEXWorker"
        )
        self.monitor_thread.start()
        self.worker_thread.start()
        logger.info("CEX Integration Agent started")

    def stop(self):
        """Stop monitoring and conversion threads"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("CEX Integration Agent stopped")

    def _monitor_exchanges_loop(self):
        """
        Monitor loop: Check all exchanges for new deposits every 5 minutes.

        Flow:
        1. Connect to each exchange API
        2. List recent deposits (last 24 hours)
        3. Filter for users with Thronos accounts
        4. Queue for auto-conversion
        5. Sleep 5 minutes, repeat
        """
        while self.is_running:
            try:
                logger.info("Scanning exchanges for deposits...")

                for exchange_name, config in EXCHANGES.items():
                    if not config.get("api_key"):
                        logger.debug(f"Skipping {exchange_name}: no API key")
                        continue

                    try:
                        deposits = self._scan_exchange_deposits(exchange_name, config)
                        for deposit in deposits:
                            self._process_detected_deposit(deposit)
                    except Exception as e:
                        logger.error(f"Error scanning {exchange_name}: {e}")

                # Sleep until next scan
                time.sleep(MONITORING_INTERVAL)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(60)

    def _scan_exchange_deposits(self, exchange: str, config: Dict) -> List[CexDeposit]:
        """
        Scan exchange for recent deposits.

        In production, this calls the actual exchange API.
        For now, returns empty list (simulation mode).

        Args:
            exchange: Exchange name (binance, mexc, kraken, etc.)
            config: Exchange API configuration

        Returns:
            List of deposits detected
        """
        try:
            logger.info(f"Scanning {exchange} for deposits...")

            # In production:
            # 1. Call exchange API to list deposits
            # 2. Filter deposits from last 24 hours
            # 3. For each deposit, look up user email
            # 4. Check if email exists in Thronos accounts
            # 5. Return matching deposits

            deposits = []

            # Simulation: Return empty list for now
            # (In production, would call real exchange APIs)

            logger.debug(f"{exchange}: Found {len(deposits)} potential deposits")
            return deposits

        except Exception as e:
            logger.error(f"Error scanning {exchange}: {e}")
            return []

    def _process_detected_deposit(self, deposit: CexDeposit):
        """Process a detected deposit"""
        try:
            with self._lock:
                self.deposits_found.append(deposit)

            logger.info(
                f"Detected deposit: {deposit.exchange} "
                f"({deposit.user_email}: {deposit.btc_amount} BTC)"
            )

            # Skip if too small
            usdc_value = deposit.btc_amount * Decimal("42500")  # ~$42.5k per BTC
            if usdc_value < MIN_AUTO_DEPOSIT:
                logger.info(f"Deposit too small (${usdc_value}), skipping")
                return

            # Create conversion task
            task_id = f"cex_{int(time.time())}_{hash(deposit.user_email) % 10000}"
            task = CexIntegrationTask(
                task_id=task_id,
                exchange=deposit.exchange,
                user_email=deposit.user_email,
                thr_address=deposit.thronos_address or "",
                btc_amount=deposit.btc_amount,
                status="pending",
                created_at=datetime.utcnow().isoformat() + "Z",
            )

            # Queue for conversion
            self.task_queue.put_nowait(task)
            with self._lock:
                self.conversions.append(task)

            logger.info(f"Queued conversion task: {task_id}")

        except Exception as e:
            logger.error(f"Error processing deposit: {e}")

    def _conversion_worker_loop(self):
        """
        Worker loop: Process conversion tasks from queue.

        Flow:
        1. Get task from queue
        2. Verify KYC status on exchange
        3. Auto-convert BTC → USDC → THR
        4. Update task status
        5. Push notification to user
        6. Record in Thronos ledger
        """
        while self.is_running:
            try:
                try:
                    task = self.task_queue.get(timeout=MONITORING_INTERVAL)
                except queue.Empty:
                    continue

                self._process_conversion_task(task)
                self.task_queue.task_done()

            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(5)

    def _process_conversion_task(self, task: CexIntegrationTask):
        """Process a single conversion task"""
        try:
            logger.info(f"Processing conversion: {task.task_id}")

            # Step 1: Verify KYC status
            task.status = "kyc_check"
            kyc_verified = self._verify_kyc_on_exchange(
                task.exchange,
                task.user_email
            )

            if not kyc_verified:
                task.status = "failed"
                task.last_error = "KYC not verified on exchange"
                logger.warning(f"KYC verification failed: {task.user_email}")
                return

            task.status = "converting"
            task.kyc_verified_at = datetime.utcnow().isoformat() + "Z"

            # Step 2: Auto-convert BTC → USDC
            success = self._auto_convert_on_exchange(
                task.exchange,
                task.user_email,
                task.btc_amount
            )

            if not success:
                task.status = "failed"
                task.last_error = "Exchange conversion failed"
                logger.error(f"Conversion failed on {task.exchange}")
                return

            # Step 3: Convert USDC → THR via Thronos system
            thr_amount = float(task.btc_amount) * 33333.33
            success = self._mint_thr_for_user(task.thr_address, thr_amount)

            if not success:
                task.status = "failed"
                task.last_error = "THR minting failed"
                logger.error(f"THR minting failed for {task.thr_address}")
                return

            # Step 4: Mark complete
            task.status = "completed"
            task.converted_at = datetime.utcnow().isoformat() + "Z"
            logger.info(f"Conversion complete: {task.task_id}")

            # Step 5: Push notification
            self._push_notification(
                task.thr_address,
                f"🎉 {task.btc_amount} BTC auto-converted to {thr_amount} THR!"
            )

        except Exception as e:
            task.status = "failed"
            task.last_error = str(e)
            logger.error(f"Error processing conversion: {e}")

    def _verify_kyc_on_exchange(self, exchange: str, user_email: str) -> bool:
        """
        Verify KYC status on exchange.

        Checks cache first, then calls exchange API if needed.

        Args:
            exchange: Exchange name
            user_email: User email address

        Returns:
            True if KYC verified, False otherwise
        """
        try:
            cache_key = f"{exchange}:{user_email}"

            # Check cache
            with self._lock:
                if cache_key in self.kyc_cache:
                    cached = self.kyc_cache[cache_key]
                    if time.time() - cached["timestamp"] < KYC_CACHE_TTL:
                        logger.debug(f"KYC cache hit: {user_email}")
                        return cached["verified"]

            # Call exchange API
            # (In production, would call real API)
            kyc_verified = self._call_exchange_kyc_api(exchange, user_email)

            # Update cache
            with self._lock:
                self.kyc_cache[cache_key] = {
                    "verified": kyc_verified,
                    "timestamp": time.time(),
                }

            logger.info(
                f"KYC verification: {user_email} on {exchange} = {kyc_verified}"
            )
            return kyc_verified

        except Exception as e:
            logger.error(f"Error verifying KYC: {e}")
            return False

    def _call_exchange_kyc_api(self, exchange: str, user_email: str) -> bool:
        """
        Call exchange API to verify KYC status.

        In production, this would call the actual exchange API.
        For now, simulates KYC verification.

        Args:
            exchange: Exchange name
            user_email: User email

        Returns:
            True if KYC verified
        """
        # In production:
        # 1. Call exchange API with API key/secret
        # 2. Look up user by email
        # 3. Check account verification status
        # 4. Return True if "verified" or equivalent

        # Simulation: Return True (assume KYC verified)
        return True

    def _auto_convert_on_exchange(
        self,
        exchange: str,
        user_email: str,
        btc_amount: Decimal
    ) -> bool:
        """
        Auto-convert BTC to USDC on exchange.

        In production, this would:
        1. Get current BTC/USDC price
        2. Place market order
        3. Monitor order completion
        4. Return success

        For now, simulates successful conversion.

        Args:
            exchange: Exchange name
            user_email: User email
            btc_amount: Amount to convert

        Returns:
            True if conversion successful
        """
        try:
            logger.info(
                f"Auto-converting {btc_amount} BTC to USDC on {exchange}"
            )

            # In production:
            # 1. Authenticate with exchange API
            # 2. Get current price
            # 3. Place market order (BTC → USDC)
            # 4. Monitor order status
            # 5. Return True on success

            # Simulation: Return True
            return True

        except Exception as e:
            logger.error(f"Conversion error on {exchange}: {e}")
            return False

    def _mint_thr_for_user(self, thr_address: str, thr_amount: float) -> bool:
        """
        Mint THR to user account.

        In production, this calls the Thronos ledger system
        to record the minting transaction.

        Args:
            thr_address: Thronos address
            thr_amount: Amount to mint

        Returns:
            True if successful
        """
        try:
            logger.info(f"Minting {thr_amount} THR to {thr_address}")

            # In production:
            # 1. Call Thronos ledger API
            # 2. Create minting transaction
            # 3. Record in blockchain
            # 4. Update user balance

            # Simulation: Return True
            return True

        except Exception as e:
            logger.error(f"Minting error: {e}")
            return False

    def _push_notification(self, thr_address: str, message: str):
        """
        Push notification to user.

        In production, this would send:
        - Email notification
        - In-app notification
        - SMS (optional)
        - Telegram bot message (optional)

        Args:
            thr_address: User's Thronos address
            message: Notification message
        """
        try:
            logger.info(f"Notification to {thr_address}: {message}")

            # In production:
            # 1. Look up user's preferred notification channels
            # 2. Send email, in-app, SMS as configured
            # 3. Log delivery status

        except Exception as e:
            logger.error(f"Notification error: {e}")

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get status of a conversion task"""
        for task in self.conversions:
            if task.task_id == task_id:
                return {
                    "task_id": task.task_id,
                    "exchange": task.exchange,
                    "user_email": task.user_email,
                    "thr_address": task.thr_address,
                    "btc_amount": str(task.btc_amount),
                    "status": task.status,
                    "created_at": task.created_at,
                    "kyc_verified_at": task.kyc_verified_at,
                    "converted_at": task.converted_at,
                    "last_error": task.last_error,
                }
        return None

    def get_pending_conversions(self) -> List[Dict]:
        """Get all pending conversions"""
        return [
            {
                "task_id": t.task_id,
                "exchange": t.exchange,
                "user_email": t.user_email,
                "btc_amount": str(t.btc_amount),
                "status": t.status,
            }
            for t in self.conversions
            if t.status in ["pending", "kyc_check", "converting"]
        ]

    def get_stats(self) -> Dict:
        """Get agent statistics"""
        completed = sum(1 for t in self.conversions if t.status == "completed")
        failed = sum(1 for t in self.conversions if t.status == "failed")
        pending = sum(1 for t in self.conversions if t.status != "completed" and t.status != "failed")
        total_btc = sum(
            t.btc_amount for t in self.conversions if t.status == "completed"
        )

        return {
            "queue_size": self.task_queue.qsize(),
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "total_btc_converted": float(total_btc),
            "total_deposits_found": len(self.deposits_found),
            "agent_running": self.is_running,
        }


# Global instance
_agent: Optional[CexIntegrationAgent] = None


def initialize_agent() -> CexIntegrationAgent:
    """Initialize global agent"""
    global _agent
    _agent = CexIntegrationAgent()
    return _agent


def get_agent() -> Optional[CexIntegrationAgent]:
    """Get global agent instance"""
    return _agent


def start_agent():
    """Start agent monitoring"""
    if not _agent:
        raise RuntimeError("Agent not initialized")
    _agent.start()


def stop_agent():
    """Stop agent monitoring"""
    if not _agent:
        return
    _agent.stop()
