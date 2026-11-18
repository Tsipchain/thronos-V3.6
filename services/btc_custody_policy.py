"""Enforce public-address role isolation without accessing signing material."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping


BRIDGE_HOT = "BridgeHot"
EARN_HOT = "EarnHot"
BRIDGE_WATCH = "BridgeWatch"
OFFLINE_TREASURY = "OfflineTreasury"
SETTLEMENT_RESERVE = "BtcSettlementReserve"

REQUIRED_ROLES = frozenset(
    {BRIDGE_HOT, EARN_HOT, BRIDGE_WATCH, OFFLINE_TREASURY, SETTLEMENT_RESERVE}
)

EXTERNAL_SIGNER = "external_signer"
WATCH_ONLY = "watch_only"
OFFLINE = "offline"

EXPECTED_MODES = {
    BRIDGE_HOT: EXTERNAL_SIGNER,
    EARN_HOT: EXTERNAL_SIGNER,
    BRIDGE_WATCH: WATCH_ONLY,
    OFFLINE_TREASURY: OFFLINE,
    SETTLEMENT_RESERVE: WATCH_ONLY,
}


class BtcCustodyPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CustodyAssignment:
    role: str
    address: str
    network: str
    mode: str


AddressValidator = Callable[[str], Mapping[str, object]]


def validate_custody_configuration(
    assignments: Iterable[CustodyAssignment],
    *,
    address_validator: AddressValidator,
    allowed_shared_roles: Iterable[frozenset[str]] = (),
) -> dict[str, CustodyAssignment]:
    """Validate role separation using read-only Bitcoin Core address evidence.

    ``address_validator`` is expected to wrap Bitcoin Core ``validateaddress``
    or equivalent trusted local evidence. No key, seed, descriptor or signing
    RPC is accepted by this interface.
    """
    by_role: dict[str, CustodyAssignment] = {}
    by_address: dict[str, list[CustodyAssignment]] = {}
    for assignment in assignments:
        if assignment.role not in REQUIRED_ROLES:
            raise BtcCustodyPolicyError("btc_custody_role_invalid")
        if assignment.role in by_role:
            raise BtcCustodyPolicyError("btc_custody_role_duplicate")
        address = str(assignment.address or "").strip()
        if not address:
            raise BtcCustodyPolicyError("btc_custody_address_missing")
        if assignment.network != "main":
            raise BtcCustodyPolicyError("btc_custody_network_mismatch")
        if assignment.mode != EXPECTED_MODES[assignment.role]:
            raise BtcCustodyPolicyError("btc_custody_mode_mismatch")
        evidence = address_validator(address)
        if not isinstance(evidence, Mapping) or evidence.get("isvalid") is not True:
            raise BtcCustodyPolicyError("btc_custody_address_invalid")
        if evidence.get("network") != "main":
            raise BtcCustodyPolicyError("btc_custody_address_network_mismatch")
        if assignment.mode == WATCH_ONLY and evidence.get("iswatchonly") is not True:
            raise BtcCustodyPolicyError("btc_custody_watch_role_not_watch_only")
        if evidence.get("has_private_keys") is True:
            raise BtcCustodyPolicyError("btc_custody_private_key_evidence_forbidden")
        normalized = CustodyAssignment(
            assignment.role, address, assignment.network, assignment.mode
        )
        by_role[assignment.role] = normalized
        by_address.setdefault(address, []).append(normalized)

    missing = REQUIRED_ROLES.difference(by_role)
    if missing:
        raise BtcCustodyPolicyError("btc_custody_roles_missing")

    allowed = {frozenset(pair) for pair in allowed_shared_roles}
    for shared in by_address.values():
        if len(shared) < 2:
            continue
        roles = frozenset(item.role for item in shared)
        if any(item.mode in (EXTERNAL_SIGNER, OFFLINE) for item in shared):
            raise BtcCustodyPolicyError("btc_custody_incompatible_address_reuse")
        if roles != frozenset({BRIDGE_WATCH, SETTLEMENT_RESERVE}) or roles not in allowed:
            raise BtcCustodyPolicyError("btc_custody_address_reuse_not_allowed")
    return by_role
