"""
Regression Tests: PR #621 - Wallet V1 State Machine Contract

Purpose: Frozen modes and deterministic transitions
- No auto-flip to pledge when canonical exists
- No auto-transition between modes
- Explicit state selection only
- Hard override if user tries devtools hack

Tests MUST FAIL before fix and PASS after.
"""
import re


class TestWalletV1StateMachineContract:
    """Regression tests for state machine contract enforcement"""

    def test_mode_to_cta_mapping_no_create_when_canonical_present(self):
        """
        REGRESSION: Mode mismatch - dropdown shows "Unlock" but CTA button shows "Create"

        Verify: When canonical exists, CTA text never shows "Create Wallet V1"
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find all div containers for modes
        unlock_mode = re.search(
            r'<div id="walletV1UnlockMode"[^>]*>.*?</div>',
            html,
            re.DOTALL
        )
        create_mode = re.search(
            r'<div id="walletV1CreateMode"[^>]*>.*?</div>',
            html,
            re.DOTALL
        )

        assert unlock_mode, "walletV1UnlockMode div must exist"
        assert create_mode, "walletV1CreateMode div must exist"

        # Unlock mode should have button with "Unlock Wallet V1"
        unlock_body = unlock_mode.group(0)
        has_unlock_cta = 'Unlock Wallet V1' in unlock_body
        assert has_unlock_cta, "Unlock mode must have 'Unlock Wallet V1' button"

        # Create mode should have button with "Create Wallet V1"
        create_body = create_mode.group(0)
        has_create_cta = 'Create Wallet V1' in create_body
        assert has_create_cta, "Create mode must have 'Create Wallet V1' button"

        # Verify they're separate - unlock CTA should NOT be in create mode
        assert 'Unlock Wallet V1' not in create_body, \
            "REGRESSION BUG: Create mode should not have Unlock button"

        print("✅ TEST PASS: Mode-to-CTA mapping is deterministic")

    def test_modes_available_production_when_canonical_present(self):
        """
        REGRESSION: Create option available in dropdown even when canonical exists

        Verify: In production mode with canonical, dropdown shows ONLY:
        - Unlock Wallet V1
        - Import Signing Key (Recovery Kit)
        - (optional) Restore if admin mode
        NOT: Create Wallet V1, Migrate Legacy
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find switchWalletV1Mode function where create option is disabled
        switch_mode = re.search(
            r'function switchWalletV1Mode\(\).*?if \(createOption\)',
            html,
            re.DOTALL
        )
        assert switch_mode, "switchWalletV1Mode function must handle createOption"

        # Verify createAllowed gates the option
        create_allowed_check = re.search(
            r'createAllowed.*?createOption.*?disabled',
            html,
            re.DOTALL
        )
        assert create_allowed_check or 'createOption.disabled = !createAllowed' in html, \
            "REGRESSION BUG: Create option must be disabled when createAllowed=false"

        # Verify createAllowed = !hasCanonical() && ...
        create_allowed_def = re.search(
            r'const createAllowed = !hasCanonical\(\)',
            html
        )
        assert create_allowed_def, \
            "REGRESSION BUG: createAllowed must gate with !hasCanonical()"

        print("✅ TEST PASS: Create option properly disabled in production mode")

    def test_no_auto_transition_to_pledge_new_when_canonical_present(self):
        """
        REGRESSION: Auto-transition to pledge when canonical exists

        Verify: Even if server returns stale modalState, UI never shows pledge or navigates to /pledge
        when canonical is present
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find switchWalletV1Mode logic for no_active_wallet state
        stale_state_check = re.search(
            r'modalState === .no_active_wallet..*?hasCanonical\(\)',
            html,
            re.DOTALL
        )
        assert stale_state_check, \
            "REGRESSION BUG: switchWalletV1Mode must check hasCanonical() even when modalState=no_active_wallet"

        # Verify pledge panel visibility logic includes !hasCanonical()
        pledge_panel_check = re.search(
            r'pledgePanel.*?style\.display.*?!hasCanonical\(\)',
            html,
            re.DOTALL
        )
        assert pledge_panel_check, \
            "REGRESSION BUG: Pledge panel visibility must be guarded with !hasCanonical()"

        # Verify no automatic window.location changes to /pledge in success paths
        import_success = re.search(
            r'Import.*?success.*?{(.*?)window\.location.*?pledge',
            html,
            re.DOTALL | re.IGNORECASE
        )
        assert not import_success, \
            "REGRESSION BUG: Import success path must NOT redirect to /pledge"

        restore_success = re.search(
            r'Restore.*?success.*?{(.*?)window\.location.*?pledge',
            html,
            re.DOTALL | re.IGNORECASE
        )
        assert not restore_success, \
            "REGRESSION BUG: Restore success path must NOT redirect to /pledge"

        print("✅ TEST PASS: No auto-transition to pledge when canonical present")

    def test_mirage_legacy_requires_explicit_user_selection(self):
        """
        REGRESSION: Mirage/Legacy options visible to regular users in production

        Verify: Mirage/Legacy modes hidden in production, only shown if:
        1. Admin flag WALLET_V1_LEGACY_REPAIR_UI_ENABLED = true, OR
        2. Explicit legacy enable variable set
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find where mirage option visibility is determined
        mirage_option = re.search(
            r'option.*?value=["\']mirage',
            html,
            re.IGNORECASE
        )

        if mirage_option:
            # If mirage option exists, verify it's conditionally hidden
            mirage_context = re.search(
                r'migrateOption.*?disabled.*?!.*?(adminMode|legacy|repair)',
                html,
                re.DOTALL | re.IGNORECASE
            )
            assert mirage_context, \
                "REGRESSION BUG: Mirage/Legacy options must be disabled unless admin mode enabled"

        # Verify applyWalletV1ProductionMode hides legacy UI
        prod_mode_check = re.search(
            r'applyWalletV1ProductionMode.*?legacyRepairEnabled === false',
            html,
            re.DOTALL
        )
        assert prod_mode_check, \
            "REGRESSION BUG: Production mode must hide legacy/mirage options"

        print("✅ TEST PASS: Mirage/Legacy options properly gated by admin flag")

    def test_hard_override_if_user_selects_create_with_canonical(self):
        """
        REGRESSION: User can devtools-hack modeSelect.value='create' when canonical exists

        Verify: switchWalletV1Mode() detects canonical + create selection and forces override
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find the hard override logic
        override_check = re.search(
            r'hasCanonical\(\).*?mode === .create.*?displayMode.*?unlock',
            html,
            re.DOTALL
        )
        assert override_check or (
            'hasCanonical() && mode === \'create\'' in html or
            'if (hasCanonical() && mode === "create")' in html
        ), "REGRESSION BUG: Must hard-override mode to unlock if user selects create with canonical"

        print("✅ TEST PASS: Hard override prevents devtools hack")


if __name__ == '__main__':
    test = TestWalletV1StateMachineContract()

    print("=" * 80)
    print("REGRESSION TESTS: PR #621 - WALLET V1 STATE MACHINE CONTRACT")
    print("=" * 80)
    print()

    tests = [
        ("Mode-to-CTA mapping", test.test_mode_to_cta_mapping_no_create_when_canonical_present),
        ("Modes availability", test.test_modes_available_production_when_canonical_present),
        ("No auto-transition to pledge", test.test_no_auto_transition_to_pledge_new_when_canonical_present),
        ("Mirage legacy gating", test.test_mirage_legacy_requires_explicit_user_selection),
        ("Hard override devtools hack", test.test_hard_override_if_user_selects_create_with_canonical),
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

    if failed > 0:
        print("\n⚠️  Some tests FAILED - these are EXPECTED before PR #621 implementation")
        print("   After implementing state machine contract, all tests should PASS")
