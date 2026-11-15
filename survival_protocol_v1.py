"""M0 canonical envelopes for offline Thronos survival relays.

This module deliberately stops at signed-message validation.  It does not
submit transactions, alter balances, reserve collateral, or claim external
Bitcoin/Ethereum settlement.  Transports can carry the JSON or canonical byte
representation without learning a private key.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ecdsa import SECP256k1, SigningKey, VerifyingKey
from ecdsa.errors import MalformedPointError
from ecdsa.keys import BadSignatureError
from ecdsa.util import sigdecode_der, sigencode_der


PROTOCOL = "thronos-survival-envelope"
VERSION = 1
DOMAIN = b"THRONOS/SURVIVAL/M0\x00"
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_ETH = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BTC = re.compile(r"^(bc1|tb1|bcrt1|[13mn2])[A-Za-z0-9]{10,90}$")
_THR = re.compile(r"^THR[A-Za-z0-9._:-]{5,127}$")


class EnvelopeError(ValueError):
    """A malformed, invalid, expired, or conflicting envelope."""


class Lifecycle(str, Enum):
    DRAFT = "draft"
    LOCALLY_SIGNED = "locally_signed"
    DELIVERED_TO_PEER = "delivered_to_peer"
    MESH_ACKNOWLEDGED = "mesh_acknowledged"
    NETWORK_SUBMITTED = "network_submitted"
    CHAIN_CONFIRMED = "chain_confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONFLICTED = "conflicted"


_TERMINAL = {
    Lifecycle.CHAIN_CONFIRMED,
    Lifecycle.REJECTED,
    Lifecycle.EXPIRED,
    Lifecycle.CONFLICTED,
}
_TRANSITIONS = {
    Lifecycle.DRAFT: {Lifecycle.LOCALLY_SIGNED, Lifecycle.REJECTED},
    Lifecycle.LOCALLY_SIGNED: {
        Lifecycle.DELIVERED_TO_PEER,
        Lifecycle.NETWORK_SUBMITTED,
        Lifecycle.REJECTED,
        Lifecycle.EXPIRED,
        Lifecycle.CONFLICTED,
    },
    Lifecycle.DELIVERED_TO_PEER: {
        Lifecycle.MESH_ACKNOWLEDGED,
        Lifecycle.NETWORK_SUBMITTED,
        Lifecycle.REJECTED,
        Lifecycle.EXPIRED,
        Lifecycle.CONFLICTED,
    },
    Lifecycle.MESH_ACKNOWLEDGED: {
        Lifecycle.NETWORK_SUBMITTED,
        Lifecycle.REJECTED,
        Lifecycle.EXPIRED,
        Lifecycle.CONFLICTED,
    },
    Lifecycle.NETWORK_SUBMITTED: {
        Lifecycle.CHAIN_CONFIRMED,
        Lifecycle.REJECTED,
        Lifecycle.EXPIRED,
        Lifecycle.CONFLICTED,
    },
    Lifecycle.CHAIN_CONFIRMED: set(),
    Lifecycle.REJECTED: set(),
    Lifecycle.EXPIRED: set(),
    Lifecycle.CONFLICTED: set(),
}


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EnvelopeError(f"{field} must be an integer >= {minimum}")
    return value


def _address_ok(asset_id: str, address: str) -> bool:
    if asset_id == "THR":
        return bool(_THR.fullmatch(address))
    if asset_id == "BTC":
        return bool(_BTC.fullmatch(address))
    if asset_id == "ETH":
        return bool(_ETH.fullmatch(address))
    return bool(address) and len(address) <= 128


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class Checkpoint:
    height: int
    block_hash: str

    def __post_init__(self) -> None:
        _require_int(self.height, "checkpoint.height")
        if not _HEX64.fullmatch(self.block_hash):
            raise EnvelopeError("checkpoint.block_hash must be 32-byte hex")

    def as_dict(self) -> dict[str, Any]:
        return {"block_hash": self.block_hash.lower(), "height": self.height}


@dataclass(frozen=True)
class Envelope:
    chain_id: str
    asset_id: str
    sender: str
    recipient: str
    amount_units: int
    fee_units: int
    nonce: int
    message_id: str
    issued_at: int
    expires_at: int
    checkpoint: Checkpoint
    public_key: str
    signature: str
    lifecycle: Lifecycle = Lifecycle.LOCALLY_SIGNED
    version: int = VERSION
    protocol: str = PROTOCOL

    def __post_init__(self) -> None:
        if isinstance(self.checkpoint, dict):
            object.__setattr__(self, "checkpoint", Checkpoint(**self.checkpoint))
        if self.protocol != PROTOCOL or self.version != VERSION:
            raise EnvelopeError("unsupported protocol version")
        if not self.chain_id or len(self.chain_id) > 128:
            raise EnvelopeError("chain_id is required and must be <=128 characters")
        if self.asset_id not in {"THR", "BTC", "ETH"}:
            raise EnvelopeError("unsupported asset_id")
        if not _address_ok(self.asset_id, self.sender):
            raise EnvelopeError("sender does not match asset boundary")
        if not _address_ok(self.asset_id, self.recipient):
            raise EnvelopeError("recipient does not match asset boundary")
        _require_int(self.amount_units, "amount_units", minimum=1)
        _require_int(self.fee_units, "fee_units")
        _require_int(self.nonce, "nonce", minimum=0)
        if self.fee_units > self.amount_units:
            raise EnvelopeError("fee_units cannot exceed amount_units")
        try:
            parsed_id = uuid.UUID(self.message_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise EnvelopeError("message_id must be a UUID") from exc
        if parsed_id.int == 0:
            raise EnvelopeError("message_id cannot be nil")
        _require_int(self.issued_at, "issued_at")
        _require_int(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise EnvelopeError("expires_at must be after issued_at")
        if len(self.public_key) != 66 or not re.fullmatch(r"[0-9a-fA-F]{66}", self.public_key):
            raise EnvelopeError("public_key must be a compressed secp256k1 key")
        if not self.signature or not re.fullmatch(r"[0-9a-fA-F]+", self.signature):
            raise EnvelopeError("signature must be hex")
        if not isinstance(self.lifecycle, Lifecycle):
            object.__setattr__(self, "lifecycle", Lifecycle(self.lifecycle))

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "amount_units": self.amount_units,
            "asset_id": self.asset_id,
            "chain_id": self.chain_id,
            "checkpoint": self.checkpoint.as_dict(),
            "expires_at": self.expires_at,
            "fee_units": self.fee_units,
            "issued_at": self.issued_at,
            "message_id": self.message_id,
            "nonce": self.nonce,
            "protocol": self.protocol,
            "recipient": self.recipient,
            "sender": self.sender,
            "version": self.version,
        }

    def canonical_bytes(self) -> bytes:
        return DOMAIN + _canonical_json(self.unsigned_dict())

    def as_dict(self) -> dict[str, Any]:
        data = self.unsigned_dict()
        data.update({
            "lifecycle": self.lifecycle.value,
            "public_key": self.public_key.lower(),
            "signature": self.signature.lower(),
        })
        return data

    def to_json(self) -> str:
        return _canonical_json(self.as_dict()).decode("utf-8")

    def verify_signature(self, now: int | None = None) -> None:
        try:
            key = VerifyingKey.from_string(bytes.fromhex(self.public_key), curve=SECP256k1)
            signature = bytes.fromhex(self.signature)
            if not key.verify_digest(signature, hashlib.sha256(self.canonical_bytes()).digest(), sigdecode=sigdecode_der):
                raise EnvelopeError("invalid signature")
        except (BadSignatureError, MalformedPointError, ValueError) as exc:
            raise EnvelopeError("invalid signature") from exc
        if now is not None:
            if now < self.issued_at:
                raise EnvelopeError("issued_at is in the future")
            if now >= self.expires_at:
                raise EnvelopeError("envelope expired")

    def transition(self, new_state: Lifecycle) -> "Envelope":
        new_state = Lifecycle(new_state)
        if new_state not in _TRANSITIONS[self.lifecycle]:
            raise EnvelopeError(f"invalid lifecycle transition {self.lifecycle.value}->{new_state.value}")
        return Envelope(**{**self.as_dict(), "lifecycle": new_state})

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Envelope":
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError
            checkpoint = data.pop("checkpoint")
            data["checkpoint"] = Checkpoint(**checkpoint)
            data["lifecycle"] = Lifecycle(data.get("lifecycle", Lifecycle.LOCALLY_SIGNED.value))
            allowed = set(cls.__dataclass_fields__)
            if set(data) != allowed:
                raise EnvelopeError("unexpected or missing envelope fields")
            return cls(**data)
        except EnvelopeError:
            raise
        except (TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise EnvelopeError("malformed envelope JSON") from exc


def sign_envelope(
    *,
    chain_id: str,
    asset_id: str,
    sender: str,
    recipient: str,
    amount_units: int,
    fee_units: int,
    nonce: int,
    message_id: str,
    issued_at: int,
    expires_at: int,
    checkpoint: Checkpoint,
    private_key_hex: str,
) -> Envelope:
    """Create a locally signed envelope; private_key_hex is never returned."""
    try:
        raw_key = bytes.fromhex(private_key_hex)
        if len(raw_key) != 32:
            raise ValueError
        key = SigningKey.from_string(raw_key, curve=SECP256k1)
    except (ValueError, TypeError) as exc:
        raise EnvelopeError("private key must be 32-byte hex") from exc
    unsigned = Envelope(
        chain_id=chain_id,
        asset_id=asset_id,
        sender=sender,
        recipient=recipient,
        amount_units=amount_units,
        fee_units=fee_units,
        nonce=nonce,
        message_id=message_id,
        issued_at=issued_at,
        expires_at=expires_at,
        checkpoint=checkpoint,
        public_key=key.verifying_key.to_string(encoding="compressed").hex(),
        signature="00",
    )
    signature = key.sign_digest_deterministic(
        hashlib.sha256(unsigned.canonical_bytes()).digest(),
        hashfunc=hashlib.sha256,
        sigencode=sigencode_der,
    ).hex()
    return Envelope(
        **{**unsigned.as_dict(), "checkpoint": checkpoint, "signature": signature}
    )


class ReplayGuard:
    """In-memory M0 duplicate/nonce guard for one local verifier.

    Persistence and multi-node reconciliation are intentionally deferred to a
    later transport/storage PR. A caller must persist accepted IDs atomically
    with its local pending ledger before treating a relay as accepted.
    """

    def __init__(self) -> None:
        self._message_ids: set[str] = set()
        self._nonces: set[tuple[str, int]] = set()

    def accept(self, envelope: Envelope, *, now: int | None = None) -> None:
        envelope.verify_signature(now=now)
        key = (envelope.sender, envelope.nonce)
        if envelope.message_id in self._message_ids:
            raise EnvelopeError("duplicate message_id")
        if key in self._nonces:
            raise EnvelopeError("duplicate sender nonce")
        self._message_ids.add(envelope.message_id)
        self._nonces.add(key)
