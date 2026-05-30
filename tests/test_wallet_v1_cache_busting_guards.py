"""
Tests for wallet cache-busting and diagnostics.
Verifies:
  - Version markers are present in wallet modules
  - Cache-busting query params are in script URLs
  - Diagnostics logging is present in swap/pools
  - No private key stored
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


class TestVersionMarkers:
    """Test that version markers are present in wallet modules."""

    def test_wallet_session_has_version(self, wallet_session_content):
        """Verify wallet_session.js exports version."""
        assert 'const VERSION =' in wallet_session_content
        assert 'version: VERSION' in wallet_session_content
        assert 'wallet-v1-state-sync-2026-05-30' in wallet_session_content

    def test_wallet_auth_has_version(self, wallet_auth_content):
        """Verify wallet_auth.js exports version."""
        assert 'const VERSION =' in wallet_auth_content
        assert 'version: VERSION' in wallet_auth_content
        assert 'wallet-v1-state-sync-2026-05-30' in wallet_auth_content

    def test_public_wallet_session_has_version(self, public_wallet_session_content):
        """Verify public/static/wallet_session.js has version."""
        assert 'const VERSION =' in public_wallet_session_content
        assert 'version: VERSION' in public_wallet_session_content

    def test_public_wallet_auth_has_version(self, public_wallet_auth_content):
        """Verify public/static/wallet_auth.js has version."""
        assert 'const VERSION =' in public_wallet_auth_content
        assert 'version: VERSION' in public_wallet_auth_content


class TestCacheBusting:
    """Test that script URLs have cache-busting query params."""

    def test_wallet_session_script_has_cache_bust(self, base_html_content):
        """Verify wallet_session.js script has ?v= query param."""
        assert 'wallet_session.js' in base_html_content
        # Should have cache busting with build_id
        match = re.search(
            r"wallet_session\.js.*\?v=.*build_id",
            base_html_content
        )
        assert match is not None, "wallet_session.js should have ?v={{ build_id }} cache buster"

    def test_wallet_auth_script_has_cache_bust(self, base_html_content):
        """Verify wallet_auth.js script has ?v= query param."""
        assert 'wallet_auth.js' in base_html_content
        # Should have cache busting with build_id
        match = re.search(
            r"wallet_auth\.js.*\?v=.*build_id",
            base_html_content
        )
        assert match is not None, "wallet_auth.js should have ?v={{ build_id }} cache buster"


class TestVersionLogging:
    """Test that base.html logs version info."""

    def test_base_html_logs_wallet_session_version(self, base_html_content):
        """Verify base.html logs wallet_session version."""
        assert '[WalletV1] wallet_session version' in base_html_content

    def test_base_html_logs_wallet_auth_version(self, base_html_content):
        """Verify base.html logs wallet_auth version."""
        assert '[WalletV1] wallet_auth version' in base_html_content

    def test_base_html_checks_version_existence(self, base_html_content):
        """Verify base.html checks if version properties exist."""
        # Should check if walletSession.version exists
        assert 'walletSession.version' in base_html_content
        assert 'WalletAuth.version' in base_html_content


class TestSwapDiagnostics:
    """Test that swap.html has unlock event diagnostics."""

    def test_swap_logs_unlock_event(self, swap_html_content):
        """Verify swap logs when unlock event is received."""
        assert "[SwapUI] Wallet V1 unlocked event received" in swap_html_content

    def test_swap_logs_active_address(self, swap_html_content):
        """Verify swap logs active address in unlock event."""
        # Should log activeAddr in event handler
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?activeAddr",
            swap_html_content
        )
        assert match is not None, "Swap should log activeAddr on unlock event"

    def test_swap_logs_isUnlockedFor(self, swap_html_content):
        """Verify swap logs isUnlockedFor status."""
        assert 'isUnlockedFor' in swap_html_content
        # Should check isUnlockedFor in event handler
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?isUnlockedFor",
            swap_html_content
        )
        assert match is not None, "Swap should check isUnlockedFor in event handler"

    def test_swap_logs_state_changed_event(self, swap_html_content):
        """Verify swap logs state-changed events."""
        assert "[SwapUI] Wallet state changed event" in swap_html_content

    def test_swap_refreshes_on_unlock(self, swap_html_content):
        """Verify swap refreshes balances/tokens on unlock."""
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?(?:loadBalances|loadSwapCatalog)",
            swap_html_content
        )
        assert match is not None, "Swap should refresh on unlock event"


class TestPoolsDiagnostics:
    """Test that pools.html has unlock event diagnostics."""

    def test_pools_logs_unlock_event(self, pools_html_content):
        """Verify pools logs when unlock event is received."""
        assert "[PoolsUI] Wallet V1 unlocked event received" in pools_html_content

    def test_pools_logs_active_address(self, pools_html_content):
        """Verify pools logs active address in unlock event."""
        # Should log activeAddr in event handler
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?activeAddr",
            pools_html_content
        )
        assert match is not None, "Pools should log activeAddr on unlock event"

    def test_pools_logs_isUnlockedFor(self, pools_html_content):
        """Verify pools logs isUnlockedFor status."""
        assert 'isUnlockedFor' in pools_html_content
        # Should check isUnlockedFor in event handler
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?isUnlockedFor",
            pools_html_content
        )
        assert match is not None, "Pools should check isUnlockedFor in event handler"

    def test_pools_logs_state_changed_event(self, pools_html_content):
        """Verify pools logs state-changed events."""
        assert "[PoolsUI] Wallet state changed event" in pools_html_content

    def test_pools_refreshes_on_unlock(self, pools_html_content):
        """Verify pools refreshes on unlock."""
        match = re.search(
            r"addEventListener\('thronos:wallet:v1:unlocked'[\s\S]*?(?:loadTokenOptions|loadPools)",
            pools_html_content
        )
        assert match is not None, "Pools should refresh on unlock event"


class TestNoPrivateKeyStorage:
    """Test that private key is never stored."""

    def test_no_private_key_in_wallet_session_storage(self, wallet_session_content):
        """Verify wallet_session doesn't store private key."""
        # Check that unlockedPrivateKeyHex is not STORED in localStorage (only checked/used in memory)
        match = re.search(
            r'localStorage\.setItem\([^)]*unlockedPrivateKeyHex[^)]*\)',
            wallet_session_content
        )
        assert match is None, "Private key should not be stored in localStorage"

    def test_no_private_key_in_wallet_auth_storage(self, wallet_auth_content):
        """Verify wallet_auth doesn't store private key."""
        match = re.search(
            r'localStorage\.setItem.*unlockedPrivateKeyHex',
            wallet_auth_content
        )
        assert match is None, "Private key should not be stored in localStorage"

    def test_no_session_storage_for_private_key(self, wallet_session_content):
        """Verify private key not in sessionStorage."""
        match = re.search(
            r'sessionStorage\.setItem.*unlockedPrivateKeyHex',
            wallet_session_content
        )
        assert match is None, "Private key should not be stored in sessionStorage"


class TestFileSync:
    """Test that static and public files are synchronized."""

    def test_version_in_both_wallet_session(self, wallet_session_content, public_wallet_session_content):
        """Verify version in both wallet_session.js files."""
        assert 'wallet-v1-state-sync-2026-05-30' in wallet_session_content
        assert 'wallet-v1-state-sync-2026-05-30' in public_wallet_session_content

    def test_version_in_both_wallet_auth(self, wallet_auth_content, public_wallet_auth_content):
        """Verify version in both wallet_auth.js files."""
        assert 'wallet-v1-state-sync-2026-05-30' in wallet_auth_content
        assert 'wallet-v1-state-sync-2026-05-30' in public_wallet_auth_content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
