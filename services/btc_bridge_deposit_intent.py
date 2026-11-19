"""Fail-closed, purpose-bound configuration for BTC bridge deposit intents.

This module does not watch Bitcoin, credit a ledger, mint an asset, or sign a
transaction.  It only exposes a short-lived, authenticated description of an
operator-verified bridge receiving address.  Settlement remains disabled.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Mapping


PURPOSE = "bridge_inbound"
NETWORK = "main"
MIN_CONFIRMATIONS = 6
CORPORATE_REVENUE_ADDRESS = "1N5ddgzVp5it6FgxninDD1R56Rh72D9HKy"

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_INCOMPATIBLE_ADDRESS_VARS = (
    "BTC_PROVIDER_REVENUE_ADDRESS",
    "BTC_EARN_PROVIDER_REVENUE_ADDRESS",
    "BTC_PLEDGE_VAULT_ADDRESS",
    "BTC_BRIDGE_HOT_ADDRESS",
    "BTC_EARN_HOT_ADDRESS",
    "BTC_SETTLEMENT_RESERVE_ADDRESS",
    "BTC_OFFLINE_TREASURY_ADDRESS",
)


class BridgeDepositIntentUnavailable(RuntimeError):
    """Raised when the operator has not supplied safe bridge configuration."""


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _decode_base58check(address: str) -> bytes | None:
    try:
        number = 0
        for char in address:
            number = number * 58 + _BASE58_ALPHABET.index(char)
        raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
        raw = b"\x00" * (len(address) - len(address.lstrip("1"))) + raw
        if len(raw) != 25:
            return None
        payload, checksum = raw[:-4], raw[-4:]
        expected = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        return payload if hmac.compare_digest(checksum, expected) else None
    except (ValueError, OverflowError):
        return None


def _bech32_polymod(values: list[int]) -> int:
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _valid_mainnet_segwit_address(address: str) -> bool:
    if address.lower() != address and address.upper() != address:
        return False
    candidate = address.lower()
    if not candidate.startswith("bc1") or candidate.rfind("1") < 1:
        return False
    separator = candidate.rfind("1")
    data_part = candidate[separator + 1 :]
    if len(candidate) > 90 or len(data_part) < 7:
        return False
    try:
        values = [_BECH32_ALPHABET.index(char) for char in data_part]
    except ValueError:
        return False
    version = values[0]
    if version > 16:
        return False
    expected_constant = 1 if version == 0 else 0x2BC830A3
    if _bech32_polymod(_bech32_hrp_expand("bc") + values) != expected_constant:
        return False

    accumulator = 0
    bits = 0
    program = bytearray()
    for value in values[1:-6]:
        accumulator = (accumulator << 5) | value
        bits += 5
        while bits >= 8:
            bits -= 8
            program.append((accumulator >> bits) & 0xFF)
    if bits >= 5 or ((accumulator << (8 - bits)) & 0xFF):
        return False
    if not 2 <= len(program) <= 40:
        return False
    return version != 0 or len(program) in {20, 32}


def is_valid_mainnet_address(address: str) -> bool:
    candidate = str(address or "").strip()
    payload = _decode_base58check(candidate)
    if payload is not None:
        return payload[0] in {0x00, 0x05}
    return _valid_mainnet_segwit_address(candidate)


@dataclass(frozen=True)
class BridgeDepositIntent:
    intent_id: str
    recipient: str
    address: str
    issued_at: int
    expires_at: int
    confirmations_required: int
    configuration_version: str
    proof: str

    def as_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "intent_version": 1,
            "configuration_version": self.configuration_version,
            "purpose": PURPOSE,
            "network": NETWORK,
            "recipient": self.recipient,
            "deposit_address": self.address,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "confirmations_required": self.confirmations_required,
            "proof": self.proof,
            "credit_authorized": False,
            "settlement_enabled": False,
            "payout_enabled": False,
        }


def build_intent(
    recipient: str,
    *,
    environ: Mapping[str, str] | None = None,
    now: int | None = None,
) -> BridgeDepositIntent:
    env = os.environ if environ is None else environ
    if not _enabled(env.get("BTC_BRIDGE_INBOUND_ENABLED")):
        raise BridgeDepositIntentUnavailable("bridge_inbound_disabled")
    if not _enabled(env.get("BTC_BRIDGE_INBOUND_ADDRESS_VERIFIED")):
        raise BridgeDepositIntentUnavailable("bridge_address_not_operator_verified")
    if str(env.get("BTC_BRIDGE_NETWORK", NETWORK)).strip().lower() != NETWORK:
        raise BridgeDepositIntentUnavailable("bridge_network_not_mainnet")

    address = str(env.get("BTC_BRIDGE_INBOUND_ADDRESS", "")).strip()
    if not is_valid_mainnet_address(address):
        raise BridgeDepositIntentUnavailable("bridge_address_invalid")
    if address == CORPORATE_REVENUE_ADDRESS:
        raise BridgeDepositIntentUnavailable("bridge_address_role_conflict")
    incompatible = {
        str(env.get(name, "")).strip()
        for name in _INCOMPATIBLE_ADDRESS_VARS
        if str(env.get(name, "")).strip()
    }
    if address in incompatible:
        raise BridgeDepositIntentUnavailable("bridge_address_role_conflict")

    signing_secret = str(env.get("BTC_BRIDGE_INTENT_SIGNING_SECRET", ""))
    if len(signing_secret.encode("utf-8")) < 32:
        raise BridgeDepositIntentUnavailable("bridge_intent_secret_missing")
    try:
        confirmations = int(env.get("BTC_BRIDGE_CONFIRMATIONS_REQUIRED", MIN_CONFIRMATIONS))
        ttl_seconds = int(env.get("BTC_BRIDGE_INTENT_TTL_SECONDS", 300))
    except (TypeError, ValueError) as exc:
        raise BridgeDepositIntentUnavailable("bridge_numeric_config_invalid") from exc
    if confirmations < MIN_CONFIRMATIONS:
        raise BridgeDepositIntentUnavailable("bridge_confirmations_below_minimum")
    if not 60 <= ttl_seconds <= 900:
        raise BridgeDepositIntentUnavailable("bridge_intent_ttl_invalid")

    configuration_version = str(env.get("BTC_BRIDGE_CONFIG_VERSION", "")).strip()
    if not configuration_version:
        raise BridgeDepositIntentUnavailable("bridge_config_version_missing")
    issued_at = int(time.time()) if now is None else int(now)
    expires_at = issued_at + ttl_seconds
    body = {
        "configuration_version": configuration_version,
        "confirmations_required": confirmations,
        "deposit_address": address,
        "expires_at": expires_at,
        "issued_at": issued_at,
        "network": NETWORK,
        "purpose": PURPOSE,
        "recipient": recipient,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    proof = hmac.new(signing_secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    intent_id = hashlib.sha256(canonical + proof.encode("ascii")).hexdigest()
    return BridgeDepositIntent(
        intent_id=intent_id,
        recipient=recipient,
        address=address,
        issued_at=issued_at,
        expires_at=expires_at,
        confirmations_required=confirmations,
        configuration_version=configuration_version,
        proof=proof,
    )
