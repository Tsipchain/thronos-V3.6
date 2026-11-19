import os
from pathlib import Path
from unittest.mock import patch

import pytest

from services.btc_bridge_deposit_intent import (
    BridgeDepositIntentUnavailable,
    CORPORATE_REVENUE_ADDRESS,
    build_intent,
    is_valid_mainnet_address,
)


THR_ADDRESS = "THR" + "A" * 40
BRIDGE_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"


def _environment(**overrides):
    environment = {
        "BTC_BRIDGE_INBOUND_ENABLED": "true",
        "BTC_BRIDGE_INBOUND_ADDRESS_VERIFIED": "true",
        "BTC_BRIDGE_NETWORK": "main",
        "BTC_BRIDGE_INBOUND_ADDRESS": BRIDGE_ADDRESS,
        "BTC_BRIDGE_INTENT_SIGNING_SECRET": "s" * 32,
        "BTC_BRIDGE_CONFIRMATIONS_REQUIRED": "6",
        "BTC_BRIDGE_INTENT_TTL_SECONDS": "300",
        "BTC_BRIDGE_CONFIG_VERSION": "bridge-address-v1",
    }
    environment.update(overrides)
    return environment


def test_mainnet_address_validation_checks_checksum_and_network():
    assert is_valid_mainnet_address(BRIDGE_ADDRESS) is True
    assert is_valid_mainnet_address(CORPORATE_REVENUE_ADDRESS) is True
    assert is_valid_mainnet_address(BRIDGE_ADDRESS[:-1] + "b") is False
    assert is_valid_mainnet_address("mk2QpYatsKicvFVuTAQLBryyccRXMUaGHP") is False


def test_complete_shared_address_configuration_still_fails_attribution_closed():
    with pytest.raises(
        BridgeDepositIntentUnavailable,
        match="^bridge_deposit_attribution_unavailable$",
    ):
        build_intent(THR_ADDRESS, environ=_environment(), now=1_700_000_000)


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"BTC_BRIDGE_INBOUND_ENABLED": "false"}, "bridge_inbound_disabled"),
        ({"BTC_BRIDGE_INBOUND_ADDRESS_VERIFIED": "false"}, "bridge_address_not_operator_verified"),
        ({"BTC_BRIDGE_NETWORK": "test"}, "bridge_network_not_mainnet"),
        ({"BTC_BRIDGE_INBOUND_ADDRESS": "not-a-bitcoin-address"}, "bridge_address_invalid"),
        ({"BTC_BRIDGE_CONFIRMATIONS_REQUIRED": "5"}, "bridge_confirmations_below_minimum"),
        ({"BTC_BRIDGE_INTENT_SIGNING_SECRET": "short"}, "bridge_intent_secret_missing"),
        ({"BTC_BRIDGE_CONFIG_VERSION": ""}, "bridge_config_version_missing"),
    ],
)
def test_incomplete_or_unsafe_configuration_fails_closed(override, reason):
    with pytest.raises(BridgeDepositIntentUnavailable, match=reason):
        build_intent(THR_ADDRESS, environ=_environment(**override), now=1_700_000_000)


def test_corporate_revenue_address_can_never_be_reused_for_bridge():
    with pytest.raises(BridgeDepositIntentUnavailable, match="bridge_address_role_conflict"):
        build_intent(
            THR_ADDRESS,
            environ=_environment(BTC_BRIDGE_INBOUND_ADDRESS=CORPORATE_REVENUE_ADDRESS),
            now=1_700_000_000,
        )


@pytest.mark.parametrize(
    "role_variable",
    [
        "BTC_PROVIDER_REVENUE_ADDRESS",
        "BTC_EARN_PROVIDER_REVENUE_ADDRESS",
        "BTC_PLEDGE_VAULT",
        "BTC_PLEDGE_VAULT_ADDRESS",
        "BTC_HOT_WALLET",
        "BTC_BRIDGE_HOT_ADDRESS",
        "BTC_EARN_HOT_ADDRESS",
        "BTC_SETTLEMENT_RESERVE",
        "BTC_SETTLEMENT_RESERVE_ADDRESS",
        "BTC_TREASURY",
        "BTC_TREASURY_ADDRESS",
        "BTC_OFFLINE_TREASURY_ADDRESS",
    ],
)
def test_named_custody_role_address_cannot_be_reused_for_bridge(role_variable):
    with pytest.raises(BridgeDepositIntentUnavailable, match="bridge_address_role_conflict"):
        build_intent(
            THR_ADDRESS,
            environ=_environment(**{role_variable: BRIDGE_ADDRESS}),
            now=1_700_000_000,
        )


def test_operator_registered_incompatible_custody_role_cannot_be_reused():
    registry = '{"independent_cold_role":"' + BRIDGE_ADDRESS + '"}'
    with pytest.raises(
        BridgeDepositIntentUnavailable,
        match="^bridge_address_role_conflict$",
    ):
        build_intent(
            THR_ADDRESS,
            environ=_environment(BTC_BRIDGE_INCOMPATIBLE_CUSTODY_ROLES=registry),
            now=1_700_000_000,
        )


@pytest.mark.parametrize("registry", ["not-json", "[]", '{"role":"invalid"}'])
def test_invalid_operator_custody_registry_fails_closed_without_values(registry):
    with pytest.raises(BridgeDepositIntentUnavailable) as exc_info:
        build_intent(
            THR_ADDRESS,
            environ=_environment(BTC_BRIDGE_INCOMPATIBLE_CUSTODY_ROLES=registry),
            now=1_700_000_000,
        )
    assert str(exc_info.value) == "bridge_incompatible_custody_roles_invalid"
    assert registry not in str(exc_info.value)


def test_deposit_endpoint_is_disabled_by_default_and_never_returns_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("EDU_DB_PATH", str(tmp_path / "l2e_edu.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "0")
    for key in tuple(os.environ):
        if key.startswith("BTC_BRIDGE_"):
            monkeypatch.delenv(key, raising=False)
    import server

    response = server.app.test_client().get(f"/api/bridge/deposit?wallet={THR_ADDRESS}")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload == {
        "attribution_ready": False,
        "error": "bridge_inbound_disabled",
        "ok": False,
        "paid_deposit_enabled": False,
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert "bc1qthronos" not in response.get_data(as_text=True)


def test_deposit_endpoint_never_exposes_shared_address_as_attributed(monkeypatch, tmp_path):
    monkeypatch.setenv("EDU_DB_PATH", str(tmp_path / "l2e_edu.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "0")
    import server

    with patch.dict(os.environ, _environment(), clear=False):
        response = server.app.test_client().get(f"/api/bridge/deposit?wallet={THR_ADDRESS}")
    assert response.status_code == 503
    payload = response.get_json()
    assert payload == {
        "attribution_ready": False,
        "error": "bridge_deposit_attribution_unavailable",
        "ok": False,
        "paid_deposit_enabled": False,
    }
    assert BRIDGE_ADDRESS not in response.get_data(as_text=True)


def test_bridge_status_and_withdrawals_fail_closed_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("EDU_DB_PATH", str(tmp_path / "l2e_edu.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "0")
    monkeypatch.delenv("BRIDGE_MODE", raising=False)
    monkeypatch.delenv("BTC_BRIDGE_WITHDRAWALS_ENABLED", raising=False)
    import server

    client = server.app.test_client()
    status = client.get("/api/bridge/status")
    assert status.status_code == 200
    assert status.get_json()["mode"] == "disabled"
    assert status.get_json()["ok"] is False

    for endpoint in ("/api/bridge/burn", "/api/bridge/withdraw"):
        response = client.post(endpoint, json={})
        assert response.status_code == 503
        assert response.get_json()["error"] == "bridge_withdrawals_disabled"


def test_bridge_template_has_no_fake_address_fixed_rate_or_three_confirmation_promise():
    template = (Path(__file__).parents[1] / "templates" / "bridge.html").read_text(encoding="utf-8")
    assert "bc1qthronos_bridge_mainnet_deposit" not in template
    assert "1 THR = 0.0001 BTC" not in template
    assert "1 BTC = 10,000 THR" not in template
    assert "Confirmations: 3" not in template
    assert "loadDepositIntent()" in template


def test_wallet_bridge_entry_points_are_non_executable_without_authoritative_service():
    root = Path(__file__).parents[1]
    pwa = (root / "public" / "wallet-pwa" / "app.js").read_text(encoding="utf-8")
    native = (root / "thronos-wallet-app" / "src" / "screens" / "BridgeScreen.tsx").read_text(encoding="utf-8")

    bridge_section = pwa[pwa.index("const _BRIDGE_PAIRS"):pwa.index("// ─── Music screen")]
    assert "available:true" not in bridge_section
    assert "private_key_hex" not in bridge_section
    assert "/api/bridge/execute" not in bridge_section

    pair_section = native[native.index("const BRIDGE_PAIRS"):native.index("// No mock data")]
    assert "available: true" not in pair_section
    assert "executeBridgeSigned" not in native
    assert "signThronosTransaction" not in native
