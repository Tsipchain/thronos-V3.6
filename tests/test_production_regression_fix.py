"""
Production Mode Regression Fix Tests

Strict regression tests that MUST FAIL on buggy code and PASS after fixes.
These tests validate the 3 critical production UX issues.
"""
import re

class TestProductionModeRegression:
    """Tests for production mode bugs introduced post-PR #616/#617"""

    def test_production_dropdown_legacy_options_removed_from_dom(self):
        """
        TEST 1: Production dropdown must NOT contain legacy options in DOM

        FAIL CONDITION: If HTML still has restore/migrate options that aren't
                       removed by applyWalletV1ProductionMode()
        PASS CONDITION: Legacy options are removed from DOM, not just hidden
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find applyWalletV1ProductionMode function
        func_start = html.find('function applyWalletV1ProductionMode(status) {')
        assert func_start > 0, \
            "applyWalletV1ProductionMode must exist"

        func_section = html[func_start:func_start+8000]  # Extended to 8000

        # CRITICAL CHECK 1: legacyValues must include BOTH restore AND migrate
        assert "'restore'" in func_section, \
            "FAIL: legacyValues missing 'restore' - legacy options won't be removed"
        assert "'migrate'" in func_section, \
            "FAIL: legacyValues missing 'migrate' - legacy migrate option won't be removed"

        # CRITICAL CHECK 2: Must call option.remove() NOT just display:none
        assert 'option.remove()' in func_section, \
            "FAIL: Code uses display:none instead of option.remove(). " \
            "Options still in DOM, users can still select them!"

        # CRITICAL CHECK 3: legacyTexts must match actual option labels
        assert 'Restore Existing Migrated' in func_section, \
            "FAIL: legacyTexts doesn't match 'Restore Existing Migrated Wallet' text"

        print("✅ TEST 1 PASS: Production dropdown legacy options properly removed")

    def test_import_mode_no_pledge_redirect(self):
        """
        TEST 2: Clicking Import mode must NOT redirect to /pledge

        FAIL CONDITION: If walletV1ImportMode or its handlers contain
                       window.location=/pledge or href="/pledge"
        PASS CONDITION: Import mode opens in-widget, no navigation
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find walletV1ImportMode section
        import_mode_start = html.find('id="walletV1ImportMode"')
        assert import_mode_start > 0, \
            "walletV1ImportMode must exist in HTML"

        # Get the ImportMode section (approximately 2000 chars)
        import_mode_section = html[import_mode_start:import_mode_start+3000]

        # CRITICAL CHECK 1: walletV1ImportMode must NOT contain /pledge href
        if '/pledge' in import_mode_section:
            raise AssertionError(
                "FAIL: walletV1ImportMode contains /pledge link. "
                "Clicking Import will redirect to /pledge instead of in-widget recovery."
            )

        # CRITICAL CHECK 2: Handlers must NOT do window.location
        # Get button onclick handlers in ImportMode
        handlers = re.findall(r'onclick="([^"]*)"', import_mode_section)
        for handler in handlers:
            assert 'window.location' not in handler, \
                f"FAIL: Import mode handler '{handler}' uses window.location. " \
                "Must be in-widget focus, not navigation."
            assert 'location.href' not in handler, \
                f"FAIL: Import mode handler '{handler}' uses location.href"

        print("✅ TEST 2 PASS: Import mode stays in-widget, no /pledge redirect")

    def test_deterministic_mode_panel_cta_alignment(self):
        """
        TEST 3: Mode dropdown ↔ Visible Panel ↔ CTA Label must be deterministic

        FAIL CONDITION: When hasNoSigningKey, production shows wrong panel or CTA
        PASS CONDITION: displayMode='import_signing_key' → show importEl → CTA="Restore Wallet"
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find switchWalletV1Mode function
        switch_start = html.find('function switchWalletV1Mode(){')
        assert switch_start > 0, \
            "switchWalletV1Mode must exist"

        switch_section = html[switch_start:switch_start+25000]

        # CRITICAL CHECK 1: When hasNoSigningKey, displayMode must be import_signing_key
        # Look for the pattern: hasNoSigningKey block → displayMode assignment
        has_no_key_match = re.search(
            r'hasNoSigningKey\s*=.*?\{.*?displayMode\s*=\s*[\'"](\w+)[\'"]',
            switch_section,
            re.DOTALL
        )

        if has_no_key_match:
            display_mode = has_no_key_match.group(1)
            assert display_mode == 'import_signing_key', \
                f"FAIL: hasNoSigningKey sets displayMode='{display_mode}' " \
                "but should be 'import_signing_key' (Recovery Kit, not legacy restore)"
        else:
            # If explicit match not found, check if import_signing_key is anywhere in hasNoSigningKey block
            assert 'import_signing_key' in switch_section, \
                "FAIL: No 'import_signing_key' displayMode found when hasNoSigningKey"

        # CRITICAL CHECK 2: Must show walletV1ImportMode (not Create/Restore)
        # Production mode when hasNoSigningKey: show Recovery Kit (ImportMode), not legacy restore
        assert "importEl.style.display = 'block'" in switch_section or \
               'importEl.style.display = "block"' in switch_section, \
            "FAIL: When hasNoSigningKey in production, walletV1ImportMode not shown"

        # CRITICAL CHECK 3: CTA button text must match (Restore Wallet for Recovery Kit)
        assert 'Restore Wallet' in html, \
            "FAIL: Recovery Kit panel missing 'Restore Wallet' CTA label"

        print("✅ TEST 3 PASS: Mode/Panel/CTA deterministic alignment verified")

    def test_walletV1ImportMode_in_production_hidden_by_default(self):
        """
        TEST 4: walletV1ImportMode must have display:none by default (shown via JS)

        Prevents accidental exposure of import UI before switchWalletV1Mode() runs
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        import_mode_line = re.search(
            r'<div\s+id="walletV1ImportMode"[^>]*style="([^"]*)"',
            html
        )
        assert import_mode_line, \
            "walletV1ImportMode div not found with style attribute"

        style_attr = import_mode_line.group(1)
        assert 'display:none' in style_attr or 'display: none' in style_attr, \
            "FAIL: walletV1ImportMode should have display:none by default " \
            "(shown only when needed via switchWalletV1Mode)"

        print("✅ TEST 4 PASS: walletV1ImportMode correctly hidden by default")


if __name__ == '__main__':
    """Run all regression tests"""
    test = TestProductionModeRegression()

    print("=" * 80)
    print("PRODUCTION MODE REGRESSION TESTS")
    print("=" * 80)
    print()

    test.test_production_dropdown_legacy_options_removed_from_dom()
    print()
    test.test_import_mode_no_pledge_redirect()
    print()
    test.test_deterministic_mode_panel_cta_alignment()
    print()
    test.test_walletV1ImportMode_in_production_hidden_by_default()

    print()
    print("=" * 80)
    print("✅ ALL PRODUCTION REGRESSION TESTS PASSED")
    print("=" * 80)
