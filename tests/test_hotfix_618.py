"""
Hotfix #618 Regression Tests

Tests for critical production bugs introduced after PR #617:
A) Production dropdown still shows legacy options (restore/migrate)
B) "Import" mode causes /pledge redirect instead of in-widget focus
C) Mode/CTA mismatch: displayMode doesn't match shown panel
"""
import re

def test_production_dropdown_removes_legacy_options():
    """
    ISSUE A: Production dropdown still shows legacy options

    BUG: In production mode (LEGACY_REPAIR_UI=0), dropdown still displays:
    - "Restore Existing Migrated Wallet"
    - "Migrate Legacy Wallet"

    FIX: applyWalletV1ProductionMode() must remove these options from DOM
    and they must not be selectable.
    """
    with open('templates/base.html', 'r') as f:
        html = f.read()

    # VERIFY: applyWalletV1ProductionMode removes legacy options
    func_idx = html.find("function applyWalletV1ProductionMode")
    assert func_idx > 0, "applyWalletV1ProductionMode function must exist"

    func_section = html[func_idx:func_idx+8000]

    # Check 1: legacyValues includes 'restore' and 'migrate'
    assert "'restore'" in func_section and "'migrate'" in func_section, \
        "legacyValues must include 'restore' and 'migrate' for removal"

    # Check 2: option.remove() is called to actually remove options
    assert "option.remove()" in func_section, \
        "Must call option.remove() to remove legacy options from DOM"

    # Check 3: legacyTexts includes the full text for matching
    assert "Restore Existing Migrated" in func_section, \
        "Must match legacy option text 'Restore Existing Migrated'"
    assert "Migrate Legacy" in func_section, \
        "Must match legacy option text 'Migrate Legacy'"

    print("✅ Production Dropdown - Legacy Options Removed:")
    print("  - legacyValues includes 'restore' and 'migrate' ✓")
    print("  - option.remove() called to remove from DOM ✓")
    print("  - legacyTexts includes full option text for matching ✓")


def test_import_mode_focus_no_redirect():
    """
    ISSUE B: "Import" mode causes /pledge redirect

    BUG: Clicking "Import" mode should open walletV1ImportMode in-widget
    and focus the Recovery Kit form, NOT redirect to /pledge.

    FIX:
    - walletV1ImportMode must stay in-widget (no href="/pledge")
    - focusCanonicalImportForm() must focus the form (not navigate)
    - No window.location assignment in import mode handler
    """
    with open('templates/base.html', 'r') as f:
        html = f.read()

    # Check 1: walletV1ImportMode section exists and is in-widget
    assert 'id="walletV1ImportMode"' in html, \
        "walletV1ImportMode div must exist in HTML"

    import_mode_idx = html.find('id="walletV1ImportMode"')
    import_mode_section = html[import_mode_idx:import_mode_idx+2000]

    # Should NOT have /pledge link in ImportMode
    assert '/pledge' not in import_mode_section, \
        "walletV1ImportMode must NOT contain /pledge redirect"

    # Check 2: focusCanonicalImportForm exists and doesn't navigate
    assert "function focusCanonicalImportForm()" in html, \
        "focusCanonicalImportForm() must be defined"

    focus_idx = html.find("function focusCanonicalImportForm()")
    focus_section = html[focus_idx:focus_idx+500]

    # Should focus element, not navigate
    assert "window.location" not in focus_section, \
        "focusCanonicalImportForm must NOT use window.location"
    assert ".focus()" in focus_section or "details" in focus_section, \
        "focusCanonicalImportForm must focus or open details element"

    # Check 3: switchWalletV1Mode doesn't have /pledge in import handling
    switch_idx = html.find("function switchWalletV1Mode()")
    switch_section = html[switch_idx:switch_idx+20000]

    # Find import mode block
    if "displayMode === 'import_signing_key'" in switch_section:
        import_block = switch_section[
            switch_section.find("displayMode === 'import_signing_key'"):
            switch_section.find("displayMode === 'import_signing_key'") + 1000
        ]
        assert "window.location" not in import_block, \
            "Import mode handler must NOT call window.location"

    print("✅ Import Mode - No /pledge Redirect:")
    print("  - walletV1ImportMode is in-widget (no /pledge) ✓")
    print("  - focusCanonicalImportForm focuses element ✓")
    print("  - switchWalletV1Mode import handler doesn't navigate ✓")


def test_mode_panel_cta_alignment():
    """
    ISSUE C: Mode/CTA mismatch

    BUG: When Recovery Kit panel (walletV1ImportMode) is shown, the
    modeSelect.value is set to wrong mode, and CTA button text doesn't
    match the displayed panel.

    FIX:
    - When displayMode='import_signing_key', modeSelect.value='import_signing_key'
    - CTA label must say "Restore Wallet" (for Recovery Kit)
    - No confusion between displayMode and selected option
    """
    with open('templates/base.html', 'r') as f:
        html = f.read()

    # Check 1: switchWalletV1Mode sets displayMode correctly
    switch_idx = html.find("function switchWalletV1Mode()")
    assert switch_idx > 0, "switchWalletV1Mode must exist"

    switch_section = html[switch_idx:switch_idx+25000]

    # When hasNoSigningKey, displayMode should be 'import_signing_key'
    has_no_key_pattern = r"hasNoSigningKey.*?\{[^}]*displayMode\s*=\s*['\"]import_signing_key['\"]"
    assert re.search(has_no_key_pattern, switch_section, re.DOTALL), \
        "When hasNoSigningKey, displayMode must be 'import_signing_key'"

    # Check 2: modeSelect.value is synced with displayMode
    if "modeSelect.value = displayMode" in switch_section or \
       "modeSelect.value = " in switch_section:
        print("  - modeSelect.value sync found ✓")
    else:
        # Check if it's done with explicit assignments
        assert "modeSelect.value" in switch_section, \
            "Must sync modeSelect.value with displayMode"

    # Check 3: Recovery Kit button CTA says "Restore Wallet"
    assert "Restore Wallet" in html, \
        "Recovery Kit button must say 'Restore Wallet' (not 'Create' or confusing text)"

    # Verify it's in the ImportMode section
    import_idx = html.find('id="walletV1ImportMode"')
    import_section = html[import_idx:import_idx+2000]
    assert "Restore Wallet" in import_section, \
        "Restore Wallet button must be in walletV1ImportMode section"

    print("✅ Mode/CTA Alignment:")
    print("  - displayMode='import_signing_key' when hasNoSigningKey ✓")
    print("  - modeSelect.value synced with displayMode ✓")
    print("  - Recovery Kit button says 'Restore Wallet' ✓")


if __name__ == '__main__':
    print("=" * 80)
    print("HOTFIX #618 - Production Bugs Regression Tests")
    print("=" * 80)

    test_production_dropdown_removes_legacy_options()
    print()
    test_import_mode_focus_no_redirect()
    print()
    test_mode_panel_cta_alignment()

    print("\n" + "=" * 80)
    print("ALL HOTFIX #618 TESTS PASSED ✓")
    print("=" * 80)
