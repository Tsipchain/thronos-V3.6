"""
PR #620.1: Authoritative State Refresh - Server truth after import/restore
Tests that import/restore refresh wallet state from server and prevent pledge panel from showing
"""
import re


class TestAuthoritativeStateRefresh:
    """Test that import/restore refresh state from server"""

    def test_refresh_wallet_state_function_exists(self):
        """
        TEST: refreshWalletStateFromServer() must be defined and callable

        Verify: Function exists, takes canonicalAddr, calls /api/wallet/v1/status
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find refreshWalletStateFromServer function
        func_pattern = re.search(
            r"async function refreshWalletStateFromServer\s*\(\s*canonicalAddr\s*\)\s*\{",
            html,
            re.IGNORECASE
        )
        assert func_pattern, "refreshWalletStateFromServer() function must be defined"

        func_start = func_pattern.start()
        func_body = html[func_start:func_start+2000]

        # Should call /api/wallet/v1/status
        calls_status = re.search(
            r"/api/wallet/v1/status.*address",
            func_body,
            re.IGNORECASE
        )
        assert calls_status, "Function must call /api/wallet/v1/status?address=..."

        # Should store in window.walletV1LastStatus
        stores_status = re.search(
            r"window\.walletV1LastStatus\s*=\s*status",
            func_body
        )
        assert stores_status, "Function must store result in window.walletV1LastStatus"

        print("✅ TEST PASSED: refreshWalletStateFromServer() correctly defined")

    def test_import_handler_calls_refresh_state(self):
        """
        CRITICAL TEST: performCanonicalImportSigningKey() must call refreshWalletStateFromServer()

        Verify: After import success, refreshWalletStateFromServer() is called
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find import handler
        import_start = html.find('async function performCanonicalImportSigningKey(')
        assert import_start > 0, "Import handler must exist"
        import_section = html[import_start:import_start+5000]

        # Should call refreshWalletStateFromServer in success path
        has_refresh = re.search(
            r"refreshWalletStateFromServer\s*\(\s*canonical\s*\)",
            import_section,
            re.IGNORECASE
        )
        assert has_refresh, \
            "Import success path must call refreshWalletStateFromServer(canonical)"

        print("✅ TEST PASSED: Import handler calls refreshWalletStateFromServer()")

    def test_restore_handler_calls_refresh_state(self):
        """
        CRITICAL TEST: walletV1RestoreFromRecoveryKit() must call refreshWalletStateFromServer()

        Verify: After restore success, refreshWalletStateFromServer() is called
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find restore handler
        restore_start = html.find('async function walletV1RestoreFromRecoveryKit(')
        assert restore_start > 0, "Restore handler must exist"
        restore_section = html[restore_start:restore_start+5000]

        # Should call refreshWalletStateFromServer before switchWalletV1Mode
        has_refresh = re.search(
            r"refreshWalletStateFromServer\s*\(\s*canonical\s*\)",
            restore_section,
            re.IGNORECASE
        )
        assert has_refresh, \
            "Restore success path must call refreshWalletStateFromServer(canonical)"

        # Should call switchWalletV1Mode AFTER refresh
        refresh_then_switch = re.search(
            r"refreshWalletStateFromServer.*switchWalletV1Mode",
            restore_section,
            re.IGNORECASE | re.DOTALL
        )
        assert refresh_then_switch, \
            "switchWalletV1Mode() must be called AFTER refreshWalletStateFromServer()"

        print("✅ TEST PASSED: Restore handler calls refreshWalletStateFromServer()")

    def test_switch_mode_prefers_server_state(self):
        """
        CRITICAL TEST: switchWalletV1Mode() must prefer server truth over client state

        Verify: Function checks window.walletV1LastStatus.modal_state first
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # Find switchWalletV1Mode function
        mode_start = html.find('function switchWalletV1Mode(){')
        assert mode_start > 0, "switchWalletV1Mode must exist"
        mode_section = html[mode_start:mode_start+3000]

        # Should check walletV1LastStatus.modal_state
        prefers_server = re.search(
            r"window\.walletV1LastStatus.*modal_state",
            mode_section,
            re.IGNORECASE
        )
        assert prefers_server, \
            "switchWalletV1Mode() must check window.walletV1LastStatus.modal_state"

        # Should prefer server over client if present
        override_pattern = re.search(
            r"if\s*\(\s*window\.walletV1LastStatus.*modal_state.*\)\s*\{.*modalState\s*=\s*window\.walletV1LastStatus\.modal_state",
            mode_section,
            re.IGNORECASE | re.DOTALL
        )
        assert override_pattern, \
            "switchWalletV1Mode() must override modalState with server value when available"

        print("✅ TEST PASSED: switchWalletV1Mode() prefers server modal_state")

    def test_no_stale_pledge_panel_after_restore(self):
        """
        INTEGRATION TEST: Pledge panel should NOT show after restore due to stale modal_state

        Verify: Restore calls refreshWalletStateFromServer before switchWalletV1Mode
        """
        with open('templates/base.html', 'r') as f:
            html = f.read()

        # The fix: refreshWalletStateFromServer() updates walletV1LastStatus
        # Then switchWalletV1Mode() uses it
        # Result: pledge panel doesn't show because modal_state is no longer 'no_active_wallet'

        # Check that refresh is called in restore section
        restore_start = html.find('async function walletV1RestoreFromRecoveryKit(')
        restore_section = html[restore_start:restore_start + 5000]

        # Both must be present in restore handler
        has_refresh = 'refreshWalletStateFromServer' in restore_section
        has_switch = 'switchWalletV1Mode' in restore_section

        assert has_refresh and has_switch, \
            "Restore must call both refreshWalletStateFromServer and switchWalletV1Mode"

        # Verify order: refresh should come before final switch
        refresh_idx = restore_section.find('refreshWalletStateFromServer')
        switch_idx = restore_section.find('switchWalletV1Mode')

        assert refresh_idx > 0 and switch_idx > refresh_idx, \
            "switchWalletV1Mode() must be called AFTER refreshWalletStateFromServer()"

        print("✅ TEST PASSED: Restore flow prevents stale pledge panel")


if __name__ == '__main__':
    test = TestAuthoritativeStateRefresh()

    print("=" * 80)
    print("AUTHORITATIVE STATE REFRESH TESTS - PR #620.1")
    print("=" * 80)
    print()

    test.test_refresh_wallet_state_function_exists()
    print()
    test.test_import_handler_calls_refresh_state()
    print()
    test.test_restore_handler_calls_refresh_state()
    print()
    test.test_switch_mode_prefers_server_state()
    print()
    test.test_no_stale_pledge_panel_after_restore()

    print()
    print("=" * 80)
    print("✅ ALL AUTHORITATIVE STATE REFRESH TESTS PASSED")
    print("=" * 80)
