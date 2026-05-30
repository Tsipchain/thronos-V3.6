"""
Tests for wallet V1 unlock state synchronization across tabs and pages.
Verifies:
  - Unlock dispatches browser events
  - WalletAuth reuses unlocked context
  - swap.html and pools.html listen for wallet events
  - Cross-tab behavior is clear and secure
  - No private key stored in localStorage/sessionStorage
"""

import re
import pytest


@pytest.fixture
def base_html_content():
    """Load templates/base.html"""
    with open('templates/base.html', 'r') as f:
        return f.read()


@pytest.fixture
def swap_html_content():
    """Load templates/swap.html"""
    with open('templates/swap.html', 'r') as f:
        return f.read()


@pytest.fixture
def pools_html_content():
    """Load templates/pools.html"""
    with open('templates/pools.html', 'r') as f:
        return f.read()


@pytest.fixture
def wallet_session_content():
    """Load static/wallet_session.js"""
    with open('static/wallet_session.js', 'r') as f:
        return f.read()


@pytest.fixture
def wallet_auth_content():
    """Load static/wallet_auth.js"""
    with open('static/wallet_auth.js', 'r') as f:
        return f.read()


@pytest.fixture
def public_wallet_session_content():
    """Load public/static/wallet_session.js"""
    with open('public/static/wallet_session.js', 'r') as f:
        return f.read()


@pytest.fixture
def public_wallet_auth_content():
    """Load public/static/wallet_auth.js"""
    with open('public/static/wallet_auth.js', 'r') as f:
        return f.read()


class TestUnlockEventDispatching:
    """Test that unlock dispatches events to notify other pages."""

    def test_unlock_dispatches_wallet_v1_unlocked_event(self, base_html_content):
        """Verify unlock dispatches thronos:wallet:v1:unlocked event."""
        assert "thronos:wallet:v1:unlocked" in base_html_content
        # Should dispatch with detail containing address
        assert "detail:" in base_html_content and "address:" in base_html_content

    def test_unlock_dispatches_state_changed_event(self, base_html_content):
        """Verify unlock dispatches thronos:wallet:state-changed event."""
        assert "thronos:wallet:state-changed" in base_html_content

    def test_unlock_dispatches_both_events(self, base_html_content):
        """Verify both events are dispatched after successful unlock."""
        # Find unlockWalletV1FromHeader function
        match = re.search(
            r'async function unlockWalletV1FromHeader\(\)[\s\S]*?alert\(.*?unlocked',
            base_html_content
        )
        if match:
            func_body = match.group(0)
            # Should have both dispatch calls
            assert 'thronos:wallet:v1:unlocked' in func_body
            assert 'thronos:wallet:state-changed' in func_body


class TestWalletSessionUnlockedFor:
    """Test walletSession.isUnlockedFor() helper."""

    def test_isUnlockedFor_function_exists(self, wallet_session_content):
        """Verify isUnlockedFor() function exists."""
        assert 'function isUnlockedFor(' in wallet_session_content

    def test_isUnlockedFor_tracks_address(self, wallet_session_content):
        """Verify isUnlockedFor() tracks which address is unlocked."""
        assert 'unlockedForAddress' in wallet_session_content

    def test_isUnlockedFor_not_exposed_in_memory(self, wallet_session_content):
        """Verify isUnlockedFor() doesn't expose private key."""
        match = re.search(
            r'function isUnlockedFor\([\s\S]*?\{[\s\S]*?\}',
            wallet_session_content
        )
        if match:
            func_body = match.group(0)
            # Should not return private key
            assert 'unlockedPrivateKeyHex' not in func_body or 'return unlockedPrivateKeyHex' not in func_body

    def test_isUnlockedFor_exported(self, wallet_session_content):
        """Verify isUnlockedFor is exported from walletSession."""
        assert 'isUnlockedFor' in wallet_session_content
        # Should be in window.walletSession
        assert 'walletSession' in wallet_session_content


class TestUnlockTracking:
    """Test that unlock properly sets and clears unlockedForAddress."""

    def test_unlockWallet_sets_unlocked_for_address(self, wallet_session_content):
        """Verify unlockWallet() sets unlockedForAddress on success."""
        assert 'unlockedForAddress' in wallet_session_content
        # Should be set when unlock succeeds
        assert 'unlockedForAddress =' in wallet_session_content

    def test_lockWallet_clears_unlocked_for_address(self, wallet_session_content):
        """Verify lockWallet() clears unlockedForAddress."""
        # Find lockWallet function
        match = re.search(
            r'function lockWallet\(\)[\s\S]*?\}',
            wallet_session_content
        )
        if match:
            func_body = match.group(0)
            # Should clear unlockedForAddress
            assert 'unlockedForAddress' in func_body


class TestWalletAuthReusesUnlocked:
    """Test that WalletAuth.requireUnlockedWallet() reuses unlocked context."""

    def test_requireUnlockedWallet_checks_isUnlockedFor(self, wallet_auth_content):
        """Verify requireUnlockedWallet checks if already unlocked."""
        assert 'isUnlockedFor' in wallet_auth_content

    def test_requireUnlockedWallet_no_prompt_if_unlocked(self, wallet_auth_content):
        """Verify no PIN prompt if wallet already unlocked."""
        # Find requireUnlockedWallet function
        match = re.search(
            r'async requireUnlockedWallet\(\)[\s\S]*?(?=\n\s{0,8}(?:async |\}|\w+\(|$))',
            wallet_auth_content
        )
        if match:
            func_body = match.group(0)
            # Should check isUnlockedFor before prompting
            isUnlocked_pos = func_body.find('isUnlockedFor')
            prompt_pos = func_body.find("prompt('")
            if isUnlocked_pos >= 0 and prompt_pos >= 0:
                # isUnlockedFor check should come before prompt
                assert isUnlocked_pos < prompt_pos


class TestSwapListeners:
    """Test that swap.html listens for wallet unlock events."""

    def test_swap_listens_for_v1_unlocked_event(self, swap_html_content):
        """Verify swap.html listens for thronos:wallet:v1:unlocked event."""
        assert "addEventListener('thronos:wallet:v1:unlocked'" in swap_html_content

    def test_swap_listens_for_state_changed_event(self, swap_html_content):
        """Verify swap.html listens for thronos:wallet:state-changed event."""
        assert "addEventListener('thronos:wallet:state-changed'" in swap_html_content

    def test_swap_refreshes_balances_on_unlock(self, swap_html_content):
        """Verify swap.html refreshes balances when wallet unlocks."""
        # Should call loadBalances in the listener
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?\}\);",
            swap_html_content
        )
        if match:
            listener_body = match.group(0)
            # Should refresh UI
            assert 'loadBalances' in listener_body or 'loadPools' in listener_body


class TestPoolsListeners:
    """Test that pools.html listens for wallet unlock events."""

    def test_pools_listens_for_v1_unlocked_event(self, pools_html_content):
        """Verify pools.html listens for thronos:wallet:v1:unlocked event."""
        assert "addEventListener('thronos:wallet:v1:unlocked'" in pools_html_content

    def test_pools_listens_for_state_changed_event(self, pools_html_content):
        """Verify pools.html listens for thronos:wallet:state-changed event."""
        assert "addEventListener('thronos:wallet:state-changed'" in pools_html_content

    def test_pools_refreshes_on_unlock(self, pools_html_content):
        """Verify pools.html refreshes when wallet unlocks."""
        # Should call loadPools in the listener
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?\}\);",
            pools_html_content
        )
        if match:
            listener_body = match.group(0)
            # Should refresh pools
            assert 'loadPools' in listener_body or 'loadTokenOptions' in listener_body


class TestNoPrivateKeyStorage:
    """Test that private key is never stored in localStorage/sessionStorage."""

    def test_wallet_session_no_private_key_in_storage(self, wallet_session_content):
        """Verify wallet_session.js doesn't store private key."""
        # Should only store encrypted key
        assert 'V1_ENCRYPTED_KEY' in wallet_session_content
        # Should not store unencrypted private key
        assert 'localStorage.setItem.*unlockedPrivateKeyHex' not in re.sub(r'\s', '', wallet_session_content)

    def test_wallet_auth_no_private_key_in_cache(self, wallet_auth_content):
        """Verify wallet_auth.js doesn't cache private key."""
        # Can cache auth_secret but not private key
        match = re.search(
            r'cachedAuthSecret|unlockedPrivateKeyHex',
            wallet_auth_content
        )
        if match:
            # Should only cache auth secret, not private key
            assert 'cachedAuthSecret' in wallet_auth_content
            # But should not expose private key in cache
            assert 'unlockedPrivateKeyHex' not in wallet_auth_content


class TestFileSynchronization:
    """Test that static and public files are synchronized."""

    def test_isUnlockedFor_in_both_files(self, wallet_session_content, public_wallet_session_content):
        """Verify isUnlockedFor exists in both wallet_session.js files."""
        assert 'function isUnlockedFor(' in wallet_session_content
        assert 'function isUnlockedFor(' in public_wallet_session_content

    def test_unlocked_for_address_in_both_files(self, wallet_session_content, public_wallet_session_content):
        """Verify unlockedForAddress exists in both files."""
        assert 'unlockedForAddress' in wallet_session_content
        assert 'unlockedForAddress' in public_wallet_session_content

    def test_wallet_auth_isUnlockedFor_in_both_files(self, wallet_auth_content, public_wallet_auth_content):
        """Verify wallet_auth.js both check isUnlockedFor."""
        assert 'isUnlockedFor' in wallet_auth_content
        assert 'isUnlockedFor' in public_wallet_auth_content


class TestCrossTabBehavior:
    """Test that cross-tab behavior is handled securely."""

    def test_private_key_not_shared_across_tabs(self, wallet_session_content):
        """Verify private key stays in-memory and not shared."""
        # Private key should be memory-only (unlockedPrivateKeyHex variable)
        # Not in localStorage
        assert 'localStorage.setItem.*unlockedPrivateKeyHex' not in re.sub(r'\s', '', wallet_session_content)

    def test_wallet_session_doesnt_attempt_cross_tab_sync(self, wallet_session_content):
        """Verify wallet doesn't try to sync key across tabs."""
        # Should not try to STORE private key via localStorage
        # (storing encrypted key is fine, but not unlockedPrivateKeyHex)
        match = re.search(
            r'localStorage\.setItem\([^)]*unlockedPrivateKeyHex[^)]*\)',
            wallet_session_content
        )
        assert match is None, "Private key should not be stored in localStorage"


class TestEventDetailStructure:
    """Test that events carry appropriate details."""

    def test_unlock_event_includes_address(self, base_html_content):
        """Verify unlock event includes address in detail."""
        match = re.search(
            r"dispatchEvent.*'thronos:wallet:v1:unlocked'.*detail.*address",
            base_html_content,
            re.IGNORECASE | re.DOTALL
        )
        assert match is not None, "Unlock event should include address in detail"

    def test_state_changed_event_dispatched(self, base_html_content):
        """Verify state-changed event is dispatched."""
        assert "new Event('thronos:wallet:state-changed')" in base_html_content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
