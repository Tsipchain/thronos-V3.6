import pytest

from services.btc_custody_policy import (
    BRIDGE_HOT,
    BRIDGE_WATCH,
    EARN_HOT,
    EXTERNAL_SIGNER,
    OFFLINE,
    OFFLINE_TREASURY,
    SETTLEMENT_RESERVE,
    WATCH_ONLY,
    BtcCustodyPolicyError,
    CustodyAssignment,
    validate_custody_configuration,
)


def assignments(**addresses):
    values = {
        BRIDGE_HOT: "bc1qbridgehot00000000000000000000000000000",
        EARN_HOT: "bc1qearnhot0000000000000000000000000000000",
        BRIDGE_WATCH: "bc1qbridgewatch000000000000000000000000000",
        OFFLINE_TREASURY: "bc1qoffline000000000000000000000000000000",
        SETTLEMENT_RESERVE: "bc1qreserve000000000000000000000000000000",
    }
    values.update(addresses)
    modes = {
        BRIDGE_HOT: EXTERNAL_SIGNER,
        EARN_HOT: EXTERNAL_SIGNER,
        BRIDGE_WATCH: WATCH_ONLY,
        OFFLINE_TREASURY: OFFLINE,
        SETTLEMENT_RESERVE: WATCH_ONLY,
    }
    return [
        CustodyAssignment(role, address, "main", modes[role])
        for role, address in values.items()
    ]


def validator(address):
    return {
        "isvalid": address.startswith("bc1q"),
        "network": "main",
        "iswatchonly": "watch" in address or "reserve" in address,
        "has_private_keys": False,
    }


def test_distinct_custody_roles_are_validated_without_keys():
    result = validate_custody_configuration(
        assignments(), address_validator=validator
    )
    assert set(result) == {
        BRIDGE_HOT,
        EARN_HOT,
        BRIDGE_WATCH,
        OFFLINE_TREASURY,
        SETTLEMENT_RESERVE,
    }


def test_bridge_hot_and_earn_hot_can_never_share_an_address():
    shared = "bc1qsharedhot00000000000000000000000000000"
    with pytest.raises(BtcCustodyPolicyError, match="incompatible_address_reuse"):
        validate_custody_configuration(
            assignments(**{BRIDGE_HOT: shared, EARN_HOT: shared}),
            address_validator=validator,
            allowed_shared_roles=[frozenset({BRIDGE_HOT, EARN_HOT})],
        )


def test_watch_and_reserve_share_only_with_explicit_policy():
    shared = "bc1qwatchreserve00000000000000000000000000"
    config = assignments(**{BRIDGE_WATCH: shared, SETTLEMENT_RESERVE: shared})
    with pytest.raises(BtcCustodyPolicyError, match="reuse_not_allowed"):
        validate_custody_configuration(config, address_validator=validator)
    result = validate_custody_configuration(
        config,
        address_validator=validator,
        allowed_shared_roles=[frozenset({BRIDGE_WATCH, SETTLEMENT_RESERVE})],
    )
    assert result[BRIDGE_WATCH].address == result[SETTLEMENT_RESERVE].address


def test_offline_treasury_cannot_share_even_with_override():
    shared = "bc1qofflinewatch0000000000000000000000000"
    with pytest.raises(BtcCustodyPolicyError, match="incompatible_address_reuse"):
        validate_custody_configuration(
            assignments(**{OFFLINE_TREASURY: shared, BRIDGE_WATCH: shared}),
            address_validator=validator,
            allowed_shared_roles=[frozenset({OFFLINE_TREASURY, BRIDGE_WATCH})],
        )


def test_wrong_network_mode_or_invalid_address_fails_closed():
    base = assignments()
    wrong_network = [
        CustodyAssignment(item.role, item.address, "test", item.mode)
        if item.role == BRIDGE_HOT else item
        for item in base
    ]
    with pytest.raises(BtcCustodyPolicyError, match="network_mismatch"):
        validate_custody_configuration(wrong_network, address_validator=validator)

    wrong_mode = [
        CustodyAssignment(item.role, item.address, item.network, WATCH_ONLY)
        if item.role == BRIDGE_HOT else item
        for item in base
    ]
    with pytest.raises(BtcCustodyPolicyError, match="mode_mismatch"):
        validate_custody_configuration(wrong_mode, address_validator=validator)

    invalid = [
        CustodyAssignment(item.role, "not-bitcoin", item.network, item.mode)
        if item.role == BRIDGE_HOT else item
        for item in base
    ]
    with pytest.raises(BtcCustodyPolicyError, match="address_invalid"):
        validate_custody_configuration(invalid, address_validator=validator)


def test_watch_roles_require_watch_only_evidence_and_no_private_keys():
    def not_watch_only(address):
        result = validator(address)
        result["iswatchonly"] = False
        return result

    with pytest.raises(BtcCustodyPolicyError, match="not_watch_only"):
        validate_custody_configuration(
            assignments(), address_validator=not_watch_only
        )

    def leaked_private_key_evidence(address):
        result = validator(address)
        result["has_private_keys"] = address.startswith("bc1qbridgehot")
        return result

    with pytest.raises(BtcCustodyPolicyError, match="private_key_evidence_forbidden"):
        validate_custody_configuration(
            assignments(), address_validator=leaked_private_key_evidence
        )
