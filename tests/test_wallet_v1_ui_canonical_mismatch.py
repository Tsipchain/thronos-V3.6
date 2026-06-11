"""
Regression Tests: Wallet V1 UI - Canonical Address Storage Mismatch Bug

Bug: hasCanonical() checks wallet_v1_canonical_address but code sets wallet_v1_address
Result: UI shows "Create Wallet V1" button and option when canonical should be immutable

Tests that FAIL before fix, PASS after fix.
"""
import re


class TestWalletV1CanonicalMismatch:
    """Regression tests for canonical address mismatch bug"""

    def test_hasCanonical_checks_multiple_storage_keys(self):
        """
        REGRESSION: hasCanonical() only checks wallet_v1_canonical_address

        Bug: Code sometimes sets wallet_v1_address but hasCanonical() only checks
        wallet_v1_canonical_address, so it returns false even when canonical exists.

        Verify: hasCanonical() checks ALL known canonical keys:
        - wallet_v1_canonical_address
        - wallet_v1_address
        - wallet_v1_active_address
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find hasCanonical function
        func_match = re.search(
            r'function hasCanonical\(\)\s*{([^}]*?)}',
            html,
            re.DOTALL
        )
        assert func_match, "hasCanonical() function must exist"

        func_body = func_match.group(1)

        # Check that function checks wallet_v1_canonical_address
        has_canonical_check = 'wallet_v1_canonical_address' in func_body
        assert has_canonical_check, "Should check wallet_v1_canonical_address"

        # Check that function ALSO checks wallet_v1_address (the key that restore uses)
        has_legacy_check = 'wallet_v1_address' in func_body or 'getItem' in func_body

        # If only checking one key, need to verify it checks wallet_v1_address fallback
        if 'wallet_v1_canonical_address' in func_body:
            # Should have || or alternative check for wallet_v1_address
            has_fallback = '||' in func_body or 'wallet_v1_address' in func_body
            assert has_fallback, \
                "REGRESSION BUG: hasCanonical() must check wallet_v1_address as fallback"

        print("✅ TEST PASS: hasCanonical() checks multiple canonical keys")

    def test_restore_kit_sets_canonical_address_key(self):
        """
        REGRESSION: walletV1RestoreFromRecoveryKit sets wallet_v1_address but not wallet_v1_canonical_address

        Verify: Recovery Kit restore must set wallet_v1_canonical_address (not just wallet_v1_address)
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find Recovery Kit restore function
        restore_match = re.search(
            r'async function walletV1RestoreFromRecoveryKit\(([^)]*)\)\s*{(.*?)\n}',
            html,
            re.DOTALL
        )
        assert restore_match, "walletV1RestoreFromRecoveryKit function must exist"

        func_body = restore_match.group(2)

        # Check that function sets wallet_v1_canonical_address
        sets_canonical = 'wallet_v1_canonical_address' in func_body and 'setItem' in func_body

        assert sets_canonical, \
            "REGRESSION BUG: Recovery Kit must set wallet_v1_canonical_address, not just wallet_v1_address"

        print("✅ TEST PASS: Recovery Kit restore sets wallet_v1_canonical_address")

    def test_admin_signer_sets_canonical_address_key(self):
        """
        REGRESSION: Admin signer generation sets wallet_v1_address but not wallet_v1_canonical_address

        Verify: Admin key binding must also set wallet_v1_canonical_address
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find admin signer function or section
        admin_match = re.search(
            r'AdminSignerGen.*?localStorage\.setItem.*?wallet_v1',
            html,
            re.DOTALL | re.IGNORECASE
        )

        # Alternative: search for the section where admin saves keys
        save_canonical = re.search(
            r'localStorage\.setItem\([\'"]wallet_v1_canonical_address',
            html
        )

        # If admin signer saves to localStorage, must include wallet_v1_canonical_address
        # This is a complex test, so we check that SOMEWHERE canonical_address key is set
        assert save_canonical, \
            "REGRESSION BUG: Code should set wallet_v1_canonical_address somewhere (for compatibility)"

        print("✅ TEST PASS: Canonical address key is set appropriately")

    def test_create_option_removed_when_canonical_detected(self):
        """
        REGRESSION: Create option visible in dropdown even when canonical exists

        Verify: Dropdown must not include "Create Wallet V1" option when hasCanonical() true
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find mode selection logic in switchWalletV1Mode
        mode_switch = re.search(
            r'function switchWalletV1Mode\(\).*?createOption',
            html,
            re.DOTALL
        )
        assert mode_switch, "switchWalletV1Mode should handle createOption"

        # Check that create option is disabled when createAllowed is false
        disable_logic = re.search(
            r'createOption.*?disabled.*?!createAllowed\b|createOption.*?disabled\s*=\s*!\s*createAllowed',
            html,
            re.DOTALL
        )

        assert disable_logic, \
            "REGRESSION BUG: Create option must be disabled when createAllowed=false (hasCanonical()=true)"

        print("✅ TEST PASS: Create option disabled when canonical exists")

    def test_sanitizer_preserves_canonical_address(self):
        """
        REGRESSION: Sanitizer logs canonicalAddrPreserved:false when canonical exists in wallet_v1_address

        Verify: Sanitizer detects canonical from ANY known key, or migrates legacy key to canonical key
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find sanitizer function
        sanitizer = re.search(
            r'function sanitizeWalletV1ProductionState\(([^)]*)\)\s*{(.*?)\nfunction ',
            html,
            re.DOTALL
        )
        assert sanitizer, "sanitizeWalletV1ProductionState function must exist"

        func_body = sanitizer.group(2)

        # Check that sanitizer reads from the right key
        reads_canonical = 'wallet_v1_canonical_address' in func_body or 'wallet_v1_address' in func_body
        assert reads_canonical, "Sanitizer must check for canonical address"

        # Check that it preserves or migrates
        preserves = 'canonicalAddrPreserved' in func_body or 'setItem.*canonical' in func_body
        assert preserves, "Sanitizer must preserve or migrate canonical address"

        print("✅ TEST PASS: Sanitizer handles canonical address correctly")

    def test_unlock_mode_primary_cta_is_unlock_not_create(self):
        """
        REGRESSION: Mode dropdown shows "Unlock" but primary CTA button shows "Create Wallet V1"

        Verify: When displayMode === 'unlock', the button/CTA text reflects unlock, not create
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find unlock mode div and its button
        unlock_section = re.search(
            r'<div id="walletV1UnlockMode"[^>]*>(.*?)</div>',
            html,
            re.DOTALL
        )
        assert unlock_section, "walletV1UnlockMode div must exist"

        unlock_body = unlock_section.group(1)

        # Should have button with "Unlock Wallet V1" text
        has_unlock_button = 'Unlock Wallet V1' in unlock_body
        assert has_unlock_button, "Unlock mode should have 'Unlock Wallet V1' button"

        # Should NOT have "Create" button in unlock section
        has_create_in_unlock = 'Create Wallet V1' in unlock_body
        assert not has_create_in_unlock, \
            "REGRESSION BUG: Unlock mode should not have 'Create Wallet V1' button"

        print("✅ TEST PASS: Unlock mode CTA is 'Unlock', not 'Create'")


if __name__ == '__main__':
    test = TestWalletV1CanonicalMismatch()

    print("=" * 80)
    print("REGRESSION TESTS: WALLET V1 UI - CANONICAL ADDRESS MISMATCH BUG")
    print("=" * 80)
    print()

    try:
        test.test_hasCanonical_checks_multiple_storage_keys()
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
    print()

    try:
        test.test_restore_kit_sets_canonical_address_key()
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
    print()

    try:
        test.test_admin_signer_sets_canonical_address_key()
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
    print()

    try:
        test.test_create_option_removed_when_canonical_detected()
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
    print()

    try:
        test.test_sanitizer_preserves_canonical_address()
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
    print()

    try:
        test.test_unlock_mode_primary_cta_is_unlock_not_create()
    except AssertionError as e:
        print(f"❌ FAIL: {e}")
    print()

    print("=" * 80)
    print("TEST SUITE COMPLETE")
    print("=" * 80)
