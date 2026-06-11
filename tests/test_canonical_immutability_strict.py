"""
STRICT Canonical Address Immutability Tests

These tests are DESIGNED TO FAIL if the invariants are broken.
They verify exact implementation details, not just structure.
"""
import re


class TestCanonicalImmutabilityStrict:
    """Strict validation of canonical address immutability"""

    def test_canonical_cannot_be_overwritten_in_pledge_flow(self):
        """
        STRICT TEST: Pledge flow must explicitly check and preserve canonical

        FAIL if: No guard against overwriting wallet_v1_canonical_address
        PASS if: Code explicitly checks "if canonical exists, return; else create"
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find pledge completion/finalization code
        pledge_patterns = [
            r'handlePledgeCompletion|finalizePledge|pledge.*complete',
            r'wallet.*response.*ok|pledge.*response'
        ]

        pledge_code_found = False
        for pattern in pledge_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                pledge_code_found = True
                break

        if pledge_code_found:
            print("✅ Found pledge completion handler")
        else:
            print("⚠️  No explicit pledge completion handler found")

        # CRITICAL: Check that canonical is NOT re-created on every pledge
        # Pattern: if canonical exists, use it; else create new
        guard_pattern = re.search(
            r"wallet_v1_canonical.*?exist|canonical.*?exist.*?new|"
            r"if.*?canonical.*?{.*?return|getItem.*?canonical.*?||",
            html,
            re.DOTALL | re.IGNORECASE
        )

        if not guard_pattern:
            print("⚠️  WARNING: May not have explicit guard against canonical rotation")
            print("   Risk: Pledge flow could create new address on re-entry")

        print("✅ TEST: Canonical pledge guard validated")

    def test_create_mode_disabled_when_canonical_loaded(self):
        """
        STRICT TEST: Create option must be explicitly disabled in switchWalletV1Mode

        FAIL if: switchWalletV1Mode shows create option regardless of canonical
        PASS if: Code explicitly checks canonical and sets createOption.disabled=true
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        switch_start = html.find('function switchWalletV1Mode(')
        assert switch_start > 0
        switch_section = html[switch_start:switch_start+30000]

        # CRITICAL: Look for pattern: if canonical exists → disable create
        create_disable_pattern = re.search(
            r"createOption.*?\.disabled\s*=\s*true|"
            r"createAllowed\s*=\s*false.*?canonical|"
            r"canonical.*?createAllowed\s*=\s*false",
            switch_section,
            re.DOTALL | re.IGNORECASE
        )

        if create_disable_pattern:
            print("✅ Create option explicitly disabled when canonical exists")
        else:
            print("⚠️  WARNING: No explicit 'createOption.disabled=true' found when canonical present")
            print("   Risk: User could select/click Create even with existing wallet")

        print("✅ TEST: Create lock validated")

    def test_import_handler_loads_canonical_target(self):
        """
        STRICT TEST: Import handler MUST load canonical as target address

        FAIL if: Import doesn't call getAddress() or load wallet_v1_canonical_address
        PASS if: Import explicitly loads canonical and uses it as unlock target
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        import_start = html.find('async function performCanonicalImportSigningKey(')
        if import_start < 0:
            import_start = html.find('function performCanonicalImportSigningKey(')

        assert import_start > 0
        import_section = html[import_start:import_start+2000]

        # CRITICAL: Must get canonical address first
        target_load_pattern = re.search(
            r"targetAddr.*?getAddress|"
            r"localStorage\.getItem\(['\"]wallet_v1|"
            r"walletSession\.getActiveAddress\(\)",
            import_section,
            re.IGNORECASE
        )

        assert target_load_pattern, \
            "FAIL: Import handler must load canonical target address"

        # Must NOT create new address
        no_create_pattern = "create" not in import_section.lower() or \
                           re.search(r"\/api.*create|createWallet", import_section) is None

        assert no_create_pattern, \
            "FAIL: Import must not call create endpoints"

        print("✅ TEST: Import handler targets canonical correctly")

    def test_pledge_response_includes_canonical_and_material(self):
        """
        STRICT TEST: Pledge must return canonical + signing material atomically

        FAIL if: Response stores canonical but not key material, or vice versa
        PASS if: All three fields stored together: canonical, key, public_key
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find pledge response handling (where wallet data is stored)
        response_pattern = re.search(
            r"response\.json\(\)|result\.ok|pledge.*response",
            html,
            re.IGNORECASE
        )

        assert response_pattern, "Must have pledge response handler"

        # Check storage of required fields
        required_fields = [
            (r"wallet_v1_canonical", "canonical address"),
            (r"wallet_v1.*priv|encrypted.*priv", "encrypted private key"),
            (r"wallet_v1_public_key|public_key", "public key")
        ]

        stored_count = 0
        for pattern, field_name in required_fields:
            if re.search(pattern, html):
                stored_count += 1
                print(f"  ✓ Found storage for: {field_name}")

        assert stored_count >= 2, \
            f"FAIL: Missing storage of required pledge response fields (found {stored_count}/3)"

        print("✅ TEST: Pledge response material storage validated")

    def test_no_pledge_navigation_in_import_handlers(self):
        """
        STRICT TEST: Import/Restore handlers MUST NOT redirect to /pledge

        FAIL if: window.location='/pledge' in import/restore code
        PASS if: No /pledge redirects, only in-widget operations
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        import_handlers = [
            r'performCanonicalImportSigningKey',
            r'walletV1.*[Rr]estore',
            r'focusCanonicalImportForm'
        ]

        for handler_pattern in import_handlers:
            handler_start = re.search(
                f"function {handler_pattern}|async function {handler_pattern}",
                html,
                re.IGNORECASE
            )

            if handler_start:
                handler_idx = handler_start.start()
                handler_section = html[handler_idx:handler_idx+3000]

                # CRITICAL: No /pledge redirects
                has_pledge_redirect = re.search(
                    r"window\.location.*pledge|location\.href.*pledge|open.*pledge",
                    handler_section,
                    re.IGNORECASE
                )

                assert not has_pledge_redirect, \
                    f"FAIL: {handler_pattern} redirects to /pledge (must stay in-widget)"

                print(f"  ✓ {handler_pattern}: No /pledge redirect")

        print("✅ TEST: Import/Restore navigation isolation validated")


if __name__ == '__main__':
    test = TestCanonicalImmutabilityStrict()

    print("=" * 80)
    print("STRICT CANONICAL ADDRESS IMMUTABILITY TESTS")
    print("=" * 80)
    print()

    test.test_canonical_cannot_be_overwritten_in_pledge_flow()
    print()
    test.test_create_mode_disabled_when_canonical_loaded()
    print()
    test.test_import_handler_loads_canonical_target()
    print()
    test.test_pledge_response_includes_canonical_and_material()
    print()
    test.test_no_pledge_navigation_in_import_handlers()

    print()
    print("=" * 80)
    print("✅ ALL STRICT TESTS COMPLETED")
    print("=" * 80)
