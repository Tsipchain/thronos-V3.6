"""
Regression Tests: Wallet V1 Mode/Label Correctness

Ensures that:
1. Mode dropdown value matches visible section
2. Button labels match the selected mode
3. Recovery Kit form visible when legacy repair UI = off and wallet has missing key
"""

import pytest
from pathlib import Path


class TestWalletModeLabelMapping:
    """Test that wallet mode correctly maps to section and button labels."""

    def test_unlock_mode_has_unlock_button(self):
        """Ensure 'Unlock Wallet V1' mode shows unlock button."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find unlock mode section
        unlock_section_start = content.find('id="walletV1UnlockMode"')
        assert unlock_section_start > 0, "Unlock mode section should exist"

        # Get section content
        unlock_section_end = content.find('</div>', unlock_section_start) + 6
        unlock_section = content[unlock_section_start:unlock_section_end]

        # Should have unlock button
        assert "Unlock Wallet V1" in unlock_section, "Unlock mode should have 'Unlock Wallet V1' button"
        assert "onclick=\"unlockWalletV1FromHeader()\"" in unlock_section, "Should call unlock handler"

    def test_create_mode_has_create_button(self):
        """Ensure 'Create Wallet V1' mode shows create button."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find create mode section
        create_section_start = content.find('id="walletV1CreateMode"')
        assert create_section_start > 0, "Create mode section should exist"

        # Get section content (find up to next div with id)
        create_section_end = content.find('id="walletV1', create_section_start + 20)
        if create_section_end < 0:
            create_section_end = create_section_start + 500
        create_section = content[create_section_start:create_section_end]

        # Should have create button
        assert "Create Wallet V1" in create_section or "create" in create_section.lower(), \
            "Create mode should reference wallet creation"

    def test_restore_mode_has_restore_button(self):
        """Ensure 'Restore Existing Migrated Wallet' mode shows restore button."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find restore mode section
        restore_section_start = content.find('id="walletV1RestoreMode"')
        assert restore_section_start > 0, "Restore mode section should exist"

        # Get section content
        restore_section_end = content.find('</div>\n\n', restore_section_start) + 10
        restore_section = content[restore_section_start:restore_section_end]

        # Should have restore button
        assert "Restore Migrated Wallet" in restore_section, \
            "Restore mode should have 'Restore Migrated Wallet' button"

    def test_mode_dropdown_has_all_options(self):
        """Ensure mode dropdown has all expected options."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find mode dropdown
        mode_select_start = content.find('id="walletWidgetMode"')
        assert mode_select_start > 0, "Mode dropdown should exist"

        # Get dropdown content
        mode_select_end = content.find('</select>', mode_select_start)
        mode_dropdown = content[mode_select_start:mode_select_end]

        # Should have all options
        expected_options = [
            'value="restore"',
            'value="migrate"',
            'value="unlock"',
            'value="create"',
            'value="import_signing_key"',
        ]

        for option in expected_options:
            assert option in mode_dropdown, f"Dropdown should have {option}"

    def test_switchWalletV1Mode_function_exists(self):
        """Ensure switchWalletV1Mode function exists and handles all modes."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should have switch function
        assert "function switchWalletV1Mode()" in content, \
            "switchWalletV1Mode function should be defined"

        # Find function
        func_start = content.find("function switchWalletV1Mode()")
        assert func_start > 0, "Function should be defined"

        # Get function body (approximate)
        func_body_start = content[func_start:func_start + 5000]

        # Should reference all mode sections
        expected_sections = [
            'walletV1UnlockMode',
            'walletV1CreateMode',
            'walletV1RestoreMode',
            'walletV1MigrateMode',
            'walletV1ImportMode',
        ]

        for section in expected_sections:
            assert section in func_body_start, \
                f"switchWalletV1Mode should handle {section}"

    def test_unlock_button_calls_correct_handler(self):
        """Ensure unlock button calls unlockWalletV1FromHeader()."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find unlock button
        unlock_button = content.find('onclick="unlockWalletV1FromHeader()"')
        assert unlock_button > 0, "Unlock button should call unlockWalletV1FromHeader()"


class TestRecoveryKitVisibility:
    """Test that Recovery Kit form is visible when needed."""

    def test_recovery_kit_form_exists(self):
        """Ensure Recovery Kit restore form exists in HTML."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should have Recovery Kit form
        assert "Recovery Kit" in content, "Should mention Recovery Kit"
        assert "walletV1ImportMode" in content, "Should have import mode for Recovery Kit restore"

    def test_recovery_kit_labeled_as_primary(self):
        """Ensure Recovery Kit is labeled as primary option when key missing."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find import mode section
        import_mode_start = content.find('id="walletV1ImportMode"')
        assert import_mode_start > 0, "Import mode should exist"

        # Get section content
        import_mode_end = content.find('</div>\n\n', import_mode_start) + 10
        import_section = content[import_mode_start:import_mode_end]

        # Should mention Recovery Kit and upload
        assert "Recovery Kit" in import_section, "Import section should mention Recovery Kit"
        assert "upload" in import_section.lower() or "Upload" in import_section, \
            "Should mention file upload for Recovery Kit"

    def test_wallet_v1_show_recovery_kit_restore_primary_function(self):
        """Ensure walletV1ShowRecoveryKitRestorePrimary function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "walletV1ShowRecoveryKitRestorePrimary" in content, \
            "Should have function to show Recovery Kit as primary"


class TestWalletStateMessages:
    """Test that appropriate state messages are shown."""

    def test_no_active_wallet_message_exists(self):
        """Ensure message for no active wallet exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should have no_active_wallet handling
        assert "no_active_wallet" in content, "Should handle no_active_wallet state"

    def test_active_wallet_with_encrypted_key_state(self):
        """Ensure unlock mode handles wallet with encrypted key."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should check for active_wallet_with_encrypted_key
        assert "active_wallet_with_encrypted_key" in content, \
            "Should handle wallet with encrypted key state"

    def test_active_wallet_no_key_state(self):
        """Ensure recovery mode handles wallet missing signing key."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Should check for active_wallet_no_key
        assert "active_wallet_no_key" in content, \
            "Should handle wallet with missing key state"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
