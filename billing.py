"""
Thronos Billing Module - Clean separation of Chat (credits) vs Architect (THR)

Rules:
- Chat: credits-only billing (consume_credits)
- Architect: THR-only billing (charge_thr)
- Cross-charge blocked with 403 + telemetry
- Architect rewards credits: 1 THR spent → +10 credits for chat
- ENV modes: CHAT_BILLING_MODE="credits", ARCHITECT_BILLING_MODE="thr"
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)

# ENV configuration
CHAT_BILLING_MODE = os.getenv("CHAT_BILLING_MODE", "credits").lower()
ARCHITECT_BILLING_MODE = os.getenv("ARCHITECT_BILLING_MODE", "thr").lower()

# Architect pricing
ARCHITECT_BASE_FEE = Decimal("0.001")  # 0.001 THR base fee
ARCHITECT_VARIABLE_RATE = Decimal("0.0001")  # per 1000 tokens or per file
ARCHITECT_CREDITS_REWARD_RATIO = 10  # 1 THR → 10 credits

# File paths (will be set by server.py)
DATA_DIR = None
LEDGER_FILE = None
CHAIN_FILE = None
AI_CREDITS_FILE = None
BILLING_TELEMETRY_FILE = None
AI_WALLET_ADDRESS = None


def init_billing(data_dir: str, ledger_file: str, chain_file: str, ai_credits_file: str, ai_wallet: str):
    """Initialize billing module with file paths from server.py"""
    global DATA_DIR, LEDGER_FILE, CHAIN_FILE, AI_CREDITS_FILE, BILLING_TELEMETRY_FILE, AI_WALLET_ADDRESS
    DATA_DIR = data_dir
    LEDGER_FILE = ledger_file
    CHAIN_FILE = chain_file
    AI_CREDITS_FILE = ai_credits_file
    AI_WALLET_ADDRESS = ai_wallet
    BILLING_TELEMETRY_FILE = os.path.join(data_dir, "billing_telemetry.jsonl")
    logger.info(f"Billing module initialized: CHAT={CHAT_BILLING_MODE}, ARCHITECT={ARCHITECT_BILLING_MODE}")


def _load_json(filepath: str, default):
    """Load JSON file with fallback"""
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
    return default


def _save_json(filepath: str, data):
    """Save JSON file"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")


def _record_telemetry(entry: Dict[str, Any]):
    """Append billing telemetry (JSONL)"""
    try:
        entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        with open(BILLING_TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to record telemetry: {e}")


# ─── CREDITS BILLING (Chat only) ────────────────────────────────────────

def consume_credits(wallet: str, amount: int, product: str = "chat") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Consume credits from wallet (Chat only).

    Args:
        wallet: User THR wallet address
        amount: Number of credits to consume (usually 1)
        product: Must be "chat" (cross-charge guard)

    Returns:
        (success: bool, error_msg: str, telemetry: dict)
    """
    # Cross-charge guard
    if product != "chat":
        error = f"BLOCKED: consume_credits called from product={product} (only 'chat' allowed)"
        logger.error(error)
        _record_telemetry({
            "event": "cross_charge_blocked",
            "product": product,
            "wallet": wallet,
            "attempted_action": "consume_credits",
            "reason": "Cross-charge violation"
        })
        return False, error, {}

    # Load credits
    credits_map = _load_json(AI_CREDITS_FILE, {})
    current = int(credits_map.get(wallet, 0))

    if current < amount:
        error = f"Insufficient credits: have {current}, need {amount}"
        _record_telemetry({
            "event": "credits_insufficient",
            "product": product,
            "wallet": wallet,
            "credits_available": current,
            "credits_needed": amount,
            "billing_channel": "credits",
            "charge_result": "failed"
        })
        return False, error, {"credits_available": current}

    # Deduct credits
    new_balance = current - amount
    credits_map[wallet] = new_balance
    _save_json(AI_CREDITS_FILE, credits_map)

    telemetry = {
        "event": "credits_consumed",
        "product": product,
        "wallet": wallet,
        "credits_delta": -amount,
        "credits_before": current,
        "credits_after": new_balance,
        "billing_channel": "credits",
        "charge_result": "success"
    }
    _record_telemetry(telemetry)

    try:
        chain = _load_json(CHAIN_FILE, [])
        tx = {
            "type": "CREDITS_CONSUME",
            "from": wallet,
            "to": AI_WALLET_ADDRESS,
            "amount": float(amount),
            "symbol": "CREDITS",
            "status": "confirmed",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "tx_id": f"CREDITS-{int(time.time())}-{len(chain)}",
            "metadata": {"billing_unit": "credits", "session_type": "chat", "product": product},
        }
        chain.append(tx)
        _save_json(CHAIN_FILE, chain)
    except Exception as e:
        logger.error(f"Failed to append credits tx: {e}")

    logger.info(f"Credits consumed: {wallet} -{amount} credits (now {new_balance})")
    return True, "", telemetry


# ─── THR BILLING (Architect only) ───────────────────────────────────────

def charge_thr(wallet: str, amount: Decimal, reason: str, product: str = "architect", metadata: Optional[Dict] = None) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Charge THR from wallet (Architect only).

    Args:
        wallet: User THR wallet address
        amount: THR amount to charge (Decimal)
        reason: Charge reason (e.g., "architect_usage")
        product: Must be "architect" (cross-charge guard)
        metadata: Optional extra info (tokens, files, etc.)

    Returns:
        (success: bool, error_msg: str, telemetry: dict)
    """
    # Cross-charge guard
    if product != "architect":
        error = f"BLOCKED: charge_thr called from product={product} (only 'architect' allowed)"
        logger.error(error)
        _record_telemetry({
            "event": "cross_charge_blocked",
            "product": product,
            "wallet": wallet,
            "attempted_action": "charge_thr",
            "reason": "Cross-charge violation"
        })
        return False, error, {}

    # Load ledger
    ledger = _load_json(LEDGER_FILE, {})
    balance = Decimal(str(ledger.get(wallet, 0)))

    if balance < amount:
        error = f"Insufficient THR: have {balance}, need {amount}"
        _record_telemetry({
            "event": "thr_insufficient",
            "product": product,
            "wallet": wallet,
            "thr_available": float(balance),
            "thr_needed": float(amount),
            "billing_channel": "thr",
            "charge_result": "failed"
        })
        return False, error, {"thr_available": float(balance)}

    # Deduct THR from user, credit AI wallet
    new_balance = balance - amount
    ledger[wallet] = float(new_balance.quantize(Decimal("0.000001"), rounding=ROUND_DOWN))

    ai_balance = Decimal(str(ledger.get(AI_WALLET_ADDRESS, 0)))
    ledger[AI_WALLET_ADDRESS] = float((ai_balance + amount).quantize(Decimal("0.000001"), rounding=ROUND_DOWN))

    _save_json(LEDGER_FILE, ledger)

    # Create chain transaction
    chain = _load_json(CHAIN_FILE, [])
    tx_meta = {"billing_unit": "thr", "session_type": "architect", "product": product}
    if metadata:
        tx_meta.update(metadata)
    tx = {
        "type": "architect_payment",
        "reason": reason,
        "from": wallet,
        "to": AI_WALLET_ADDRESS,
        "amount": float(amount),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "tx_id": f"ARCH-{int(time.time())}-{len(chain)}",
        "metadata": tx_meta,
    }
    chain.append(tx)
    _save_json(CHAIN_FILE, chain)

    telemetry = {
        "event": "thr_charged",
        "product": product,
        "wallet": wallet,
        "thr_delta": -float(amount),
        "thr_before": float(balance),
        "thr_after": float(new_balance),
        "billing_channel": "thr",
        "charge_result": "success",
        "reason": reason,
        "tx_id": tx["tx_id"]
    }
    if metadata:
        telemetry["metadata"] = metadata
    _record_telemetry(telemetry)

    logger.info(f"THR charged: {wallet} -{amount} THR (now {new_balance}, reason: {reason})")
    return True, "", telemetry


def grant_credits_from_thr_spend(wallet: str, thr_spent: Decimal) -> Dict[str, Any]:
    """
    Grant credits as reward for THR spending in Architect.
    Ratio: 1 THR → 10 credits

    Args:
        wallet: User wallet
        thr_spent: THR amount spent (Decimal)

    Returns:
        telemetry: dict
    """
    credits_granted = int(thr_spent * ARCHITECT_CREDITS_REWARD_RATIO)

    if credits_granted <= 0:
        return {}

    # Load credits
    credits_map = _load_json(AI_CREDITS_FILE, {})
    current = int(credits_map.get(wallet, 0))
    new_balance = current + credits_granted
    credits_map[wallet] = new_balance
    _save_json(AI_CREDITS_FILE, credits_map)

    telemetry = {
        "event": "credits_granted_from_thr",
        "product": "architect",
        "wallet": wallet,
        "thr_spent": float(thr_spent),
        "credits_delta": credits_granted,
        "credits_before": current,
        "credits_after": new_balance,
        "billing_channel": "reward",
        "charge_result": "success"
    }
    _record_telemetry(telemetry)

    logger.info(f"Credits granted: {wallet} +{credits_granted} credits from {thr_spent} THR spent")
    return telemetry


# ─── ARCHITECT FEE CALCULATION ──────────────────────────────────────────

def calculate_architect_fee(tokens_out: int = 0, files_count: int = 0, blueprint_complexity: int = 1) -> Decimal:
    """
    Calculate Architect variable fee.

    Formula: base (0.001 THR) + (tokens_out / 1000 * 0.0001) + (files_count * 0.0001)

    Args:
        tokens_out: Output tokens count
        files_count: Number of generated files
        blueprint_complexity: Multiplier (1-10)

    Returns:
        total_fee: Decimal
    """
    base = ARCHITECT_BASE_FEE

    # Token-based fee (per 1000 tokens)
    token_fee = Decimal(tokens_out) / Decimal("1000") * ARCHITECT_VARIABLE_RATE

    # File-based fee
    file_fee = Decimal(files_count) * ARCHITECT_VARIABLE_RATE

    # Complexity multiplier
    variable = (token_fee + file_fee) * Decimal(blueprint_complexity)

    total = base + variable
    return total.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
