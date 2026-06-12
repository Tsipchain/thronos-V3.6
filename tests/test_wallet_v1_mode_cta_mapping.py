"""
Regression Tests: Wallet V1 Mode → CTA Mismatch

Verify: When mode changes, CTA button text and handler match the displayed mode

Test MUST FAIL before fix, PASS after.
"""
import re


class TestWalletV1ModeCTAMapping:
    """Regression tests for mode→CTA deterministic mapping"""

    def test_unlock_mode_cta_is_unlock_not_create(self):
        """
        REGRESSION: Mode dropdown shows 'Unlock' but button says 'Create'

        Verify: When displayMode === 'unlock', CTA button must:
        - Show text: 'Unlock Wallet V1'
        - Call: unlockWalletV1FromHeader()
        - NOT show: 'Create Wallet V1'
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find walletV1UnlockMode div
        unlock_mode = re.search(
            r'<div id="walletV1UnlockMode"[^>]*>.*?</div>',
            html,
            re.DOTALL
        )
        assert unlock_mode, "walletV1UnlockMode div must exist"

        unlock_body = unlock_mode.group(0)

        # Verify button text is "Unlock Wallet V1"
        has_unlock_text = 'Unlock Wallet V1' in unlock_body
        assert has_unlock_text, "Unlock mode button must say 'Unlock Wallet V1'"

        # Verify button calls unlockWalletV1FromHeader
        has_unlock_handler = 'unlockWalletV1FromHeader()' in unlock_body
        assert has_unlock_handler, "Unlock mode button must call unlockWalletV1FromHeader()"

        # Verify it does NOT say "Create Wallet V1"
        has_create_text = 'Create Wallet V1' in unlock_body
        assert not has_create_text, \
            "REGRESSION BUG: Unlock mode button must NOT say 'Create Wallet V1'"

        print("✅ TEST PASS: Unlock mode CTA is 'Unlock', not 'Create'")

    def test_create_mode_cta_is_create(self):
        """
        REGRESSION: Create mode button says something other than 'Create Wallet V1'

        Verify: When displayMode === 'create', CTA button must:
        - Show text: 'Create Wallet V1'
        - Call: createWalletV1FromHeader()
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find walletV1CreateMode div
        create_mode = re.search(
            r'<div id="walletV1CreateMode"[^>]*>.*?</div>',
            html,
            re.DOTALL
        )
        assert create_mode, "walletV1CreateMode div must exist"

        create_body = create_mode.group(0)

        # Verify button text is "Create Wallet V1"
        has_create_text = 'Create Wallet V1' in create_body
        assert has_create_text, "Create mode button must say 'Create Wallet V1'"

        # Verify button calls createWalletV1FromHeader
        has_create_handler = 'createWalletV1FromHeader()' in create_body
        assert has_create_handler, "Create mode button must call createWalletV1FromHeader()"

        print("✅ TEST PASS: Create mode CTA is 'Create Wallet V1'")

    def test_import_mode_cta_is_import_or_restore(self):
        """
        REGRESSION: Import/Restore mode button CTA text mismatch

        Verify: When displayMode === 'import_signing_key', CTA button must:
        - Show text related to import/restore (e.g., 'Import', 'Restore')
        - NOT show: 'Create Wallet V1' or 'Unlock'
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find walletV1ImportMode div
        import_mode = re.search(
            r'<div id="walletV1ImportMode"[^>]*>.*?</div>',
            html,
            re.DOTALL
        )
        assert import_mode, "walletV1ImportMode div must exist"

        import_body = import_mode.group(0)

        # Verify it has import/restore related button (not create, not unlock)
        has_import_or_restore = any(text in import_body for text in [
            'Import', 'Restore', 'Recovery Kit', 'import', 'restore'
        ])
        assert has_import_or_restore, \
            "Import mode must have button text related to import/restore"

        # Verify it does NOT say "Create Wallet V1"
        has_create_text = 'Create Wallet V1' in import_body
        assert not has_create_text, \
            "REGRESSION BUG: Import mode must NOT show 'Create' button"

        # Verify it does NOT say "Unlock Wallet V1"
        has_unlock_text = 'Unlock Wallet V1' in import_body
        assert not has_unlock_text, \
            "REGRESSION BUG: Import mode must NOT show 'Unlock' button"

        print("✅ TEST PASS: Import mode CTA is restore/import, not Create/Unlock")

    def test_displayMode_synced_to_dropdown(self):
        """
        REGRESSION: Dropdown shows one mode but UI shows different mode

        Verify: switchWalletV1Mode() syncs modeSelect.value to displayMode
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find the sync logic in switchWalletV1Mode
        sync_check = re.search(
            r'modeSelect\.value = displayMode|modeSelect\.value = .*displayMode',
            html
        )
        assert sync_check, \
            "REGRESSION BUG: switchWalletV1Mode() must sync dropdown value to displayMode"

        print("✅ TEST PASS: Dropdown synced to displayMode")

    def test_mode_divs_shown_hidden_correctly(self):
        """
        REGRESSION: Wrong mode div is shown (hardcoded mode instead of displayMode)

        Verify: switchWalletV1Mode() uses displayMode (not mode parameter) to show/hide divs
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find div display logic - should use displayMode
        display_unlock = re.search(
            r'unlockEl.*?style\.display.*?\(displayMode === [\'"]unlock[\'"]',
            html,
            re.DOTALL
        )
        assert display_unlock, \
            "REGRESSION BUG: unlockEl visibility must use (displayMode === 'unlock')"

        display_create = re.search(
            r'createEl.*?style\.display.*?\(displayMode === [\'"]create[\'"]',
            html,
            re.DOTALL
        )
        assert display_create, \
            "REGRESSION BUG: createEl visibility must use (displayMode === 'create')"

        print("✅ TEST PASS: Mode divs shown/hidden based on displayMode")


if __name__ == '__main__':
    test = TestWalletV1ModeCTAMapping()

    print("=" * 80)
    print("REGRESSION TESTS: WALLET V1 MODE → CTA MISMATCH")
    print("=" * 80)
    print()

    tests = [
        ("Unlock mode CTA", test.test_unlock_mode_cta_is_unlock_not_create),
        ("Create mode CTA", test.test_create_mode_cta_is_create),
        ("Import mode CTA", test.test_import_mode_cta_is_import_or_restore),
        ("Dropdown sync", test.test_displayMode_synced_to_dropdown),
        ("Mode divs visibility", test.test_mode_divs_shown_hidden_correctly),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ FAIL: {name}")
            print(f"   {e}")
            failed += 1
        print()

    print("=" * 80)
    print(f"TEST RESULTS: {passed} PASS, {failed} FAIL")
    print("=" * 80)

    if failed == 0:
        print("\n✅ All tests PASS - Mode→CTA mapping is correct")
    else:
        print(f"\n⚠️  {failed} test(s) FAILED - Fix needed")
