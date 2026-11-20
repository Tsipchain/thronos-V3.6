"""Cryptographic verification for Wallet V1 service request envelopes.

This module deliberately does not create wallets, derive pledge credentials, or
mutate wallet/pledge records.  It only verifies an already-built request.  The
two historical browser serializations are kept explicit because changing their
canonical bytes would invalidate signatures made by deployed clients.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

from wallet_v1_address_derivation import derive_thronos_address, validate_thronos_address


LEGACY_WEB_CONTRACT = "wallet_v1_web_compact_v1"
ADAPTER_CONTRACT = "wallet_v1_adapter_compact_v1"
MAX_CLOCK_SKEW_SECONDS = 300
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def normalize_secp256k1_public_key_hex(public_key: Any) -> Optional[str]:
    """Return validated secp256k1 SEC1 hex, or ``None``.

    Historical clients may send compressed or uncompressed SEC1 points and may
    include a ``0x`` prefix.  Point validation is performed by OpenSSL, not just
    by checking the prefix and length.
    """

    if not isinstance(public_key, str):
        return None
    normalized = public_key.strip()
    if normalized[:2].lower() == "0x":
        normalized = normalized[2:]
    if not _HEX_RE.fullmatch(normalized or ""):
        return None
    if not (
        (len(normalized) == 66 and normalized[:2] in ("02", "03"))
        or (len(normalized) == 130 and normalized[:2] == "04")
    ):
        return None
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), bytes.fromhex(normalized))
    except (ValueError, TypeError):
        return None
    return normalized.lower()


def compressed_public_key_hex(public_key: str) -> str:
    """Normalize a valid SEC1 key to the compressed form used by THR addresses."""

    key_obj = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256K1(), bytes.fromhex(public_key)
    )
    numbers = key_obj.public_numbers()
    prefix = "02" if numbers.y % 2 == 0 else "03"
    return prefix + f"{numbers.x:064x}"


def derive_thr_address_from_public_key_hex(public_key: str) -> str:
    """Derive the existing canonical THR address without changing its algorithm."""

    return derive_thronos_address(compressed_public_key_hex(public_key))


def _legacy_replacer_value(value: Any, allowed_keys: tuple[str, ...]) -> Any:
    """Emulate JSON.stringify(value, Object.keys(topLevel).sort()).

    The array replacer is applied recursively by JavaScript.  This odd deployed
    behavior normally reduces the inner action payload to ``{}`` and is retained
    byte-for-byte for ``secp256k1_compact`` requests.
    """

    if isinstance(value, Mapping):
        return {
            key: _legacy_replacer_value(value[key], allowed_keys)
            for key in allowed_keys
            if key in value
        }
    if isinstance(value, list):
        return [_legacy_replacer_value(item, allowed_keys) for item in value]
    return value


def canonical_signed_request_bytes(request_json: Mapping[str, Any]) -> Tuple[bytes, str]:
    """Return the exact signed bytes and the identified compatibility contract."""

    # The first deployed web helper predated the signature_format field.  Its
    # server verifier used the same legacy canonical bytes, so absence maps only
    # to that exact contract.  It must never be guessed as the payload-binding
    # adapter contract.
    signature_format = str(
        request_json.get("signature_format") or "secp256k1_compact"
    ).strip()
    action = str(request_json.get("action") or "").strip().lower()
    canonical = str(request_json.get("canonical_v1_address") or "").strip()
    nonce = str(request_json.get("nonce") or "").strip()
    timestamp = request_json.get("timestamp")
    payload = request_json.get("payload")
    if payload is None:
        payload = {}

    if signature_format == "secp256k1_compact":
        # Exact deployed templates/base.html contract.  Do not replace with a
        # conventional nested canonical JSON encoding without a new version.
        signing_payload = {
            "action": action,
            "canonical_v1_address": canonical,
            "timestamp": timestamp,
            "nonce": nonce,
            "payload": payload,
        }
        allowed = tuple(sorted(signing_payload))
        signing_payload = _legacy_replacer_value(signing_payload, allowed)
        encoded = json.dumps(signing_payload, ensure_ascii=False, separators=(",", ":"))
        return encoded.encode("utf-8"), LEGACY_WEB_CONTRACT

    if signature_format == "compact_secp256k1_hex":
        # Existing static/wallet_v1_signer.js insertion order.
        signing_payload = {
            "action": str(request_json.get("action") or "").strip(),
            "canonical_v1_address": canonical,
            "payload": payload,
            "timestamp": timestamp,
            "nonce": nonce,
        }
        encoded = json.dumps(signing_payload, ensure_ascii=False, separators=(",", ":"))
        return encoded.encode("utf-8"), ADAPTER_CONTRACT

    raise ValueError("unsupported_signature_format")


def _parse_timestamp(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


def _verify_compact_signature(public_key: str, signature: str, message: bytes) -> bool:
    try:
        signature_bytes = bytes.fromhex(signature)
        if len(signature_bytes) != 64:
            return False
        r = int.from_bytes(signature_bytes[:32], "big")
        s = int.from_bytes(signature_bytes[32:], "big")
        if r == 0 or s == 0:
            return False
        der_signature = utils.encode_dss_signature(r, s)
        key_obj = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256K1(), bytes.fromhex(public_key)
        )
        key_obj.verify(der_signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_signed_request(
    request_json: Mapping[str, Any],
    expected_action: str,
    *,
    binding_lookup: Callable[[str], Optional[Mapping[str, Any]]],
    nonce_guard: Callable[[str, str, float], Tuple[bool, str]],
    now: Optional[float] = None,
    max_clock_skew_seconds: int = MAX_CLOCK_SKEW_SECONDS,
) -> Tuple[bool, dict[str, Any]]:
    """Verify structure, ECDSA, identity binding, freshness, and replay state."""

    diagnostics = {
        "has_public_key": bool(request_json.get("public_key")),
        "has_signature": bool(request_json.get("signature")),
        "signature_format": str(request_json.get("signature_format") or ""),
        "has_active_binding": False,
    }
    canonical_v1_address = str(request_json.get("canonical_v1_address") or "").strip()
    action = str(request_json.get("action") or "").strip()
    public_key_raw = request_json.get("public_key")
    signature = str(request_json.get("signature") or "").strip()
    nonce = str(request_json.get("nonce") or "").strip()

    if not validate_thronos_address(canonical_v1_address):
        return False, {"error": "invalid_canonical_address", "diagnostics": diagnostics}
    if action.lower().replace("-", "_").replace(" ", "_") != str(expected_action).lower().replace("-", "_").replace(" ", "_"):
        return False, {"error": "action_mismatch", "diagnostics": diagnostics}

    public_key = normalize_secp256k1_public_key_hex(public_key_raw)
    if public_key is None:
        error = "missing_public_key" if not public_key_raw else "invalid_public_key_format"
        return False, {"error": error, "diagnostics": diagnostics}
    if len(signature) != 128 or not _HEX_RE.fullmatch(signature):
        return False, {"error": "invalid_signature_format", "diagnostics": diagnostics}
    if not nonce or len(nonce) > 128:
        return False, {"error": "invalid_nonce", "diagnostics": diagnostics}

    timestamp = _parse_timestamp(request_json.get("timestamp"))
    if timestamp is None:
        return False, {"error": "invalid_timestamp", "diagnostics": diagnostics}
    current_time = datetime.now(timezone.utc).timestamp() if now is None else float(now)
    if abs(current_time - timestamp) > max_clock_skew_seconds:
        return False, {"error": "timestamp_out_of_range", "diagnostics": diagnostics}

    try:
        signed_bytes, signature_contract = canonical_signed_request_bytes(request_json)
    except ValueError as exc:
        return False, {"error": str(exc), "diagnostics": diagnostics}

    claimed_hash = request_json.get("signing_payload_hash")
    actual_hash = hashlib.sha256(signed_bytes).hexdigest()
    if isinstance(claimed_hash, str) and claimed_hash and claimed_hash.lower() != actual_hash:
        return False, {"error": "signing_payload_hash_mismatch", "diagnostics": diagnostics}
    if not _verify_compact_signature(public_key, signature, signed_bytes):
        return False, {"error": "invalid_signature", "diagnostics": diagnostics}

    signer_address = derive_thr_address_from_public_key_hex(public_key)
    is_bound_signer = signer_address != canonical_v1_address
    active_binding: Optional[Mapping[str, Any]] = None
    if is_bound_signer:
        active_binding = binding_lookup(canonical_v1_address)
        diagnostics["has_active_binding"] = active_binding is not None
        if not active_binding:
            return False, {"error": "no_active_binding", "diagnostics": diagnostics}
        binding_public_key = normalize_secp256k1_public_key_hex(active_binding.get("public_key"))
        if binding_public_key != public_key:
            return False, {"error": "public_key_mismatch", "diagnostics": diagnostics}
        binding_address = str(active_binding.get("public_key_address") or "").strip().upper()
        if binding_address and binding_address != signer_address:
            return False, {"error": "binding_address_mismatch", "diagnostics": diagnostics}
        claimed_bound = str(request_json.get("bound_key_address") or "").strip().upper()
        if claimed_bound and claimed_bound != signer_address:
            return False, {"error": "bound_key_address_mismatch", "diagnostics": diagnostics}
    else:
        # Direct wallet: its signing public key still has to derive to the
        # authoritative canonical address.  No binding record is required.
        claimed_bound = str(request_json.get("bound_key_address") or "").strip().upper()
        if claimed_bound and claimed_bound != signer_address:
            return False, {"error": "bound_key_address_mismatch", "diagnostics": diagnostics}

    nonce_ok, nonce_error = nonce_guard(canonical_v1_address, nonce, timestamp)
    if not nonce_ok:
        return False, {"error": nonce_error or "nonce_replay_detected", "diagnostics": diagnostics}

    return True, {
        "canonical_v1_address": canonical_v1_address,
        "public_key": public_key,
        "bound_key_address": signer_address if is_bound_signer else None,
        "signer_address": signer_address,
        "is_bound_signer": is_bound_signer,
        "action": action,
        "signature_contract": signature_contract,
        "payload_cryptographically_bound": signature_contract == ADAPTER_CONTRACT,
        "diagnostics": diagnostics,
    }
