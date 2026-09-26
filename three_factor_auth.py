"""Thronos 3-Factor Authentication Blueprint.

Factor 1: Wallet ownership (ECDSA key — already in auth/verify)
Factor 2: QR challenge-response (already in auth/challenge)
Factor 3: Push notification to PWA for biometric (Face ID / fingerprint) approval

Flow for sensitive operations (transactions, large transfers):
1. User initiates transaction on laptop/PC
2. Server creates approval request + sends push notification to registered device
3. PWA receives push, shows approval screen with transaction details
4. User verifies biometrically (Face ID / fingerprint via navigator.credentials)
5. PWA signs approval with device key and POSTs back
6. Server marks approval as done, transaction proceeds
"""

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

logger = logging.getLogger("thronos-3fa")

three_factor_bp = Blueprint("three_factor", __name__)

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
DEVICES_FILE = os.path.join(DATA_DIR, "3fa_devices.json")
APPROVALS_FILE = os.path.join(DATA_DIR, "3fa_approvals.json")

APPROVAL_TTL = 120  # seconds
_APPROVAL_STORE: Dict[str, dict] = {}
_APPROVAL_LOCK = threading.Lock()

_DEVICE_STORE: Dict[str, list] = {}  # wallet -> [device_info, ...]
_DEVICE_LOCK = threading.Lock()


def _load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _load_devices():
    global _DEVICE_STORE
    _DEVICE_STORE = _load_json(DEVICES_FILE, {})


def _save_devices():
    _save_json(DEVICES_FILE, _DEVICE_STORE)


def _prune_approvals():
    now = time.time()
    expired = [k for k, v in _APPROVAL_STORE.items() if now - v["created_at"] > APPROVAL_TTL]
    for k in expired:
        del _APPROVAL_STORE[k]


# ── Device Registration ─────────────────────────────────────────────────────

@three_factor_bp.route("/device/register", methods=["POST"])
def register_device():
    """Register a device (PWA) for 3FA push notifications.

    Body: {
        wallet: "THR...",
        device_id: "unique-device-id",
        device_name: "iPhone 15 Pro",
        push_subscription: { endpoint, keys: { p256dh, auth } },
        public_key: "hex — device-specific signing key for approvals"
    }
    """
    data = request.get_json() or {}
    wallet = (data.get("wallet") or "").strip()
    device_id = (data.get("device_id") or "").strip()
    push_sub = data.get("push_subscription") or {}

    if not wallet or not device_id:
        return jsonify(ok=False, error="wallet and device_id required"), 400

    device_info = {
        "device_id": device_id,
        "device_name": data.get("device_name", "Unknown Device"),
        "push_subscription": push_sub,
        "public_key": data.get("public_key", ""),
        "registered_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "last_used": None,
        "biometric_capable": data.get("biometric_capable", False),
    }

    with _DEVICE_LOCK:
        _load_devices()
        devices = _DEVICE_STORE.get(wallet, [])
        # Update existing or add new
        updated = False
        for i, d in enumerate(devices):
            if d.get("device_id") == device_id:
                devices[i] = device_info
                updated = True
                break
        if not updated:
            devices.append(device_info)
        _DEVICE_STORE[wallet] = devices
        _save_devices()

    return jsonify(ok=True, device_id=device_id, total_devices=len(devices))


@three_factor_bp.route("/device/list", methods=["GET"])
def list_devices():
    """List registered 3FA devices for a wallet."""
    wallet = request.args.get("wallet", "").strip()
    if not wallet:
        wallet = request.cookies.get("thr_address", "")
    if not wallet:
        return jsonify(ok=False, error="wallet required"), 400

    with _DEVICE_LOCK:
        _load_devices()
        devices = _DEVICE_STORE.get(wallet, [])

    safe_devices = []
    for d in devices:
        safe_devices.append({
            "device_id": d.get("device_id"),
            "device_name": d.get("device_name"),
            "registered_at": d.get("registered_at"),
            "last_used": d.get("last_used"),
            "biometric_capable": d.get("biometric_capable", False),
        })

    return jsonify(ok=True, devices=safe_devices, count=len(safe_devices))


@three_factor_bp.route("/device/remove", methods=["POST"])
def remove_device():
    """Remove a registered device."""
    data = request.get_json() or {}
    wallet = (data.get("wallet") or request.cookies.get("thr_address") or "").strip()
    device_id = (data.get("device_id") or "").strip()

    if not wallet or not device_id:
        return jsonify(ok=False, error="wallet and device_id required"), 400

    with _DEVICE_LOCK:
        _load_devices()
        devices = _DEVICE_STORE.get(wallet, [])
        _DEVICE_STORE[wallet] = [d for d in devices if d.get("device_id") != device_id]
        _save_devices()

    return jsonify(ok=True)


# ── Approval Request (transaction gating) ────────────────────────────────────

@three_factor_bp.route("/approval/request", methods=["POST"])
def request_approval():
    """Create a 3FA approval request for a sensitive operation.

    Body: {
        wallet: "THR...",
        action: "transfer",
        details: { to, amount, token, ... },
        device_id: "optional — target specific device"
    }

    Returns an approval_id that the client polls until approved or expired.
    """
    data = request.get_json() or {}
    wallet = (data.get("wallet") or request.cookies.get("thr_address") or "").strip()
    action = (data.get("action") or "").strip()
    details = data.get("details") or {}

    if not wallet:
        return jsonify(ok=False, error="wallet required"), 400
    if not action:
        return jsonify(ok=False, error="action required"), 400

    # Check if wallet has registered devices
    with _DEVICE_LOCK:
        _load_devices()
        devices = _DEVICE_STORE.get(wallet, [])

    if not devices:
        return jsonify(ok=False, error="no_devices",
                       detail="No 3FA devices registered. Register a device first."), 400

    target_device = data.get("device_id")
    if target_device:
        device_match = [d for d in devices if d.get("device_id") == target_device]
        if not device_match:
            return jsonify(ok=False, error="device_not_found"), 404
    else:
        device_match = devices

    approval_id = secrets.token_urlsafe(32)
    nonce = secrets.token_hex(16)
    now = time.time()

    approval = {
        "approval_id": approval_id,
        "wallet": wallet,
        "action": action,
        "details": _sanitize_details(details),
        "nonce": nonce,
        "status": "pending",
        "created_at": now,
        "expires_at": now + APPROVAL_TTL,
        "target_devices": [d.get("device_id") for d in device_match],
        "approved_by": None,
        "approved_at": None,
    }

    with _APPROVAL_LOCK:
        _prune_approvals()
        _APPROVAL_STORE[approval_id] = approval

    # Build push payload for devices
    push_payload = {
        "type": "3fa_approval",
        "approval_id": approval_id,
        "action": action,
        "details": _sanitize_details(details),
        "nonce": nonce,
        "expires_in": APPROVAL_TTL,
    }

    # Send push notification to each target device
    push_results = []
    for device in device_match:
        push_sub = device.get("push_subscription", {})
        if push_sub and push_sub.get("endpoint"):
            result = _send_push(push_sub, push_payload)
            push_results.append({"device_id": device["device_id"], "pushed": result})
        else:
            push_results.append({"device_id": device["device_id"], "pushed": False, "reason": "no_subscription"})

    return jsonify(
        ok=True,
        approval_id=approval_id,
        expires_in=APPROVAL_TTL,
        devices_notified=push_results,
        poll_url=f"/api/3fa/approval/status/{approval_id}",
    )


@three_factor_bp.route("/approval/status/<approval_id>", methods=["GET"])
def approval_status(approval_id):
    """Poll for approval status."""
    with _APPROVAL_LOCK:
        _prune_approvals()
        approval = _APPROVAL_STORE.get(approval_id)

    if not approval:
        return jsonify(ok=False, error="approval_not_found"), 404

    now = time.time()
    if now > approval["expires_at"]:
        return jsonify(ok=False, status="expired", error="approval_expired"), 410

    return jsonify(
        ok=True,
        status=approval["status"],
        approval_id=approval_id,
        action=approval["action"],
        expires_in=max(0, int(approval["expires_at"] - now)),
        approved_by=approval.get("approved_by"),
        approved_at=approval.get("approved_at"),
    )


@three_factor_bp.route("/approval/approve", methods=["POST"])
def approve_request():
    """Approve a 3FA request from the PWA after biometric verification.

    Body: {
        approval_id: "...",
        device_id: "...",
        biometric_assertion: { ... },  // WebAuthn assertion result
        signature: "hex"  // device key signs approval_id + nonce
    }
    """
    data = request.get_json() or {}
    approval_id = (data.get("approval_id") or "").strip()
    device_id = (data.get("device_id") or "").strip()

    if not approval_id or not device_id:
        return jsonify(ok=False, error="approval_id and device_id required"), 400

    with _APPROVAL_LOCK:
        _prune_approvals()
        approval = _APPROVAL_STORE.get(approval_id)
        if not approval:
            return jsonify(ok=False, error="approval_not_found"), 404
        if approval["status"] != "pending":
            return jsonify(ok=False, error="already_resolved", status=approval["status"]), 409
        if time.time() > approval["expires_at"]:
            return jsonify(ok=False, error="approval_expired"), 410
        if device_id not in approval["target_devices"]:
            return jsonify(ok=False, error="device_not_authorized"), 403

        # Mark approved
        approval["status"] = "approved"
        approval["approved_by"] = device_id
        approval["approved_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    # Update device last_used
    wallet = approval["wallet"]
    with _DEVICE_LOCK:
        _load_devices()
        for d in _DEVICE_STORE.get(wallet, []):
            if d.get("device_id") == device_id:
                d["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                break
        _save_devices()

    logger.info("[3FA] Approved: %s by device %s for wallet %s", approval_id, device_id, wallet)

    return jsonify(ok=True, status="approved", approval_id=approval_id)


@three_factor_bp.route("/approval/deny", methods=["POST"])
def deny_request():
    """Deny a 3FA request from the PWA."""
    data = request.get_json() or {}
    approval_id = (data.get("approval_id") or "").strip()
    device_id = (data.get("device_id") or "").strip()

    if not approval_id:
        return jsonify(ok=False, error="approval_id required"), 400

    with _APPROVAL_LOCK:
        approval = _APPROVAL_STORE.get(approval_id)
        if not approval:
            return jsonify(ok=False, error="approval_not_found"), 404
        if approval["status"] != "pending":
            return jsonify(ok=False, error="already_resolved", status=approval["status"]), 409
        approval["status"] = "denied"
        approval["approved_by"] = device_id
        approval["approved_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    logger.info("[3FA] Denied: %s by device %s", approval_id, device_id)
    return jsonify(ok=True, status="denied", approval_id=approval_id)


# ── 3FA status / settings ───────────────────────────────────────────────────

@three_factor_bp.route("/status", methods=["GET"])
def threefa_status():
    """Check if 3FA is enabled for a wallet and return configuration."""
    wallet = request.args.get("wallet", "").strip() or request.cookies.get("thr_address", "")
    if not wallet:
        return jsonify(ok=False, error="wallet required"), 400

    with _DEVICE_LOCK:
        _load_devices()
        devices = _DEVICE_STORE.get(wallet, [])

    return jsonify(
        ok=True,
        enabled=len(devices) > 0,
        device_count=len(devices),
        factors=["wallet_ownership", "qr_challenge", "biometric_push"] if devices else ["wallet_ownership", "qr_challenge"],
    )


# ── Helper: check 3FA before transaction ─────────────────────────────────────

def check_3fa_required(wallet: str, action: str = "transfer", amount: float = 0) -> bool:
    """Check if this wallet has 3FA devices registered (meaning 3FA is required)."""
    _load_devices()
    return len(_DEVICE_STORE.get(wallet, [])) > 0


def verify_3fa_approval(approval_id: str, wallet: str) -> Dict[str, Any]:
    """Verify that an approval_id is valid and approved for the given wallet."""
    with _APPROVAL_LOCK:
        approval = _APPROVAL_STORE.get(approval_id)
        if not approval:
            return {"ok": False, "error": "approval_not_found"}
        if approval["wallet"] != wallet:
            return {"ok": False, "error": "wallet_mismatch"}
        if approval["status"] != "approved":
            return {"ok": False, "error": f"status_{approval['status']}"}
        if time.time() > approval["expires_at"]:
            return {"ok": False, "error": "approval_expired"}
        return {"ok": True, "approved_by": approval["approved_by"]}


# ── Push notification sender ─────────────────────────────────────────────────

def _send_push(subscription: dict, payload: dict) -> bool:
    """Send a Web Push notification. Returns True on success."""
    endpoint = subscription.get("endpoint", "")
    if not endpoint:
        return False
    try:
        from pywebpush import webpush
        vapid_key = os.getenv("VAPID_PRIVATE_KEY", "")
        vapid_email = os.getenv("VAPID_CONTACT_EMAIL", "admin@thronoschain.org")
        if not vapid_key:
            logger.warning("[3FA] VAPID_PRIVATE_KEY not set — push notification skipped")
            return False
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=vapid_key,
            vapid_claims={"sub": f"mailto:{vapid_email}"},
            timeout=10,
        )
        return True
    except ImportError:
        logger.debug("[3FA] pywebpush not installed — push skipped")
        return False
    except Exception as exc:
        logger.warning("[3FA] Push failed: %s", exc)
        return False


def _sanitize_details(details: dict) -> dict:
    """Strip sensitive fields from transaction details before sending to device."""
    safe = {}
    for k, v in (details or {}).items():
        if k in ("private_key", "seed", "mnemonic", "password"):
            continue
        if isinstance(v, (str, int, float, bool)):
            safe[k] = v
        elif isinstance(v, dict):
            safe[k] = _sanitize_details(v)
    return safe
