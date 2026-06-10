"""
PR #620: Frontend Route Guard - No /pledge redirects when canonical exists
Tests that Import/Restore/Unlock flows never navigate to /pledge and Create mode is locked
"""
import re


class TestFrontendRouteGuard:
    """Test that frontend never redirects to /pledge when canonical exists"""

    def test_no_pledge_redirect_when_canonical_exists(self):
        """
        CRITICAL TEST: Import/Restore handlers must NOT have /pledge redirects

        Verify: When canonical_v1_address exists, handlers don't redirect to /pledge
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find Import handler
        import_start = html.find('async function performCanonicalImportSigningKey(')
        assert import_start > 0, "performCanonicalImportSigningKey must exist"
        import_section = html[import_start:import_start+3000]

        # CRITICAL: Should check hasCanonical() and return early if missing
        has_canonical_check = re.search(
            r"if\s*\(!hasCanonical\(\)\)|hasCanonical\(\).*alert",
            import_section,
            re.IGNORECASE
        )
        assert has_canonical_check, \
            "Import handler must check hasCanonical() before proceeding"

        # Should NOT redirect to /pledge
        pledge_redirect = re.search(
            r"window\.location.*pledge|location\.href.*pledge",
            import_section,
            re.IGNORECASE
        )
        assert not pledge_redirect, \
            "Import handler must NOT redirect to /pledge"

        print("✅ TEST PASSED: Import handler has canonical check, no /pledge redirect")

    def test_create_mode_hidden_when_canonical_exists(self):
        """
        CRITICAL TEST: Create option must be disabled when canonical exists

        Verify: switchWalletV1Mode() disables 'create' when hasCanonical()
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find switchWalletV1Mode function
        mode_start = html.find('function switchWalletV1Mode(){')
        assert mode_start > 0, "switchWalletV1Mode must exist"
        mode_section = html[mode_start:mode_start+5000]

        # Check for createAllowed condition with hasCanonical()
        create_guard = re.search(
            r"createAllowed\s*=\s*!hasCanonical|const createAllowed.*!hasCanonical",
            mode_section,
            re.IGNORECASE | re.DOTALL
        )
        assert create_guard, \
            "switchWalletV1Mode must set createAllowed = !hasCanonical()"

        print("✅ TEST PASSED: Create mode guarded by hasCanonical()")

    def test_pledge_panel_only_when_no_canonical(self):
        """
        CRITICAL TEST: Pledge panel must only show when NO canonical exists

        Verify: Pledge panel condition includes !hasCanonical()
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find pledge panel logic
        pledge_panel_start = html.find("const pledgePanel = document.getElementById('walletV1PledgeActivationPanel')")
        assert pledge_panel_start > 0, "Pledge panel logic must exist"
        pledge_section = html[pledge_panel_start:pledge_panel_start+2000]

        # Check for !hasCanonical() in condition
        has_canonical_guard = re.search(
            r"!hasCanonical\(\)",
            pledge_section,
            re.IGNORECASE
        )
        assert has_canonical_guard, \
            "Pledge panel condition must include !hasCanonical()"

        print("✅ TEST PASSED: Pledge panel guarded by !hasCanonical()")

    def test_has_canonical_helper_exists(self):
        """
        TEST: Helper function hasCanonical() must be defined

        Verify: Function exists and checks wallet_v1_canonical_address
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find hasCanonical function
        has_canonical_match = re.search(
            r"function\s+hasCanonical\s*\(\)\s*\{",
            html,
            re.IGNORECASE
        )
        assert has_canonical_match, \
            "hasCanonical() helper function must be defined"

        # Get the function body
        func_start = has_canonical_match.start()
        func_body = html[func_start:func_start+500]

        # Should check wallet_v1_canonical_address
        checks_localStorage = re.search(
            r"localStorage\.getItem.*wallet_v1_canonical",
            func_body
        )
        assert checks_localStorage, \
            "hasCanonical() must check localStorage.getItem('wallet_v1_canonical_address')"

        # Should check starts with 'THR'
        checks_thr = re.search(
            r"startsWith\s*\(\s*['\"]THR",
            func_body
        )
        assert checks_thr, \
            "hasCanonical() must verify address starts with 'THR'"

        print("✅ TEST PASSED: hasCanonical() helper correctly defined")

    def test_pledge_button_checks_canonical(self):
        """
        TEST: Pledge button onclick must check hasCanonical()

        Verify: Button has conditional logic guarding /pledge navigation
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find pledge button with hasCanonical check
        pledge_button = re.search(
            r"onclick=['\"]if\s*\(\s*hasCanonical\(\)",
            html,
            re.IGNORECASE
        )
        assert pledge_button, \
            "Pledge button onclick must start with if(hasCanonical())"

        # Verify the full button exists
        full_button = re.search(
            r"<button[^>]*onclick=[^>]*hasCanonical[^>]*>Go to Pledge",
            html,
            re.IGNORECASE
        )
        assert full_button, \
            "Pledge button with hasCanonical check must exist"

        print("✅ TEST PASSED: Pledge button has canonical check")


if __name__ == '__main__':
    test = TestFrontendRouteGuard()

    print("=" * 80)
    print("FRONTEND ROUTE GUARD TESTS - PR #620")
    print("=" * 80)
    print()

    test.test_has_canonical_helper_exists()
    print()
    test.test_no_pledge_redirect_when_canonical_exists()
    print()
    test.test_create_mode_hidden_when_canonical_exists()
    print()
    test.test_pledge_panel_only_when_no_canonical()
    print()
    test.test_pledge_button_checks_canonical()

    print()
    print("=" * 80)
    print("✅ ALL FRONTEND ROUTE GUARD TESTS PASSED")
    print("=" * 80)
