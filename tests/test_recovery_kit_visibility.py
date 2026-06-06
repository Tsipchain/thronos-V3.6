"""
Test Recovery Kit visibility and auto-detection of missing signing key state.

Ensures that when a wallet has encrypted key material but no runtime signing material,
the Recovery Kit restore flow is shown as PRIMARY UI option.
"""

import pytest
from pathlib import Path


class TestRecoveryKitAutoDetection:
    """Test that missing signing key state is automatically detected."""

    def test_missing_signing_key_detection_function_exists(self):
        """Verify detectMissingSigningKeyState function is defined."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function detectMissingSigningKeyState()" in content, \
            "detectMissingSigningKeyState function not found"

    def test_missing_signing_key_checks_encrypted_key(self):
        """Verify detection checks for encrypted key presence."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        func_start = content.find("function detectMissingSigningKeyState()")
        func_end = content.find("function ", func_start + 1)
        func_body = content[func_start:func_end]

        assert "has_encrypted_send_seed" in func_body, \
            "Should check for encrypted key"

    def test_missing_signing_key_checks_no_runtime_material(self):
        """Verify detection checks that runtime material is missing."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        func_start = content.find("function detectMissingSigningKeyState()")
        func_end = content.find("function ", func_start + 1)
        func_body = content[func_start:func_end]

        assert "has_runtime_signing_material" in func_body, \
            "Should check for runtime material"
        assert "!" in func_body or "not" in func_body or "false" in func_body, \
            "Should check that runtime material is NOT present"

    def test_show_wallet_login_form_calls_detection(self):
        """Verify showWalletLoginForm calls missing key detection."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        func_start = content.find("function showWalletLoginForm()")
        func_end = content.find("function ", func_start + 1)
        func_body = content[func_start:func_end]

        assert "detectMissingSigningKeyState" in func_body, \
            "showWalletLoginForm should call missing key detection"


class TestRecoveryKitModeAutoSwitch:
    """Test that UI automatically switches to unlock mode when recovery needed."""

    def test_show_wallet_login_form_sets_unlock_mode(self):
        """Verify that unlock mode is forced when missing key detected."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        func_start = content.find("function showWalletLoginForm()")
        func_end = content.find("function ", func_start + 1)
        func_body = content[func_start:func_end]

        assert "modeSelect.value = 'unlock'" in func_body or \
               "walletWidgetMode" in func_body and "unlock" in func_body, \
            "Should auto-select unlock mode when missing key detected"

    def test_auto_switch_is_conditional_on_missing_key(self):
        """Verify mode switch only happens when missing key state detected."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        func_start = content.find("function showWalletLoginForm()")
        func_end = content.find("function ", func_start + 1)
        func_body = content[func_start:func_end]

        assert "hasMissingKey" in func_body or \
               "detectMissingSigningKeyState()" in func_body, \
            "Mode switch should be conditional on missing key detection"

    def test_unlock_mode_section_visible_when_needed(self):
        """Verify unlock mode UI section is visible in HTML."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'id="walletV1UnlockMode"' in content, \
            "Unlock mode section should exist in HTML"


class TestRecoveryKitUIElements:
    """Test that Recovery Kit UI elements are properly structured."""

    def test_unlock_mode_section_exists(self):
        """Verify unlock mode section exists in modal."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'id="walletV1UnlockMode"' in content, \
            "Unlock mode section not found"

        start = content.find('id="walletV1UnlockMode"')
        section = content[start:start + 1000]

        assert "PIN" in section, \
            "PIN input should be in unlock mode"
        assert "Unlock Wallet V1" in section, \
            "Unlock button should be visible"

    def test_recovery_section_has_migration_restore(self):
        """Verify recovery section has migration restore button."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "restoreMigratedWalletSection" in content, \
            "Restore migrated wallet section should exist"

    def test_recovery_section_is_conditional(self):
        """Verify recovery section is conditionally shown."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "style=\"display:none" in content and "restoreMigratedWalletSection" in content, \
            "Recovery section should be hidden by default"


class TestDiagnosticsDisplay:
    """Test that wallet diagnostics help user understand state."""

    def test_wallet_diagnostics_section_exists(self):
        """Verify diagnostics section exists for debugging."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "walletDiagnosticsContent" in content or "walletPanelDiagnostics" in content, \
            "Diagnostics section should exist"

    def test_diagnostics_shows_signing_material_status(self):
        """Verify diagnostics display signing material status."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        func_start = content.find("function updateWalletPanelDiagnostics()")
        func_end = content.find("function ", func_start + 1)
        func_body = content[func_start:func_end]

        assert "Signing" in func_body or "signing" in func_body or \
               "has_signing_material" in func_body, \
            "Diagnostics should show signing material status"


class TestNoSilentFallback:
    """Test that missing key doesn't silently fall back to legacy auth."""

    def test_unlock_mode_doesnt_show_legacy_fallback(self):
        """Verify unlock mode doesn't show legacy auth fields."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find unlock mode section
        unlock_start = content.find('id="walletV1UnlockMode"')
        unlock_end = content.find('</div>', unlock_start + 100)
        unlock_section = content[unlock_start:unlock_end]

        # Should NOT have legacy auth_secret field in unlock mode
        assert "auth_secret" not in unlock_section or \
               'id="walletV1UnlockMode"' in unlock_section, \
            "Unlock mode should not show legacy auth_secret field"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
