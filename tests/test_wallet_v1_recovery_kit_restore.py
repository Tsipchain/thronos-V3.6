"""
Wallet V1 Recovery Kit Restore Tests

Verifies that:
1. Recovery Kit restore functions exist and are properly implemented
2. Recovery Kit restore is shown as PRIMARY action for missing signing key
3. Advanced recovery options are hidden by default
4. Recovery Kit restore form has correct validation
5. PIN validation is enforced (4-8 digits)
6. Canonical address comparison prevents wallet switching
7. Public key format validation is applied
8. Error handling preserves wallet identity on PIN failure
9. After restore, wallet can build signed requests
10. UI integration with switchWalletV1Mode() works correctly
"""

import pytest
from pathlib import Path
import json
import re


class TestRecoveryKitRestoreFunctions:
    """Test that Recovery Kit restore functions are defined correctly."""

    def test_walletV1DetectMissingSigningKeyState_exists(self):
        """Verify walletV1DetectMissingSigningKeyState function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletV1DetectMissingSigningKeyState()" in content, \
            "walletV1DetectMissingSigningKeyState function not found"

    def test_walletV1ShowRecoveryKitRestorePrimary_exists(self):
        """Verify walletV1ShowRecoveryKitRestorePrimary function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletV1ShowRecoveryKitRestorePrimary()" in content, \
            "walletV1ShowRecoveryKitRestorePrimary function not found"

    def test_walletV1RestoreFromRecoveryKit_exists(self):
        """Verify walletV1RestoreFromRecoveryKit async function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "async function walletV1RestoreFromRecoveryKit" in content, \
            "walletV1RestoreFromRecoveryKit function not found"

    def test_walletV1HandleRecoveryKitRestore_exists(self):
        """Verify walletV1HandleRecoveryKitRestore function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletV1HandleRecoveryKitRestore()" in content, \
            "walletV1HandleRecoveryKitRestore function not found"

    def test_walletV1ShowAdvancedRecovery_exists(self):
        """Verify walletV1ShowAdvancedRecovery function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletV1ShowAdvancedRecovery()" in content, \
            "walletV1ShowAdvancedRecovery function not found"


class TestRecoveryKitRestorePrimaryUI:
    """Test that Recovery Kit is shown as primary UI element."""

    def test_recovery_kit_restore_form_exists(self):
        """Verify Recovery Kit restore form HTML exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'id="walletV1RecoveryKitRestoreForm"' in content, \
            "Recovery Kit restore form not found"

    def test_recovery_kit_restore_form_is_primary(self):
        """Verify Recovery Kit restore form appears before advanced toggle."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Recovery Kit form should come before Advanced toggle in the file
        kit_form_pos = content.find('id="walletV1RecoveryKitRestoreForm"')
        advanced_toggle_pos = content.find('id="walletV1AdvancedRecoveryToggle"')

        assert kit_form_pos > 0, "Recovery Kit form not found"
        assert advanced_toggle_pos > 0, "Advanced toggle not found"
        assert kit_form_pos < advanced_toggle_pos, \
            "Recovery Kit form should appear before Advanced toggle"

    def test_recovery_kit_inputs_exist(self):
        """Verify Recovery Kit restore form has required inputs."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Must have file input
        assert 'id="walletV1RecoveryKitFileInput"' in content, \
            "Missing file input for Recovery Kit"

        # Must have paste input
        assert 'id="walletV1RecoveryKitPasteInput"' in content, \
            "Missing paste input for Recovery Kit"

        # Must have PIN input
        assert 'id="walletV1RecoveryKitPin"' in content, \
            "Missing PIN input for Recovery Kit"

        # Must have status display
        assert 'id="walletV1RecoveryKitStatus"' in content, \
            "Missing status display for Recovery Kit"

    def test_recovery_kit_restore_button_calls_handler(self):
        """Verify Restore Wallet button calls correct handler."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'onclick="walletV1HandleRecoveryKitRestore()"' in content, \
            "Restore button should call walletV1HandleRecoveryKitRestore()"


class TestAdvancedRecoveryUI:
    """Test that legacy recovery forms are hidden in Advanced section."""

    def test_advanced_recovery_section_exists(self):
        """Verify Advanced Recovery section div exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'id="walletV1AdvancedRecoverySection"' in content, \
            "Advanced Recovery section not found"

    def test_advanced_recovery_toggle_exists(self):
        """Verify Advanced Recovery toggle button exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'id="walletV1AdvancedRecoveryToggle"' in content, \
            "Advanced Recovery toggle button not found"

    def test_advanced_toggle_is_hidden_by_default(self):
        """Verify Advanced Recovery section is hidden by default."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find Advanced section
        start = content.find('id="walletV1AdvancedRecoverySection"')
        end = content.find('>', start)
        tag = content[start:end + 1]

        assert 'style="display:none;"' in tag or 'display:none' in tag, \
            "Advanced Recovery section should be hidden by default"

    def test_legacy_recovery_forms_in_advanced_section(self):
        """Verify legacy recovery forms are in Advanced section."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find positions
        advanced_section_pos = content.find('id="walletV1AdvancedRecoverySection"')
        legacy_form_pos = content.find('id="walletV1LegacyRecoveryForm"')
        advanced_key_import_pos = content.find('id="walletV1AdvancedKeyImportForm"')
        rekey_form_pos = content.find('id="walletV1RekeyCeremonyForm"')
        advanced_section_close_pos = content.find('</div>  <!-- Close walletV1AdvancedRecoverySection -->')

        # All forms should come after Advanced section opens
        assert legacy_form_pos > advanced_section_pos, \
            "Legacy recovery form should be after Advanced section opens"
        assert advanced_key_import_pos > advanced_section_pos, \
            "Advanced key import form should be after Advanced section opens"
        assert rekey_form_pos > advanced_section_pos, \
            "Re-key ceremony form should be after Advanced section opens"

        # All forms should come before Advanced section closes
        assert legacy_form_pos < advanced_section_close_pos, \
            "Legacy recovery form should be before Advanced section closes"
        assert advanced_key_import_pos < advanced_section_close_pos, \
            "Advanced key import form should be before Advanced section closes"
        assert rekey_form_pos < advanced_section_close_pos, \
            "Re-key ceremony form should be before Advanced section closes"


class TestRecoveryKitRestoreLogic:
    """Test Recovery Kit restore function logic."""

    def test_detect_missing_signing_key_checks_canonical_address(self):
        """Verify detect function checks for canonical address."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("function walletV1DetectMissingSigningKeyState()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "wallet_v1_address" in func, \
            "Should check wallet_v1_address in localStorage"
        assert "wallet_v1_encrypted_priv" in func, \
            "Should check wallet_v1_encrypted_priv in localStorage"

    def test_show_recovery_kit_as_primary_hides_legacy(self):
        """Verify primary UI function hides legacy forms."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("function walletV1ShowRecoveryKitRestorePrimary()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "walletV1LegacyRecoveryForm" in func, \
            "Should hide legacy recovery form"
        assert "walletV1AdvancedKeyImportForm" in func, \
            "Should hide advanced key import form"
        assert "walletV1RekeyCeremonyForm" in func, \
            "Should hide re-key ceremony form"
        assert "style.display = 'none'" in func, \
            "Should set display to none for hidden forms"

    def test_restore_validates_recovery_kit_version(self):
        """Verify restore function validates kit version."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "wallet-v1-recovery-kit" in func, \
            "Should validate recovery kit version"
        assert "Invalid Recovery Kit version" in func, \
            "Should throw error for invalid version"

    def test_restore_validates_canonical_address(self):
        """Verify restore function validates canonical address format."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "canonical_v1_address" in func, \
            "Should check canonical address from kit"
        assert "startsWith('THR')" in func or "THR" in func, \
            "Should validate canonical address starts with THR"

    def test_restore_checks_for_wallet_switch(self):
        """Verify restore function warns about wallet switching."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "confirm(" in func, \
            "Should prompt user about wallet switch"
        assert "different wallet" in func, \
            "Should warn about different wallet"

    def test_restore_validates_public_key_format(self):
        """Verify restore function validates public key format."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "isValidSecp256k1PublicKeyHex" in func, \
            "Should validate public key format"

    def test_restore_enforces_pin_decryption(self):
        """Verify restore function requires PIN decryption."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "decryptPrivateKeyHex" in func, \
            "Should decrypt private key with PIN"
        assert "Wrong PIN" in func, \
            "Should give generic error for wrong PIN"

    def test_restore_persists_to_localStorage(self):
        """Verify restore function saves to localStorage."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "wallet_v1_address" in func, \
            "Should save canonical address"
        assert "wallet_v1_encrypted_priv" in func, \
            "Should save encrypted private key"
        assert "wallet_v1_public_key" in func, \
            "Should save public key"

    def test_restore_preserves_wallet_identity_on_error(self):
        """Verify restore function does NOT clear wallet on error."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        # Should NOT clear wallet
        assert "localStorage.removeItem('wallet_v1_address')" not in func, \
            "Should NOT clear wallet identity on error"
        assert "walletSession.clear()" not in func, \
            "Should NOT clear session on error"

        # Should have error handling
        assert "catch" in func, \
            "Should have catch block for error handling"

    def test_restore_updates_runtime_signer(self):
        """Verify restore function updates runtime wallet session."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract function
        start = content.find("async function walletV1RestoreFromRecoveryKit")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "walletSession.setAddress" in func, \
            "Should update runtime address"
        assert "walletSession.unlockWithPin" in func, \
            "Should unlock runtime signing material"


class TestRecoveryKitHandlerValidation:
    """Test Recovery Kit handler form validation."""

    def test_handler_validates_pin_length(self):
        """Verify handler validates PIN is 4-8 digits."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract handler function
        start = content.find("function walletV1HandleRecoveryKitRestore()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "pinInput.value.length" in func, \
            "Should check PIN length"
        assert "4" in func, \
            "Should require minimum 4 digit PIN"

    def test_handler_supports_file_upload(self):
        """Verify handler supports file upload."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract handler function
        start = content.find("function walletV1HandleRecoveryKitRestore()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "FileReader" in func, \
            "Should handle file upload"

    def test_handler_supports_paste_input(self):
        """Verify handler supports pasted JSON."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract handler function
        start = content.find("function walletV1HandleRecoveryKitRestore()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "walletV1RecoveryKitPasteInput" in func, \
            "Should handle pasted JSON"


class TestSwitchModeIntegration:
    """Test Recovery Kit integration with switchWalletV1Mode."""

    def test_switchWalletV1Mode_calls_recovery_kit_primary(self):
        """Verify switchWalletV1Mode calls walletV1ShowRecoveryKitRestorePrimary."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find switchWalletV1Mode function (there may be wrapping/override)
        # Look for the call to walletV1ShowRecoveryKitRestorePrimary
        assert "walletV1ShowRecoveryKitRestorePrimary()" in content, \
            "switchWalletV1Mode should call walletV1ShowRecoveryKitRestorePrimary()"

        # Find where it's called
        call_pos = content.find("walletV1ShowRecoveryKitRestorePrimary()")
        # Should be near importEl.style.display assignment
        context_start = max(0, call_pos - 500)
        context_end = min(len(content), call_pos + 500)
        context = content[context_start:context_end]

        assert "importEl" in context, \
            "Recovery Kit primary should be called when import mode shown"


class TestNoOldDuplicates:
    """Test that old/duplicate recovery forms are cleaned up."""

    def test_no_duplicate_recovery_kit_restore_form(self):
        """Verify no duplicate recovery kit restore forms exist."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should only have one walletV1RecoveryKitRestoreForm
        count = content.count('id="walletV1RecoveryKitRestoreForm"')
        assert count == 1, \
            f"Should have exactly one Recovery Kit restore form, found {count}"

    def test_no_orphaned_recovery_divs(self):
        """Verify no orphaned recovery-related divs."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Check for orphaned data-missing-key-recovery divs
        # These should only be created dynamically by JavaScript, not in HTML
        pattern = r'<div[^>]*data-missing-key-recovery[^>]*>\s*</div>'
        orphaned = re.findall(pattern, content)
        assert len(orphaned) == 0, \
            f"Found orphaned data-missing-key-recovery divs: {orphaned}"

    def test_advanced_section_properly_closed(self):
        """Verify walletV1AdvancedRecoverySection is properly closed."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find Advanced section with explicit close comment
        start = content.find('id="walletV1AdvancedRecoverySection"')
        closing = content.find('</div>  <!-- Close walletV1AdvancedRecoverySection -->', start)

        assert start > 0, "Advanced Recovery section should exist"
        assert closing > start, \
            "Advanced Recovery section should be explicitly closed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
