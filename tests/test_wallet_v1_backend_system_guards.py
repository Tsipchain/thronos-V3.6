"""
Tests for backend system wallet guards on migration/repair/resolve endpoints.
Ensures system wallets (AI/game/treasury/Pythia) are never accepted as user
migration sources or targets, regardless of env configuration.

Addresses issue #542.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch


SYSTEM_WALLET = "THR5DF27A86C477F381594E896F0E55357DEC5942BA"
USER_LEGACY = "THR79CA94A7EB70A6AA99D12D7FDB01446EF246301A"
USER_V1 = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"


# ───────────────────────────────────────────────────────────────────────────
# 1. Core is_system_wallet detection
# ───────────────────────────────────────────────────────────────────────────

class TestIsSystemWallet:

    def test_hardcoded_system_wallet_detected(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet(SYSTEM_WALLET) is True

    def test_case_insensitive(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet(SYSTEM_WALLET.lower()) is True

    def test_whitespace_stripped(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet("  " + SYSTEM_WALLET + "  ") is True

    def test_normal_user_wallet_not_system(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet(USER_LEGACY) is False
        assert is_system_wallet(USER_V1) is False

    def test_empty_or_none_not_system(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet("") is False
        assert is_system_wallet(None) is False


# ───────────────────────────────────────────────────────────────────────────
# 2. Each production system wallet role is covered
# ───────────────────────────────────────────────────────────────────────────

class TestEverySystemRoleCovered:
    """Verify each production system wallet source feeds into is_system_wallet."""

    def test_env_wallet_system_addresses(self):
        from wallet_v1_migration import is_system_wallet
        extra = "THREXTRA0000000000000000000000000000000000"
        with patch.dict(os.environ, {"WALLET_SYSTEM_ADDRESSES": extra}):
            assert is_system_wallet(extra) is True

    def test_env_thr_ai_agent_wallet(self):
        from wallet_v1_migration import is_system_wallet
        addr = "THRAI_AGENT_TEST_00000000000000000000000000"
        with patch.dict(os.environ, {"THR_AI_AGENT_WALLET": addr}):
            assert is_system_wallet(addr) is True

    def test_env_pythia_system_thr_address(self):
        from wallet_v1_migration import is_system_wallet
        addr = "THRPYTHIA_TEST_000000000000000000000000000000"
        with patch.dict(os.environ, {"PYTHIA_SYSTEM_THR_ADDRESS": addr}):
            assert is_system_wallet(addr) is True

    def test_env_ai_wallet_address(self):
        from wallet_v1_migration import is_system_wallet
        addr = "THRAI_SERVICES_TEST_000000000000000000000000"
        with patch.dict(os.environ, {"AI_WALLET_ADDRESS": addr}):
            assert is_system_wallet(addr) is True

    def test_env_treasury_wbtc_address_thr_format(self):
        from wallet_v1_migration import is_system_wallet
        addr = "THRTREASURY_WBTC_TEST_00000000000000000000000"
        with patch.dict(os.environ, {"TREASURY_WBTC_ADDRESS": addr}):
            assert is_system_wallet(addr) is True

    def test_non_thr_env_values_excluded(self):
        """Non-THR addresses (BTC, EVM) must not pollute the THR system set."""
        from wallet_v1_migration import _get_system_wallet_set
        with patch.dict(os.environ, {"TREASURY_WBTC_ADDRESS": "3KUGVJQ5tJWKY7GDVgwLjJ7EBzVWatD9nF"}):
            addrs = _get_system_wallet_set()
            assert "3KUGVJQ5TJWKY7GDVGWLJJ7EBZVWATD9NF" not in addrs

    def test_runtime_server_addresses_included(self):
        """is_system_wallet reads server.AI_WALLET_ADDRESS and PYTHIA_SYSTEM_THR_ADDRESS at runtime."""
        from wallet_v1_migration import _get_system_wallet_set
        import server
        ai_addr = getattr(server, 'AI_WALLET_ADDRESS', '')
        pythia_addr = getattr(server, 'PYTHIA_SYSTEM_THR_ADDRESS', '')
        addrs = _get_system_wallet_set()
        if ai_addr and ai_addr.upper().startswith('THR'):
            assert ai_addr.upper() in addrs
        if pythia_addr and pythia_addr.upper().startswith('THR'):
            assert pythia_addr.upper() in addrs

    def test_env_source_list_matches_code(self):
        """All env keys read by _get_system_wallet_set must match documented sources."""
        from wallet_v1_migration import _ENV_SYSTEM_WALLET_KEYS
        expected = {
            'WALLET_SYSTEM_ADDRESSES',
            'THR_AI_AGENT_WALLET',
            'PYTHIA_SYSTEM_THR_ADDRESS',
            'AI_WALLET_ADDRESS',
            'TREASURY_WBTC_ADDRESS',
        }
        assert set(_ENV_SYSTEM_WALLET_KEYS) == expected


# ───────────────────────────────────────────────────────────────────────────
# 3. Missing env entry MUST NOT allow system wallet through
# ───────────────────────────────────────────────────────────────────────────

class TestMissingEnvFallback:
    """A typo or missing env entry must not allow a system wallet to migrate."""

    def test_hardcoded_survives_empty_env(self):
        """Even with all env vars empty, the hardcoded address is still blocked."""
        from wallet_v1_migration import is_system_wallet
        env_overrides = {k: "" for k in (
            "WALLET_SYSTEM_ADDRESSES",
            "THR_AI_AGENT_WALLET",
            "PYTHIA_SYSTEM_THR_ADDRESS",
            "AI_WALLET_ADDRESS",
            "TREASURY_WBTC_ADDRESS",
        )}
        with patch.dict(os.environ, env_overrides, clear=False):
            assert is_system_wallet(SYSTEM_WALLET) is True

    def test_hardcoded_survives_unset_env(self):
        """Even if env vars are completely unset, hardcoded stays."""
        from wallet_v1_migration import is_system_wallet
        keys_to_remove = [
            "WALLET_SYSTEM_ADDRESSES",
            "THR_AI_AGENT_WALLET",
            "PYTHIA_SYSTEM_THR_ADDRESS",
            "AI_WALLET_ADDRESS",
            "TREASURY_WBTC_ADDRESS",
        ]
        env_copy = {k: v for k, v in os.environ.items() if k not in keys_to_remove}
        with patch.dict(os.environ, env_copy, clear=True):
            assert is_system_wallet(SYSTEM_WALLET) is True

    def test_comma_separated_env_multiple_addresses(self):
        from wallet_v1_migration import is_system_wallet
        addrs = "THRA000000000000000000000000000000000000000,THRB000000000000000000000000000000000000000"
        with patch.dict(os.environ, {"WALLET_SYSTEM_ADDRESSES": addrs}):
            assert is_system_wallet("THRA000000000000000000000000000000000000000") is True
            assert is_system_wallet("THRB000000000000000000000000000000000000000") is True


# ───────────────────────────────────────────────────────────────────────────
# 4. Migration rejection for system wallets
# ───────────────────────────────────────────────────────────────────────────

class TestMigrateRejectsSystemWallet:

    def test_reject_system_wallet_as_old_address(self):
        from wallet_v1_migration import migrate_legacy_address
        with pytest.raises(ValueError, match="system_wallet_migration_rejected"):
            migrate_legacy_address(SYSTEM_WALLET, "fake_secret", "02" + "ab" * 32)

    def test_reject_system_wallet_as_derived_target(self):
        from wallet_v1_migration import migrate_legacy_address
        with patch("wallet_v1_migration.derive_thronos_address", return_value=SYSTEM_WALLET):
            with pytest.raises(ValueError, match="system_wallet_migration_rejected"):
                migrate_legacy_address(USER_LEGACY, "fake_secret", "02" + "cd" * 32)

    def test_reject_env_system_wallet_as_source(self):
        """An address only known from env must also be rejected."""
        from wallet_v1_migration import migrate_legacy_address
        env_sys = "THRENV_SYSTEM_TEST_0000000000000000000000000"
        with patch.dict(os.environ, {"WALLET_SYSTEM_ADDRESSES": env_sys}):
            with pytest.raises(ValueError, match="system_wallet_migration_rejected"):
                migrate_legacy_address(env_sys, "fake_secret", "02" + "ef" * 32)


# ───────────────────────────────────────────────────────────────────────────
# 5. Repair rejection for system wallets
# ───────────────────────────────────────────────────────────────────────────

class TestRepairRejectsSystemWallet:

    def test_reject_system_wallet_as_old(self):
        from wallet_v1_migration import repair_migration
        with pytest.raises(ValueError, match="system_wallet_repair_rejected"):
            repair_migration(SYSTEM_WALLET, USER_V1)

    def test_reject_system_wallet_as_new(self):
        from wallet_v1_migration import repair_migration
        with pytest.raises(ValueError, match="system_wallet_repair_rejected"):
            repair_migration(USER_LEGACY, SYSTEM_WALLET)

    def test_reject_both_system(self):
        from wallet_v1_migration import repair_migration
        with pytest.raises(ValueError, match="system_wallet_repair_rejected"):
            repair_migration(SYSTEM_WALLET, SYSTEM_WALLET)


# ───────────────────────────────────────────────────────────────────────────
# 6. Server endpoint source guards (present in code)
# ───────────────────────────────────────────────────────────────────────────

class TestEndpointGuardsPresent:
    """Verify server.py endpoints call is_system_wallet before processing."""

    def test_restore_migration_has_guard(self):
        src = Path("server.py").read_text()
        idx = src.index("def api_wallet_v1_restore_migration")
        block = src[idx:idx + 2500]
        assert "is_system_wallet" in block
        assert "system_wallet_not_user_migratable" in block

    def test_resolve_address_has_guard(self):
        src = Path("server.py").read_text()
        idx = src.index("def api_wallet_v1_resolve_address")
        block = src[idx:idx + 2500]
        assert "is_system_wallet" in block
        assert "system_wallet_not_user_resolvable" in block


# ───────────────────────────────────────────────────────────────────────────
# 7. Wallet identity diagnostics (UNVERIFIED — from source text only)
# ───────────────────────────────────────────────────────────────────────────

class TestWalletIdentityDiagnostics:
    """Source-level assertions from issue #542.
    NOTE: These mappings are from source text inspection, NOT from the
    deployed migration store. They are labeled unverified until a
    sanitized read-only production check establishes them."""

    def test_thr24d877_not_in_migration_module(self):
        """THR24d877... has no code references — unverified: likely browser pollution."""
        src = Path("wallet_v1_migration.py").read_text()
        assert "THR24d877dd21c6b0c9d8a702f24842fc34052a5689" not in src

    def test_thr79ca_and_thr683318_in_frontend_source(self):
        """UNVERIFIED mapping from source: THR79ca → THR683318 in wallet_session.js.
        Production migration store not checked."""
        src = Path("static/wallet_session.js").read_text()
        assert "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a" in src
        assert "THR683318ACF083723B3EDFE6C0A30AD62670F00353" in src

    def test_system_wallet_only_in_guard_block(self):
        """THR5DF27... must only appear in the _HARDCODED_SYSTEM_WALLETS block."""
        src = Path("wallet_v1_migration.py").read_text()
        guard_start = src.index("_HARDCODED_SYSTEM_WALLETS")
        guard_end = src.index("})", guard_start) + 2
        src_without_guard = src[:guard_start] + src[guard_end:]
        assert SYSTEM_WALLET not in src_without_guard

    def test_system_wallet_in_frontend_guard(self):
        src = Path("static/wallet_session.js").read_text()
        assert SYSTEM_WALLET in src
        assert "ai_game_wallet" in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
