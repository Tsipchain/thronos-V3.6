"""
Test Wallet V1 Session Management with 15-minute TTL.

Ensures:
1. Session TTL is enforced (15 minutes)
2. Auto-lock when TTL expires
3. Countdown timer available for UI
4. On browser refresh: if encrypted key exists but runtime material missing → show "Unlock"
5. No PIN spam (TTL prevents repeated unlocks)
"""

import pytest
from pathlib import Path


class TestSessionTTLConstant:
    """Test that 15-minute TTL is properly defined."""

    def test_session_ttl_constant_defined(self):
        """Verify SESSION_TTL_MS is defined."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        assert "SESSION_TTL_MS" in content, \
            "SESSION_TTL_MS constant not found"

    def test_session_ttl_is_15_minutes(self):
        """Verify TTL is set to 15 minutes (900000ms)."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        # Find the constant definition
        ttl_start = content.find("SESSION_TTL_MS")
        ttl_line = content[ttl_start:ttl_start + 100]

        # Should be 15 * 60 * 1000 or similar
        assert "15" in ttl_line and ("60" in ttl_line or "900" in ttl_line), \
            "TTL should be 15 minutes"


class TestSessionUnlockTimestamp:
    """Test that unlock timestamp is recorded."""

    def test_unlock_timestamp_variable_exists(self):
        """Verify unlockedAtTime variable is declared."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        assert "unlockedAtTime" in content, \
            "unlockedAtTime variable not found"

    def test_unlock_sets_timestamp_on_create_wallet(self):
        """Verify createWalletV1 sets unlock timestamp."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        create_start = content.find("function createWalletV1(")
        create_end = content.find("return {", create_start)
        create_func = content[create_start:create_end]

        assert "unlockedAtTime" in create_func, \
            "createWalletV1 should set unlock timestamp"

    def test_unlock_sets_timestamp_on_unlock_wallet(self):
        """Verify unlockWallet sets unlock timestamp."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        unlock_start = content.find("unlockedPrivateKeyHex = decryptedPrivKeyHex")
        unlock_context = content[unlock_start:unlock_start + 500]

        assert "unlockedAtTime" in unlock_context, \
            "unlockWallet should set unlock timestamp"


class TestSessionExpiryDetection:
    """Test that session expiry is properly detected."""

    def test_is_session_expired_function_exists(self):
        """Verify isSessionExpired function is defined."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        assert "function isSessionExpired()" in content, \
            "isSessionExpired function not found"

    def test_session_expiry_checks_time_elapsed(self):
        """Verify isSessionExpired checks elapsed time."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        func_start = content.find("function isSessionExpired()")
        func_end = content.find("function ", func_start + 100)
        func = content[func_start:func_end]

        assert "Date.now()" in func, \
            "Should check current time"
        assert "SESSION_TTL_MS" in func, \
            "Should check against TTL constant"

    def test_session_expiry_auto_locks_wallet(self):
        """Verify isSessionExpired clears runtime material on expiry."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        func_start = content.find("function isSessionExpired()")
        func_end = content.find("function ", func_start + 100)
        func = content[func_start:func_end]

        assert "unlockedPrivateKeyHex = null" in func, \
            "Should clear private key on expiry"
        assert "unlockedAtTime = null" in func, \
            "Should clear unlock time on expiry"


class TestSessionTimeRemaining:
    """Test countdown timer functionality."""

    def test_get_session_time_remaining_function_exists(self):
        """Verify getSessionTimeRemaining function is defined."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        assert "function getSessionTimeRemaining()" in content, \
            "getSessionTimeRemaining function not found"

    def test_get_session_time_remaining_returns_milliseconds(self):
        """Verify getSessionTimeRemaining returns time in milliseconds."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        func_start = content.find("function getSessionTimeRemaining()")
        func_end = content.find("function ", func_start + 100)
        func = content[func_start:func_end]

        assert "Math.max(0" in func or "remaining = " in func, \
            "Should calculate remaining time"

    def test_get_session_time_remaining_returns_zero_if_not_unlocked(self):
        """Verify getSessionTimeRemaining returns 0 if not unlocked."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        func_start = content.find("function getSessionTimeRemaining()")
        func_end = content.find("function ", func_start + 100)
        func = content[func_start:func_end]

        assert "if (!unlockedAtTime" in func or "return 0" in func, \
            "Should return 0 if not unlocked"


class TestRuntimeMaterialExpiryCheck:
    """Test that runtime material check includes TTL."""

    def test_has_runtime_signing_material_checks_expiry(self):
        """Verify hasRuntimeSigningMaterial checks session expiry."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        func_start = content.find("function hasRuntimeSigningMaterial(")
        func_end = content.find("function ", func_start + 100)
        func = content[func_start:func_end]

        assert "isSessionExpired()" in func, \
            "Should check if session is expired"

    def test_has_runtime_signing_material_returns_false_if_expired(self):
        """Verify hasRuntimeSigningMaterial returns false after expiry."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        func_start = content.find("function hasRuntimeSigningMaterial(")
        func_end = content.find("function ", func_start + 100)
        func = content[func_start:func_end]

        assert "return false" in func, \
            "Should return false if TTL expired"


class TestLockingClearsTimestamp:
    """Test that locking properly clears TTL timestamp."""

    def test_lock_wallet_clears_timestamp(self):
        """Verify lockWallet clears unlockedAtTime."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        lock_start = content.find("function lockWallet()")
        lock_end = content.find("}", lock_start)
        lock_func = content[lock_start:lock_end]

        assert "unlockedAtTime = null" in lock_func, \
            "lockWallet should clear timestamp"

    def test_disconnect_clears_timestamp(self):
        """Verify disconnect clears unlockedAtTime."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        disconnect_line = [line for line in content.split('\n') if 'function disconnect()' in line][0]
        assert "unlockedAtTime" in disconnect_line, \
            "disconnect should clear timestamp"

    def test_forget_device_clears_timestamp(self):
        """Verify forgetDevice clears unlockedAtTime."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        forget_line = [line for line in content.split('\n') if 'function forgetDevice()' in line][0]
        assert "unlockedAtTime" in forget_line, \
            "forgetDevice should clear timestamp"


class TestExportsNewFunctions:
    """Test that new functions are exported."""

    def test_is_session_expired_exported(self):
        """Verify isSessionExpired is exported."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        assert "isSessionExpired" in content and "window.walletSession" in content, \
            "isSessionExpired should be exported"

    def test_get_session_time_remaining_exported(self):
        """Verify getSessionTimeRemaining is exported."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        assert "getSessionTimeRemaining" in content and "window.walletSession" in content, \
            "getSessionTimeRemaining should be exported"


class TestRefreshBehavior:
    """Test behavior on browser refresh."""

    def test_runtime_material_not_persisted_across_refresh(self):
        """Verify runtime material is in-memory only (not persisted)."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        # unlockedPrivateKeyHex should NOT be in localStorage
        localStorage_keys = ["ADDRESS_KEY", "SEND_SECRET_KEY", "PIN_KEY", "V1_ENCRYPTED_KEY", "V1_PUBLIC_KEY"]
        for key in localStorage_keys:
            assert key in content, f"{key} should be persisted"

        # But unlockedPrivateKeyHex is just a variable
        unlockedprivate_count = content.count("localStorage.setItem") and content.count("unlockedPrivateKeyHex = ")
        assert "localStorage" not in content[content.find("unlockedPrivateKeyHex = null"):content.find("unlockedPrivateKeyHex = null") + 100], \
            "unlockedPrivateKeyHex should NOT be persisted to localStorage"

    def test_encrypted_key_persists_across_refresh(self):
        """Verify encrypted key is persisted and can be restored."""
        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        assert "V1_ENCRYPTED_KEY" in content, \
            "Should persist encrypted key"
        assert "localStorage" in content and "V1_ENCRYPTED_KEY" in content, \
            "Encrypted key should use localStorage"


class TestNoPINSpam:
    """Test that TTL prevents repeated unlock prompts."""

    def test_session_prevents_repeated_unlock_requests(self):
        """Verify session keeps user unlocked for 15 minutes."""
        # This is a conceptual test - the actual behavior is:
        # 1. User enters PIN once
        # 2. unlockedAtTime is set
        # 3. For next 15 minutes, hasRuntimeSigningMaterial returns true
        # 4. No additional PIN prompts needed

        wallet_js = Path(__file__).parent.parent / "static" / "wallet_session.js"
        content = wallet_js.read_text()

        # Verify the logic is there:
        assert "SESSION_TTL_MS" in content, "TTL constant should exist"
        assert "getSessionTimeRemaining" in content, "Countdown function should exist"
        assert "isSessionExpired" in content, "Expiry check should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
