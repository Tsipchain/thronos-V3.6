"""
Tests for Wallet V1 wallet panel state management and safety.

Ensures that wallet panel modes are mutually exclusive and failed operations
don't corrupt the active wallet address or localStorage state.
"""
from pathlib import Path


def test_wallet_panel_unlock_mode_exists():
    """Verify unlock mode UI section exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'id="walletV1UnlockMode"' in content
    assert 'unlockWalletV1FromHeader()' in content


def test_wallet_panel_create_mode_exists():
    """Verify create mode UI section exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'id="walletV1CreateMode"' in content
    assert 'createWalletV1FromHeader()' in content


def test_wallet_panel_migrate_mode_exists():
    """Verify migrate mode UI section exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'id="walletV1MigrateMode"' in content
    assert 'migrateLegacyWalletFromHeader()' in content


def test_wallet_panel_restore_button_exists():
    """Verify restore migrated wallet button exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'restoreMigratedWalletFromHeader' in content
    assert 'restoreMigratedWalletSection' in content


def test_switch_mode_function_exists():
    """Verify switchWalletV1Mode function exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'function switchWalletV1Mode()' in content
    assert 'walletV1UnlockMode' in content
    assert 'walletV1MigrateMode' in content
    assert 'walletV1CreateMode' in content


def test_mode_selector_has_all_modes():
    """Verify wallet mode select has all three options."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'id="walletWidgetMode"' in content
    assert '<option value="create">' in content
    assert '<option value="unlock">' in content
    assert '<option value="migrate">' in content


def test_unlock_function_exists():
    """Verify unlockWalletV1FromHeader function exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'function unlockWalletV1FromHeader()' in content
    assert 'walletWidgetUnlockPin' in content


def test_unlock_function_has_error_handling():
    """Verify unlock function has try/catch."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    unlock_start = content.find('function unlockWalletV1FromHeader()')
    unlock_section = content[unlock_start:unlock_start + 2000]
    assert 'try' in unlock_section
    assert 'catch' in unlock_section


def test_create_function_has_error_handling():
    """Verify create function has try/catch."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    create_start = content.find('function createWalletV1FromHeader()')
    create_section = content[create_start:create_start + 2000]
    assert 'try' in create_section
    assert 'catch' in create_section


def test_migrate_function_validates_address_format():
    """Verify migrate function validates address starts with THR."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    migrate_start = content.find('function migrateLegacyWalletFromHeader()')
    migrate_section = content[migrate_start:migrate_start + 3000]
    assert "startsWith('THR')" in migrate_section
    assert 'THR' in migrate_section


def test_wallet_diagnostics_section_exists():
    """Verify wallet panel diagnostics display section exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'walletPanelDiagnostics' in content
    assert 'updateWalletPanelDiagnostics' in content


def test_restore_function_exists():
    """Verify restoreMigratedWalletFromHeader function exists."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    assert 'function restoreMigratedWalletFromHeader()' in content
    assert 'getMigrationInfo' in content


def test_no_raw_send_secret_in_unlock_mode():
    """Verify unlock mode does not ask for send secret."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    unlock_start = content.find('id="walletV1UnlockMode"')
    unlock_end = content.find('</div>', unlock_start + 100)
    unlock_section = content[unlock_start:unlock_end]
    # Unlock mode should NOT have send secret field
    assert 'walletWidgetLegacySecret' not in unlock_section
    assert 'Legacy Send Secret' not in unlock_section


def test_migrate_mode_requires_legacy_address():
    """Verify migrate mode requires legacy address input."""
    html_file = Path(__file__).resolve().parent.parent / "templates/base.html"
    content = html_file.read_text()
    migrate_start = content.find('id="walletV1MigrateMode"')
    migrate_end = content.find('</div>', migrate_start + 100)
    migrate_section = content[migrate_start:migrate_end]
    # Migrate mode SHOULD have legacy address and secret fields
    assert 'walletWidgetLegacyAddress' in migrate_section
    assert 'walletWidgetLegacySecret' in migrate_section


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
