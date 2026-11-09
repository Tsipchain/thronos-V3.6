"""
Tests for backend system wallet guards on migration/repair/resolve endpoints.
Ensures system wallets (AI/game/treasury/Pythia) are never accepted as user
migration sources or targets.

Addresses issue #542.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

SYSTEM_WALLET = "THR5DF27A86C477F381594E896F0E55357DEC5942BA"
USER_LEGACY = "THR79CA94A7EB70A6AA99D12D7FDB01446EF246301A"
USER_V1 = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"


class TestIsSystemWallet:
    """Test the is_system_wallet() function in wallet_v1_migration."""

    def test_hardcoded_system_wallet_detected(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet(SYSTEM_WALLET) is True

    def test_case_insensitive(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet(SYSTEM_WALLET.lower()) is True

    def test_normal_user_wallet_not_system(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet(USER_LEGACY) is False
        assert is_system_wallet(USER_V1) is False

    def test_empty_or_none_not_system(self):
        from wallet_v1_migration import is_system_wallet
        assert is_system_wallet("") is False
        assert is_system_wallet(None) is False

    def test_env_override_adds_addresses(self):
        from wallet_v1_migration import is_system_wallet, _get_system_wallet_set
        extra = "THREXTRA0000000000000000000000000000000000"
        with patch.dict(os.environ, {"WALLET_SYSTEM_ADDRESSES": extra}):
            addrs = _get_system_wallet_set()
            assert extra in addrs
            assert is_system_wallet(extra) is True


class TestMigrateRejectsSystemWallet:
    """migrate_legacy_address must reject system wallets as source or target."""

    def test_reject_system_wallet_as_old_address(self):
        from wallet_v1_migration import migrate_legacy_address
        with pytest.raises(ValueError, match="system_wallet_migration_rejected"):
            migrate_legacy_address(SYSTEM_WALLET, "fake_secret", "02" + "ab" * 32)

    def test_reject_system_wallet_as_derived_target(self):
        from wallet_v1_migration import migrate_legacy_address
        with patch("wallet_v1_migration.derive_thronos_address", return_value=SYSTEM_WALLET):
            with pytest.raises(ValueError, match="system_wallet_migration_rejected"):
                migrate_legacy_address(USER_LEGACY, "fake_secret", "02" + "cd" * 32)


class TestRepairRejectsSystemWallet:
    """repair_migration must reject system wallets."""

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


class TestRestoreMigrationEndpointRejectsSystem:
    """api_wallet_v1_restore_migration must not return system wallet as canonical."""

    def test_source_code_has_system_wallet_guard(self):
        src = Path("server.py").read_text()
        idx = src.index("def api_wallet_v1_restore_migration")
        block = src[idx:idx + 2500]
        assert "is_system_wallet" in block
        assert "system_wallet_not_user_migratable" in block

    def test_restore_migration_guard_checks_both_addresses(self):
        src = Path("server.py").read_text()
        idx = src.index("def api_wallet_v1_restore_migration")
        block = src[idx:idx + 2500]
        assert "is_system_wallet(legacy_address)" in block
        assert "is_system_wallet(canonical_v1_address)" in block


class TestResolveAddressEndpointRejectsSystem:
    """api_wallet_v1_resolve_address must not resolve system wallets."""

    def test_source_code_has_system_wallet_guard(self):
        src = Path("server.py").read_text()
        idx = src.index("def api_wallet_v1_resolve_address")
        block = src[idx:idx + 2500]
        assert "is_system_wallet" in block
        assert "system_wallet_not_user_resolvable" in block


class TestWalletIdentityMapping:
    """Diagnostic assertions from issue #542."""

    def test_thr24d877_not_in_codebase(self):
        """THR24d877... (Pair A legacy) has no code references — browser pollution."""
        src = Path("wallet_v1_migration.py").read_text()
        assert "THR24d877dd21c6b0c9d8a702f24842fc34052a5689" not in src

    def test_thr79ca_maps_to_thr683318_not_thre85(self):
        """THR79ca... maps to THR683318..., NOT to THRE85A3E0..."""
        src = Path("static/wallet_session.js").read_text()
        assert "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a" in src
        assert "THR683318ACF083723B3EDFE6C0A30AD62670F00353" in src
        idx = src.index("VERIFIED_LEGACY_SOURCE_ADDRESS")
        block = src[idx:idx + 300]
        assert "THR79ca" in block
        idx2 = src.index("VERIFIED_CANONICAL_V1_ADDRESS")
        block2 = src[idx2:idx2 + 300]
        assert "THR683318" in block2

    def test_system_wallet_never_as_migration_source_or_target(self):
        """THR5DF27... must not appear as a migration source/target in migration module.
        It may only appear inside the _HARDCODED_SYSTEM_WALLETS block."""
        src = Path("wallet_v1_migration.py").read_text()
        guard_start = src.index("_HARDCODED_SYSTEM_WALLETS")
        guard_end = src.index("})", guard_start) + 2
        src_without_guard = src[:guard_start] + src[guard_end:]
        assert SYSTEM_WALLET not in src_without_guard, \
            "System wallet appears outside the guard definition in wallet_v1_migration.py"

    def test_system_wallet_is_in_frontend_guard(self):
        """THR5DF27... must be in frontend SYSTEM_WALLETS dict."""
        src = Path("static/wallet_session.js").read_text()
        assert SYSTEM_WALLET in src
        assert "ai_game_wallet" in src
