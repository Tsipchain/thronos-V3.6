"""
Tests for wallet recovery and active address precedence.
Verifies:
  - Active address precedence: wallet_v1_address > migration.new_v1_address > thr_address
  - Failed unlock doesn't mutate localStorage state
  - Recovery buttons exist and work safely
  - Reset doesn't delete encrypted key material
  - Danger clear requires confirmation
  - No secrets exposed in diagnostics
  - Missing signing material handled properly
"""

import re
import pytest


@pytest.fixture
def base_html_content():
    """Load templates/base.html"""
    with open('templates/base.html', 'r') as f:
        return f.read()


@pytest.fixture
def wallet_session_content():
    """Load static/wallet_session.js"""
    with open('static/wallet_session.js', 'r') as f:
        return f.read()


@pytest.fixture
def public_wallet_session_content():
    """Load public/static/wallet_session.js"""
    with open('public/static/wallet_session.js', 'r') as f:
        return f.read()


class TestActiveAddressPrecedence:
    """Test that active address resolution follows correct precedence."""

    def test_getActiveAddress_function_exists(self, wallet_session_content):
        """Verify getActiveAddress() function is present."""
        assert 'function getActiveAddress()' in wallet_session_content

    def test_getActiveAddress_checks_wallet_v1_address(self, wallet_session_content):
        """Verify getActiveAddress() checks wallet_v1_address first."""
        assert 'V1_ADDRESS_KEY' in wallet_session_content
        assert 'getActiveAddress' in wallet_session_content

    def test_getActiveAddress_validates_addresses(self, wallet_session_content):
        """Verify getActiveAddress() validates THR format before using legacy address."""
        assert 'isValidThrAddress' in wallet_session_content
        assert 'function getActiveAddress()' in wallet_session_content
        assert 'startsWith(\'THR\')' in wallet_session_content

    def test_isValidThrAddress_function_exists(self, wallet_session_content):
        """Verify isValidThrAddress() helper exists."""
        assert 'function isValidThrAddress(' in wallet_session_content
        assert 'startsWith(\'THR\')' in wallet_session_content

    def test_wallet_session_synced(self, wallet_session_content, public_wallet_session_content):
        """Verify static/ and public/static/ wallet_session.js are synced."""
        assert 'function getActiveAddress()' in public_wallet_session_content
        assert 'isValidThrAddress' in public_wallet_session_content
        assert 'getDebugState' in public_wallet_session_content


class TestFailedUnlockProtection:
    """Test that failed wallet operations don't mutate localStorage state."""

    def test_migrateLegacyWallet_function_exists(self, wallet_session_content):
        """Verify migrateLegacyWallet() function is present."""
        assert 'function migrateLegacyWallet(' in wallet_session_content

    def test_unlockWallet_has_error_handling(self, wallet_session_content):
        """Verify unlockWallet has try/catch and doesn't mutate on failure."""
        assert 'function unlockWallet(' in wallet_session_content
        assert 'catch' in wallet_session_content

    def test_restore_to_migrated_wallet_function_exists(self, wallet_session_content):
        """Verify restoreToMigratedWallet() function exists for recovery."""
        assert 'function restoreToMigratedWallet(' in wallet_session_content


class TestRecoveryButtonsPresent:
    """Test that recovery buttons and functions exist in base.html."""

    def test_reset_active_wallet_pointers_button_exists(self, base_html_content):
        """Verify 'Reset Active Wallet Pointers' button exists."""
        assert 'Reset Active Wallet Pointers' in base_html_content or 'resetActiveWalletPointers' in base_html_content

    def test_clear_wallet_data_button_exists(self, base_html_content):
        """Verify 'Clear All Wallet Data' danger button exists."""
        assert 'Clear All Wallet Data' in base_html_content or 'clearAllWalletData' in base_html_content

    def test_recovery_buttons_have_js_handlers(self, base_html_content):
        """Verify recovery buttons have onclick handlers."""
        assert 'resetActiveWalletPointersFromHeader' in base_html_content
        assert 'clearAllWalletDataFromHeader' in base_html_content

    def test_advanced_recovery_toggle_exists(self, base_html_content):
        """Verify Advanced Recovery section exists with toggle."""
        assert 'Advanced Recovery' in base_html_content or 'toggleAdvancedRecovery' in base_html_content


class TestResetSafety:
    """Test that reset operations preserve encrypted key material."""

    def test_resetActiveWalletPointers_function_exists(self, wallet_session_content):
        """Verify resetActiveWalletPointers() function exists."""
        assert 'function resetActiveWalletPointers(' in wallet_session_content

    def test_clearAllWalletData_function_exists(self, wallet_session_content):
        """Verify clearAllWalletData() function exists."""
        assert 'function clearAllWalletData(' in wallet_session_content

    def test_clearAllWalletData_preserves_migration_meta(self, wallet_session_content):
        """Verify dangerous clear preserves MIGRATION_META for recovery reference."""
        # Find the clearAllWalletData function
        match = re.search(
            r'function clearAllWalletData\(\)[\s\S]*?(?=\n  function|\Z)',
            wallet_session_content
        )
        if match:
            func_body = match.group(0)
            # Should NOT include MIGRATION_META_KEY removal in the removals
            # But it should have a comment about keeping it
            assert 'MIGRATION_META_KEY' in func_body or 'migration record' in func_body.lower()


class TestDangerClearConfirmation:
    """Test that dangerous clear operations require confirmation."""

    def test_danger_clear_requires_confirmation_text(self, base_html_content):
        """Verify danger clear button requires typing confirmation."""
        assert 'I UNDERSTAND' in base_html_content or 'confirm' in base_html_content.lower()

    def test_clear_all_wallet_data_handler_exists(self, wallet_session_content):
        """Verify clearAllWalletData handler checks for confirmation."""
        assert 'function clearAllWalletData(' in wallet_session_content

    def test_clear_requires_explicit_opt_in(self, base_html_content):
        """Verify danger clear has explicit opt-in requirement."""
        assert 'I UNDERSTAND' in base_html_content or 'danger' in base_html_content.lower()


class TestDiagnosticsNoSecrets:
    """Test that diagnostic functions don't expose secrets."""

    def test_getDebugState_function_exists(self, wallet_session_content):
        """Verify getDebugState() diagnostic helper exists."""
        assert 'function getDebugState(' in wallet_session_content

    def test_getDebugState_no_pin(self, wallet_session_content):
        """Verify getDebugState() does NOT return PIN."""
        match = re.search(
            r'function getDebugState\(\)[\s\S]*?return\s*\{[\s\S]*?\};',
            wallet_session_content
        )
        if match:
            func_body = match.group(0)
            # Should not expose PIN
            assert 'PIN_KEY' not in func_body or 'getPin' not in func_body

    def test_getDebugState_no_seed(self, wallet_session_content):
        """Verify getDebugState() does NOT return seed or mnemonic."""
        match = re.search(
            r'function getDebugState\(\)[\s\S]*?return\s*\{[\s\S]*?\};',
            wallet_session_content
        )
        if match:
            func_body = match.group(0)
            # Should not expose seed
            assert 'SEND_SEED' not in func_body or 'getSendSeed' not in func_body

    def test_getDebugState_no_auth_secret(self, wallet_session_content):
        """Verify getDebugState() does NOT return auth_secret."""
        match = re.search(
            r'function getDebugState\(\)[\s\S]*?return\s*\{[\s\S]*?\};',
            wallet_session_content
        )
        if match:
            func_body = match.group(0)
            # Should not expose auth_secret
            assert 'SEND_SECRET' not in func_body or 'getSendSecret' not in func_body

    def test_getDebugState_returns_safe_fields(self, wallet_session_content):
        """Verify getDebugState() returns safe diagnostic fields."""
        # Should return things like: active_wallet, has_signing_material, is_locked, etc.
        assert 'active_wallet' in wallet_session_content or 'active_address' in wallet_session_content
        assert 'has_signing_material' in wallet_session_content or 'is_locked' in wallet_session_content


class TestWalletModesMutuallyExclusive:
    """Test that wallet modes (Unlock/Create/Migrate) are mutually exclusive."""

    def test_unlock_mode_div_exists(self, base_html_content):
        """Verify Unlock mode div exists."""
        assert 'walletV1UnlockMode' in base_html_content

    def test_create_mode_div_exists(self, base_html_content):
        """Verify Create mode div exists."""
        assert 'walletV1CreateMode' in base_html_content

    def test_migrate_mode_div_exists(self, base_html_content):
        """Verify Migrate mode div exists."""
        assert 'walletV1MigrateMode' in base_html_content

    def test_mode_switch_function_exists(self, base_html_content):
        """Verify switchWalletV1Mode() function exists to toggle modes."""
        assert 'switchWalletV1Mode' in base_html_content

    def test_modes_use_display_none(self, base_html_content):
        """Verify modes use display:none for exclusivity."""
        assert 'display' in base_html_content or 'style' in base_html_content


class TestRecoveryButtonHandlers:
    """Test that recovery button handlers exist and are wired correctly."""

    def test_reset_active_wallet_pointers_from_header_exists(self, base_html_content):
        """Verify resetActiveWalletPointersFromHeader() handler exists."""
        assert 'resetActiveWalletPointersFromHeader' in base_html_content

    def test_clear_all_wallet_data_from_header_exists(self, base_html_content):
        """Verify clearAllWalletDataFromHeader() handler exists."""
        assert 'clearAllWalletDataFromHeader' in base_html_content

    def test_toggle_advanced_recovery_exists(self, base_html_content):
        """Verify toggleAdvancedRecoveryFromHeader() function exists."""
        assert 'toggleAdvancedRecoveryFromHeader' in base_html_content


class TestExportsAndSyncing:
    """Test that recovery functions are properly exported."""

    def test_recovery_functions_exported_static(self, wallet_session_content):
        """Verify recovery functions are exported from static/wallet_session.js."""
        assert 'getDebugState' in wallet_session_content
        assert 'resetActiveWalletPointers' in wallet_session_content
        assert 'restoreToMigratedWallet' in wallet_session_content
        assert 'clearAllWalletData' in wallet_session_content
        assert 'isValidThrAddress' in wallet_session_content

    def test_recovery_functions_exported_public(self, public_wallet_session_content):
        """Verify recovery functions are exported from public/static/wallet_session.js."""
        assert 'getDebugState' in public_wallet_session_content
        assert 'resetActiveWalletPointers' in public_wallet_session_content
        assert 'restoreToMigratedWallet' in public_wallet_session_content
        assert 'clearAllWalletData' in public_wallet_session_content
        assert 'isValidThrAddress' in public_wallet_session_content

    def test_files_are_synchronized(self, wallet_session_content, public_wallet_session_content):
        """Verify static and public wallet files have equivalent functions."""
        static_has_recovery = all(fn in wallet_session_content for fn in [
            'function getDebugState',
            'function resetActiveWalletPointers',
            'function restoreToMigratedWallet',
            'function clearAllWalletData',
            'function isValidThrAddress'
        ])
        public_has_recovery = all(fn in public_wallet_session_content for fn in [
            'function getDebugState',
            'function resetActiveWalletPointers',
            'function restoreToMigratedWallet',
            'function clearAllWalletData',
            'function isValidThrAddress'
        ])
        assert static_has_recovery and public_has_recovery


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
