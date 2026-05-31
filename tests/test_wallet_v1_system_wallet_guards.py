"""
Tests for wallet V1 system wallet guards.
Verifies that system wallets (AI/game wallet) are never returned as active user wallets,
even if they appear in localStorage or migration records.
"""

import re
import pytest


@pytest.fixture
def static_wallet_session_content():
    """Load static/wallet_session.js"""
    with open('static/wallet_session.js', 'r') as f:
        return f.read()


@pytest.fixture
def public_wallet_session_content():
    """Load public/static/wallet_session.js"""
    with open('public/static/wallet_session.js', 'r') as f:
        return f.read()


class TestSystemWalletIdentification:
    """Test that system wallets are correctly identified."""

    def test_has_system_wallets_constant(self, static_wallet_session_content):
        """Verify SYSTEM_WALLETS constant is defined."""
        assert 'const SYSTEM_WALLETS' in static_wallet_session_content
        assert 'THR5DF27A86C477F381594E896F0E55357DEC5942BA' in static_wallet_session_content

    def test_has_is_system_wallet_address_function(self, static_wallet_session_content):
        """Verify isSystemWalletAddress function exists."""
        assert 'function isSystemWalletAddress(addr)' in static_wallet_session_content

    def test_system_wallet_function_uses_hasOwnProperty(self, static_wallet_session_content):
        """Verify isSystemWalletAddress uses proper lookup."""
        match = re.search(
            r'function isSystemWalletAddress\(addr\)[\s\S]*?SYSTEM_WALLETS\.hasOwnProperty',
            static_wallet_session_content
        )
        assert match is not None, "isSystemWalletAddress should use SYSTEM_WALLETS.hasOwnProperty"


class TestGetActiveAddressSkipsSystemWallets:
    """Test that getActiveAddress() never returns system wallets."""

    def test_get_active_address_checks_v1_wallet_for_system(self, static_wallet_session_content):
        """Verify getActiveAddress rejects wallet_v1_address if it's a system wallet."""
        match = re.search(
            r'if \(v1_addr && isValidThrAddress\(v1_addr\) && !isSystemWalletAddress\(v1_addr\)\)',
            static_wallet_session_content
        )
        assert match is not None, "getActiveAddress should check if v1_addr is NOT a system wallet"

    def test_get_active_address_checks_migration_new_v1_for_system(self, static_wallet_session_content):
        """Verify getActiveAddress rejects migration.new_v1_address if it's a system wallet."""
        match = re.search(
            r'if \(info\.new_v1_address && isValidThrAddress\(info\.new_v1_address\) && !isSystemWalletAddress\(info\.new_v1_address\)\)',
            static_wallet_session_content
        )
        assert match is not None, "getActiveAddress should check if migration.new_v1_address is NOT a system wallet"

    def test_get_active_address_checks_legacy_address_for_system(self, static_wallet_session_content):
        """Verify getActiveAddress rejects thr_address if it's a system wallet."""
        match = re.search(
            r'if \(legacy_addr && isValidThrAddress\(legacy_addr\) && !isSystemWalletAddress\(legacy_addr\)\)',
            static_wallet_session_content
        )
        assert match is not None, "getActiveAddress should check if legacy_addr is NOT a system wallet"

    def test_get_active_address_returns_empty_for_all_system(self, static_wallet_session_content):
        """Verify getActiveAddress returns empty string as fallback."""
        # Should have fallback that returns ''
        match = re.search(
            r'return \'\';',
            static_wallet_session_content
        )
        assert match is not None, "getActiveAddress should have fallback returning ''"


class TestIgnoredSystemWalletTracking:
    """Test that ignored system wallets are tracked for debugging."""

    def test_has_ignored_system_wallet_source_variable(self, static_wallet_session_content):
        """Verify _ignoredSystemWalletSource tracking variable exists."""
        assert '_ignoredSystemWalletSource = null' in static_wallet_session_content

    def test_sets_ignored_source_for_v1_wallet(self, static_wallet_session_content):
        """Verify code sets _ignoredSystemWalletSource when v1_addr is system wallet."""
        match = re.search(
            r"_ignoredSystemWalletSource = 'wallet_v1_address'",
            static_wallet_session_content
        )
        assert match is not None

    def test_sets_ignored_source_for_migration(self, static_wallet_session_content):
        """Verify code sets _ignoredSystemWalletSource when migration.new_v1_address is system wallet."""
        match = re.search(
            r"_ignoredSystemWalletSource = 'migration\.new_v1_address'",
            static_wallet_session_content
        )
        assert match is not None

    def test_sets_ignored_source_for_legacy(self, static_wallet_session_content):
        """Verify code sets _ignoredSystemWalletSource when thr_address is system wallet."""
        match = re.search(
            r"_ignoredSystemWalletSource = 'thr_address'",
            static_wallet_session_content
        )
        assert match is not None

    def test_resets_ignored_source_on_each_call(self, static_wallet_session_content):
        """Verify _ignoredSystemWalletSource is reset at start of getActiveAddress."""
        # Should have _ignoredSystemWalletSource = null at start
        match = re.search(
            r'function getActiveAddress\(\)[\s\S]*?_ignoredSystemWalletSource = null',
            static_wallet_session_content
        )
        assert match is not None


class TestGetDebugStateFunction:
    """Test the getDebugState debug helper function."""

    def test_has_get_debug_state_function(self, static_wallet_session_content):
        """Verify getDebugState function exists."""
        assert 'function getDebugState()' in static_wallet_session_content

    def test_get_debug_state_returns_active_wallet(self, static_wallet_session_content):
        """Verify getDebugState includes active_wallet field."""
        match = re.search(
            r'active_wallet:',
            static_wallet_session_content
        )
        assert match is not None

    def test_get_debug_state_returns_migration_addresses(self, static_wallet_session_content):
        """Verify getDebugState includes migration address fields."""
        assert 'migration_new_v1_address:' in static_wallet_session_content

    def test_get_debug_state_reports_ignored_system_wallet(self, static_wallet_session_content):
        """Verify getDebugState includes ignored_system_wallet field."""
        assert 'ignored_system_wallet:' in static_wallet_session_content
        assert 'ignored_system_wallet_source:' in static_wallet_session_content

    def test_get_debug_state_no_private_key(self, static_wallet_session_content):
        """Verify getDebugState does not include any private key material."""
        # Should not have unlockedPrivateKeyHex, privateKey, secret in return
        match = re.search(
            r'function getDebugState[\s\S]*?return \{[\s\S]*?\}',
            static_wallet_session_content
        )
        if match:
            state_obj = match.group(0)
            assert 'unlockedPrivateKeyHex' not in state_obj
            assert 'privateKey' not in state_obj


class TestFilesSynchronized:
    """Test that static and public wallet_session files are synchronized."""

    def test_both_files_have_system_wallets_const(self, static_wallet_session_content, public_wallet_session_content):
        """Verify both files define SYSTEM_WALLETS."""
        for content in [static_wallet_session_content, public_wallet_session_content]:
            assert 'const SYSTEM_WALLETS' in content

    def test_both_files_have_is_system_wallet_function(self, static_wallet_session_content, public_wallet_session_content):
        """Verify both files have isSystemWalletAddress function."""
        for content in [static_wallet_session_content, public_wallet_session_content]:
            assert 'function isSystemWalletAddress(addr)' in content

    def test_both_files_have_get_debug_state_with_ignored_fields(self, static_wallet_session_content, public_wallet_session_content):
        """Verify both files have getDebugState with ignored_system_wallet fields."""
        for content in [static_wallet_session_content, public_wallet_session_content]:
            assert 'ignored_system_wallet:' in content
            assert 'ignored_system_wallet_source:' in content

    def test_both_files_export_is_system_wallet(self, static_wallet_session_content, public_wallet_session_content):
        """Verify both files export isSystemWalletAddress."""
        for content in [static_wallet_session_content, public_wallet_session_content]:
            assert 'isSystemWalletAddress' in content


class TestAIWalletGuards:
    """Test specific AI wallet guards."""

    def test_thronos_ai_agent_wallet_v1_guarded(self, static_wallet_session_content):
        """Verify THR_AI_AGENT_WALLET_V1 is in system wallets."""
        assert 'THR_AI_AGENT_WALLET_V1' in static_wallet_session_content

    def test_thronos_ai_game_wallet_thronos_guarded(self, static_wallet_session_content):
        """Verify THR5DF (AI game wallet) is in system wallets."""
        assert 'THR5DF27A86C477F381594E896F0E55357DEC5942BA' in static_wallet_session_content


class TestLocaleStorageNotMutated:
    """Test that localStorage is not automatically cleared."""

    def test_get_active_address_does_not_remove_items(self, static_wallet_session_content):
        """Verify getActiveAddress doesn't call removeItem."""
        match = re.search(
            r'function getActiveAddress\(\)[\s\S]*?(?=function )',
            static_wallet_session_content
        )
        if match:
            func_body = match.group(0)
            assert 'removeItem' not in func_body, "getActiveAddress should not mutate localStorage"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
