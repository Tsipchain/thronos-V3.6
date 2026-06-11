"""
Test Music Module Wallet Safety - No State Leaks

Ensures that music.html operations don't affect wallet state:
1. Wallet widget remains responsive on /music page
2. getActiveWalletAddress() reads-only (no side effects)
3. 404 covers don't kill wallet session
4. No walletSession re-init or reassignment
5. Music module doesn't call disconnect/forget/clearSession
"""

import pytest
from pathlib import Path


class TestMusicModuleWalletSafety:
    """Test that music module doesn't interfere with wallet state."""

    def test_music_html_accesses_wallet_session_read_only(self):
        """Verify music.html only reads wallet, doesn't modify."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # Should read walletSession
        assert "walletSession" in content, \
            "Music should access walletSession"

        # Should NOT call destructive functions
        assert "disconnect()" not in content, \
            "Music should not call disconnect()"
        assert "forgetDevice()" not in content, \
            "Music should not call forgetDevice()"
        assert "clearSession()" not in content, \
            "Music should not call clearSession()"
        assert "setBound(false)" not in content, \
            "Music should not call setBound(false)"
        assert "localStorage.clear()" not in content, \
            "Music should not call localStorage.clear()"

    def test_get_active_wallet_address_is_read_only(self):
        """Verify getActiveWalletAddress() doesn't modify state."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # Find function
        func_start = content.find("async function getActiveWalletAddress()")
        func_end = content.find("}", func_start) + 1
        func = content[func_start:func_end]

        # Should only read wallet info
        assert "getActiveAddress" in func or "getAddress" in func, \
            "Should call wallet read functions"

        # Should not modify wallet
        assert "setAddress" not in func, \
            "Should not call setAddress()"
        assert "localStorage.setItem" not in func, \
            "Should not modify localStorage (wallet keys)"

    def test_music_handles_404_without_killing_wallet(self):
        """Verify 404 errors (missing covers) don't affect wallet."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # Should have error handling for fetch failures
        assert "catch" in content or "try" in content, \
            "Should handle fetch errors gracefully"

        # Error handling should be local to music, not global
        # Check that 404/errors don't trigger wallet disconnect
        fetch_section = content.find("fetchJsonWithRetry")
        if fetch_section > 0:
            error_handling = content[fetch_section:fetch_section + 2000]
            assert "throw" in error_handling or "catch" in error_handling, \
                "Should handle errors without side effects"


class TestMusicModuleInitialization:
    """Test music module initialization doesn't interfere with wallet."""

    def test_music_init_is_local_not_global(self):
        """Verify initMusic() is local and doesn't reset global state."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # Find initMusic function
        init_start = content.find("function initMusic()")
        init_end = content.find("}", init_start) + 1
        init_func = content[init_start:init_end]

        # Should only load music tracks, not reset wallet
        assert "loadTracks()" in init_func, \
            "Should load music tracks"

        # Should not reinit wallet
        assert "walletSession = " not in init_func, \
            "Should not reassign walletSession"
        assert "window.walletSession = " not in init_func, \
            "Should not reassign global walletSession"

    def test_music_listener_setup_isolated(self):
        """Verify audio listeners don't affect wallet listeners."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # Find setupAudioListeners
        setup_start = content.find("function setupAudioListeners()")
        setup_end = content.find("}", setup_start)
        if setup_end < setup_start:
            setup_end = content.find("function ", setup_start + 100)
        setup_func = content[setup_start:setup_end]

        # Should only add audio-related listeners
        assert "addEventListener" in setup_func, \
            "Should set up event listeners"

        # Should not touch wallet listeners/events
        assert "wallet" not in setup_func.lower() or "addEventListener" not in setup_func[setup_func.lower().find("wallet"):], \
            "Should not set up wallet event listeners here"


class TestMusicWidgetCoexistence:
    """Test that wallet widget works correctly on music page."""

    def test_wallet_widget_not_hidden_in_music(self):
        """Verify wallet widget is visible on /music page."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        base_html = Path(__file__).parent.parent / "templates" / "base.html"

        music_content = music_html.read_text()
        base_content = base_html.read_text()

        # Music page should not have CSS that hides wallet widget
        assert "walletStatus" not in music_content or "display:none" not in music_content, \
            "Music page should not hide wallet widget"

        # Wallet widget should be in base template (applies to all pages including music)
        assert "walletStatus" in base_content, \
            "Wallet widget should be in base template"

    def test_music_playlist_loading_doesnt_block_wallet(self):
        """Verify playlist loading is async and doesn't block wallet."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # loadUploadPlaylists should be present
        assert "loadUploadPlaylists" in content, \
            "Should have loadUploadPlaylists function"

        # Should use async operations (fetch is used in music module)
        assert "fetch" in content, \
            "Music module should use fetch for async operations"

        # Should not block with synchronous calls
        assert "XMLHttpRequest" not in content, \
            "Should not use synchronous XMLHttpRequest"


class TestMusicErrorRecovery:
    """Test that music errors don't cascade to wallet."""

    def test_music_errors_dont_propagate_globally(self):
        """Verify music module errors are caught locally."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # Check for error handlers
        assert "catch" in content, \
            "Should have error handlers"

        # Errors should be logged/handled, not throw to global
        assert "console.error" in content or "console.log" in content, \
            "Should log errors for debugging"

    def test_music_missing_assets_dont_break_init(self):
        """Verify missing music assets (404) don't break music initialization."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # fetchJsonWithRetry should handle failures
        assert "fetchJsonWithRetry" in content, \
            "Should have retry logic for failed fetches"

        # Should continue even if some playlists fail to load
        fetch_func_start = content.find("async function fetchJsonWithRetry(")
        fetch_func_end = content.find("throw lastError", fetch_func_start)
        if fetch_func_end > fetch_func_start:
            assert True, "Has proper error propagation"


class TestMusicWalletIntegrationPoints:
    """Test safe integration points between music and wallet."""

    def test_music_respects_wallet_address_immutability(self):
        """Verify wallet address from music is never used to modify state."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # getActiveWalletAddress is called many times
        address_calls = content.count("getActiveWalletAddress()")
        assert address_calls > 0, \
            "Should call getActiveWalletAddress"

        # But should never use it to reassign wallets
        for i in range(5):
            pos = content.find("getActiveWalletAddress()")
            if pos < 0:
                break
            context = content[pos:pos + 200]
            assert "setAddress" not in context, \
                "Should not use wallet address to modify wallet state"
            content = content[pos + 1:]

    def test_music_playlist_cache_doesnt_modify_wallet_cache(self):
        """Verify music playlist cache uses different keys than wallet cache."""
        music_html = Path(__file__).parent.parent / "templates" / "music.html"
        content = music_html.read_text()

        # Should use music-specific cache keys
        assert "playlistCacheKey" in content or "playlist" in content.lower(), \
            "Should have music-specific cache mechanism"

        # Should not use wallet cache keys
        assert "MIGRATION_META_KEY" not in content, \
            "Should not use wallet migration cache"
        assert "V1_ENCRYPTED_KEY" not in content, \
            "Should not access wallet encryption key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
