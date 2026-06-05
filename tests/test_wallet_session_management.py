"""
Wallet Session Management Tests

Verifies PIN unlock session behavior:
1. PIN unlock marks session as active (localStorage tracking)
2. Session remains active for 15 minutes
3. Session timer display shows remaining time
4. Timer updates every minute
5. Helper functions track unlock time
6. Recovery Kit restore also marks session
7. Functions return remaining minutes correctly
8. Session can be cleared manually
"""

import pytest
from pathlib import Path


class TestSessionManagementFunctions:
    """Test wallet session management functions."""

    def test_wallet_session_config_defined(self):
        """Verify WALLET_SESSION_CONFIG is defined."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "WALLET_SESSION_CONFIG" in content, \
            "Session config not defined"
        assert "UNLOCK_DURATION_MINUTES" in content, \
            "UNLOCK_DURATION_MINUTES config missing"
        assert "INACTIVITY_TIMEOUT_MINUTES" in content, \
            "INACTIVITY_TIMEOUT_MINUTES config missing"

    def test_walletSessionSetUnlocked_exists(self):
        """Verify walletSessionSetUnlocked function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletSessionSetUnlocked" in content, \
            "walletSessionSetUnlocked function not found"

    def test_walletSessionGetRemainingMinutes_exists(self):
        """Verify walletSessionGetRemainingMinutes function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletSessionGetRemainingMinutes" in content, \
            "walletSessionGetRemainingMinutes function not found"

    def test_walletSessionIsUnlocked_exists(self):
        """Verify walletSessionIsUnlocked function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletSessionIsUnlocked" in content, \
            "walletSessionIsUnlocked function not found"

    def test_walletSessionClear_exists(self):
        """Verify walletSessionClear function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletSessionClear" in content, \
            "walletSessionClear function not found"

    def test_walletSessionUpdateTimerDisplay_exists(self):
        """Verify walletSessionUpdateTimerDisplay function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletSessionUpdateTimerDisplay" in content, \
            "walletSessionUpdateTimerDisplay function not found"


class TestSessionStorageUsage:
    """Test that session functions use localStorage correctly."""

    def test_setUnlocked_uses_localStorage(self):
        """Verify setUnlocked stores unlock time in localStorage."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionSetUnlocked")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "localStorage.setItem" in func, \
            "Should save unlock time to localStorage"
        assert "wallet_session_unlock_time" in func, \
            "Should track unlock_time key"

    def test_getRemainingMinutes_reads_localStorage(self):
        """Verify getRemainingMinutes reads from localStorage."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionGetRemainingMinutes")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "localStorage.getItem" in func, \
            "Should read from localStorage"
        assert "wallet_session_unlock_time" in func, \
            "Should read unlock_time key"

    def test_setUnlocked_also_tracks_activity(self):
        """Verify setUnlocked tracks last activity time."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionSetUnlocked")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "wallet_session_last_activity" in func, \
            "Should also track last_activity"

    def test_clear_removes_session_storage(self):
        """Verify clear removes session data."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionClear()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "localStorage.removeItem" in func, \
            "Should remove from localStorage"
        assert "wallet_session_unlock_time" in func, \
            "Should remove unlock_time on clear"


class TestSessionTimerUI:
    """Test session timer display."""

    def test_session_timer_display_exists(self):
        """Verify session timer display HTML exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'id="walletSessionTimerDisplay"' in content, \
            "Session timer display element not found"

    def test_session_timer_display_hidden_by_default(self):
        """Verify session timer starts hidden."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find timer element
        start = content.find('id="walletSessionTimerDisplay"')
        end = content.find('</div>', start) + 6
        timer_el = content[start:end]

        assert 'style="display:none;' in timer_el or 'display:none' in timer_el, \
            "Session timer should be hidden by default"

    def test_updateTimerDisplay_function_updates_UI(self):
        """Verify updateTimerDisplay updates the timer element."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionUpdateTimerDisplay()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "walletSessionTimerDisplay" in func, \
            "Should update timer display element"
        assert "display" in func or "innerHTML" in func, \
            "Should modify element visibility or content"

    def test_timer_auto_update_interval_set(self):
        """Verify timer updates every minute."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Check for setInterval call
        assert "setInterval(walletSessionUpdateTimerDisplay" in content, \
            "Should auto-update timer display on interval"
        assert "60000" in content or "60 * 1000" in content, \
            "Should update every minute (60000ms)"


class TestUnlockSessionIntegration:
    """Test that unlock functions trigger session tracking."""

    def test_unlockWalletV1FromHeader_calls_walletSessionSetUnlocked(self):
        """Verify unlock function sets session."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find unlock function
        start = content.find("async function unlockWalletV1FromHeader()")
        end = content.find("\n}", start)
        func = content[start:end]

        assert "walletSessionSetUnlocked" in func, \
            "Unlock should set session"

    def test_recovery_kit_restore_calls_walletSessionSetUnlocked(self):
        """Verify Recovery Kit restore sets session."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find Recovery Kit handler
        start = content.find("function walletV1HandleRecoveryKitRestore()")
        end = content.find("\n}", start)
        handler = content[start:end]

        assert "walletSessionSetUnlocked" in handler, \
            "Recovery Kit restore should set session"


class TestSessionExpiry:
    """Test session expiry behavior."""

    def test_getRemainingMinutes_returns_zero_on_expiry(self):
        """Verify getRemainingMinutes returns 0 when session expired."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionGetRemainingMinutes")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "remainingMs <= 0" in func or "remaining" in func.lower(), \
            "Should check for expiry"
        assert "return 0" in func, \
            "Should return 0 on expiry"

    def test_isUnlocked_checks_remaining_minutes(self):
        """Verify isUnlocked checks remaining time."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionIsUnlocked()")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "walletSessionGetRemainingMinutes" in func, \
            "Should use remaining minutes check"


class TestSessionTimeFormatting:
    """Test time formatting."""

    def test_formatTime_function_exists(self):
        """Verify time formatting function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function walletSessionFormatTime" in content, \
            "Time formatting function not found"

    def test_formatTime_handles_minutes_and_hours(self):
        """Verify time formatter handles both minutes and hours."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Find function
        start = content.find("function walletSessionFormatTime")
        end = content.find("\n}", start) + 2
        func = content[start:end]

        assert "hours" in func.lower() or "Math.floor" in func, \
            "Should handle hours"
        assert "minutes" in func.lower() or "%" in func, \
            "Should handle minutes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
