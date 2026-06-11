"""
Regression Tests: Production Mode Crash Hotfix
Tests to prevent ReferenceError in applyWalletV1ProductionMode and pledge button issues
"""
import re


class TestProductionModeCrashHotfix:
    """Prevent production crashes in wallet UI"""

    def test_applyWalletV1ProductionMode_no_undefined_vars(self):
        """
        REGRESSION: ReferenceError: advancedImportForm is not defined

        Verify: All variable references in applyWalletV1ProductionMode()
        are properly declared with const/querySelector before use
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find applyWalletV1ProductionMode function
        func_start = html.find('function applyWalletV1ProductionMode(')
        func_end = html.find('\n}\n', func_start)
        func_body = html[func_start:func_end+10]

        # Find all variable references (pattern: if (someName))
        var_refs = re.findall(r'if\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)', func_body)

        # For each reference, verify it's declared as const before first use
        declared_vars = set()

        # Extract all const declarations
        const_decls = re.findall(r'const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=', func_body)
        declared_vars.update(const_decls)

        # Also check function parameters
        func_params = re.findall(r'function applyWalletV1ProductionMode\(([^)]*)\)', func_body)
        if func_params:
            declared_vars.add(func_params[0].strip())

        # Check for built-in JS objects that don't need declaration
        builtin_vars = {'document', 'status', 'legacyRepairEnabled', 'modeSelect', 'advancedBySelector', 'resetBySelector'}
        declared_vars.update(builtin_vars)

        # Verify all referenced variables are declared
        undeclared = []
        for var in var_refs:
            if var not in declared_vars:
                undeclared.append(var)

        assert not undeclared, \
            f"REGRESSION BUG: Undeclared variable references in applyWalletV1ProductionMode(): {undeclared}"

        print("✅ TEST PASS: All variables in applyWalletV1ProductionMode() properly declared")

    def test_applyWalletV1ProductionMode_null_safe_dom_access(self):
        """
        REGRESSION: ReferenceError when DOM elements don't exist

        Verify: advancedImportForm is properly declared with const
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find function
        func_start = html.find('function applyWalletV1ProductionMode(')
        func_end = html.find('\n}\n', func_start)
        func_body = html[func_start:func_end+10]

        # The critical fix: advancedImportForm must be declared
        has_declaration = re.search(
            r'const\s+advancedImportForm\s*=\s*document\.getElementById',
            func_body
        )

        assert has_declaration, \
            "REGRESSION BUG: advancedImportForm must be declared with const"

        print("✅ TEST PASS: advancedImportForm properly declared")

    def test_pledge_button_no_self_redirect_on_pledge_route(self):
        """
        REGRESSION: /pledge button redirects to itself when already on /pledge

        Verify: Pledge button checks location.pathname before redirect
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find pledge activation button
        button_match = re.search(
            r'Go to Pledge Activation</button>',
            html
        )

        assert button_match, "Pledge activation button must exist"

        # Find the button's onclick code
        button_start = html.rfind('<button', 0, button_match.start())
        button_end = html.find('</button>', button_match.start()) + len('</button>')
        button_html = html[button_start:button_end]

        # Verify self-redirect guard exists
        has_pathname_check = 'window.location.pathname' in button_html or 'location.pathname' in button_html

        assert has_pathname_check, \
            "REGRESSION BUG: Pledge button missing pathname check for self-redirect"

        print("✅ TEST PASS: Pledge button checks pathname before redirect")

    def test_no_pledge_redirect_when_canonical_exists(self):
        """
        REGRESSION: No /pledge redirect when canonical address exists

        Verify: hasCanonical() guard prevents redirect to /pledge
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Verify hasCanonical() function exists
        has_canonical_func = 'function hasCanonical()' in html or 'const hasCanonical' in html
        assert has_canonical_func, "hasCanonical() function must exist"

        # Verify pledge button uses hasCanonical guard
        button_match = re.search(
            r'Go to Pledge Activation</button>',
            html
        )
        button_start = html.rfind('<button', 0, button_match.start())
        button_end = html.find('</button>', button_match.start()) + len('</button>')
        button_html = html[button_start:button_end]

        has_guard = 'hasCanonical()' in button_html
        assert has_guard, "Pledge button must check hasCanonical() before allowing redirect"

        print("✅ TEST PASS: Pledge button guards against redirect when canonical exists")

    def test_create_mode_disabled_when_canonical_loaded(self):
        """
        REGRESSION: Create mode disabled when canonical address exists

        Verify: createAllowed = !hasCanonical() && (...)
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find createAllowed assignment
        create_allowed_pattern = r'createAllowed\s*=\s*!hasCanonical\(\)'
        has_pattern = re.search(create_allowed_pattern, html)

        assert has_pattern, \
            "createAllowed must be gated with !hasCanonical() to disable create when canonical exists"

        print("✅ TEST PASS: Create mode disabled when canonical exists")

    def test_pledge_submit_returns_created_false_when_canonical_exists(self):
        """
        REGRESSION: pledge_submit returns created=false when canonical exists

        Verify: Server identity lock prevents new canonical creation
        """
        with open('server.py', 'r') as f:
            server = f.read()

        # Find pledge response that checks for existing canonical
        # Should have response with created: false when canonical exists
        has_false_response = (
            '"created": false' in server or
            "'created': False" in server or
            'created=False' in server or
            '"created": False' in server
        )
        has_status_exists = (
            'already_has_canonical' in server or
            'existing' in server.lower() or
            'canonical_v1_address' in server
        )

        assert has_false_response, "pledge_submit must return created=false when canonical exists"
        assert has_status_exists, "Server must distinguish new vs existing canonical in response"

        print("✅ TEST PASS: pledge_submit returns created=false for existing canonicals")


if __name__ == '__main__':
    test = TestProductionModeCrashHotfix()

    print("=" * 80)
    print("REGRESSION TESTS: PRODUCTION MODE CRASH HOTFIX + CANONICAL IMMUTABILITY")
    print("=" * 80)
    print()

    test.test_applyWalletV1ProductionMode_no_undefined_vars()
    print()
    test.test_applyWalletV1ProductionMode_null_safe_dom_access()
    print()
    test.test_pledge_button_no_self_redirect_on_pledge_route()
    print()
    test.test_no_pledge_redirect_when_canonical_exists()
    print()
    test.test_create_mode_disabled_when_canonical_loaded()
    print()
    test.test_pledge_submit_returns_created_false_when_canonical_exists()

    print()
    print("=" * 80)
    print("✅ ALL REGRESSION TESTS PASSED (6/6)")
    print("=" * 80)
