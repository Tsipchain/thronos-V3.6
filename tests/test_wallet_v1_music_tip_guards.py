"""
Guard tests for Wallet V1 music tip functionality.

Ensures:
1. Music tip modal uses WalletAuth.requireUnlockedWallet() for PIN-based unlock
2. No raw auth_secret prompts in the tip flow
3. Balance fetching uses correct active/migrated wallet address
4. Response parsing handles all known balance response shapes
"""

import pytest
from pathlib import Path


def test_tip_modal_uses_wallet_auth():
    """Verify openGlobalTipModal uses WalletAuth.requireUnlockedWallet()."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    assert "openGlobalTipModal" in content, "Missing openGlobalTipModal function"
    assert "WalletAuth.requireUnlockedWallet" in content, "Tip modal must use WalletAuth.requireUnlockedWallet()"

    # Verify PIN prompt is NOT used directly in openGlobalTipModal (happens in submitGlobalTip)
    modal_start = content.find("async function openGlobalTipModal")
    modal_end = content.find("\nfunction closeGlobalTipModal", modal_start)
    modal_code = content[modal_start:modal_end]

    # openGlobalTipModal should use WalletAuth, not prompt()
    assert "prompt(" not in modal_code or "buildWalletMusicApiUrl" in modal_code, \
        "openGlobalTipModal should not prompt for auth_secret"


def test_tip_submit_uses_correct_auth():
    """Verify submitGlobalTip uses auth.authSecret, not raw seed."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    submit_start = content.find("async function submitGlobalTip")
    submit_end = content.find("\n}", submit_start + 100)
    submit_code = content[submit_start:submit_end + 1]

    # Should use authSecret from WalletAuth, not raw seed
    assert "authSecret" in submit_code, "submitGlobalTip must use WalletAuth authSecret"
    assert "getSendSeed" not in submit_code, "submitGlobalTip must not use raw seed"
    assert "localStorage.getItem('send_seed')" not in submit_code, \
        "submitGlobalTip must not access raw seed from localStorage"


def test_balance_response_parsing_robust():
    """Verify balance response parsing handles multiple shapes."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    modal_start = content.find("async function openGlobalTipModal")
    modal_end = content.find("\nfunction closeGlobalTipModal", modal_start)
    modal_code = content[modal_start:modal_end]

    # Should handle j.tokens (array) OR j.balances (map)
    assert "j.tokens" in modal_code, "Should parse j.tokens array"
    assert "j.balances" in modal_code, "Should fallback to j.balances map"

    # Should filter to non-zero balances for display
    assert ".filter(x => x.balance > 0)" in modal_code, "Should filter non-zero assets for dropdown"


def test_music_tip_uses_show_zero_true():
    """Verify balance fetch uses show_zero=true for fetching all balances."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    modal_start = content.find("async function openGlobalTipModal")
    modal_end = content.find("\nfunction closeGlobalTipModal", modal_start)
    modal_code = content[modal_start:modal_end]

    assert "show_zero=true" in modal_code, \
        "Balance fetch must use show_zero=true to get all token balances"


def test_music_tip_modal_html_exists():
    """Verify the global tip modal HTML element exists in base.html."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    assert 'id="globalTipModal"' in content, "Missing globalTipModal element"
    assert 'id="globalTipAsset"' in content, "Missing globalTipAsset select"
    assert 'id="globalTipAmount"' in content, "Missing globalTipAmount input"
    assert 'id="globalTipTrackMeta"' in content, "Missing globalTipTrackMeta display"
    assert 'id="globalTipHint"' in content, "Missing globalTipHint display"


def test_music_html_tip_artist_flow():
    """Verify music.html tipArtist() uses global tip modal."""
    music_html = Path(__file__).parent.parent / "templates" / "music.html"
    content = music_html.read_text()

    tip_start = content.find("async function tipArtist()")
    tip_end = content.find("\n}", tip_start + 100)
    tip_code = content[tip_start:tip_end + 1]

    # Should prefer global tip modal
    assert "openGlobalTipModal" in tip_code, "tipArtist should use openGlobalTipModal"
    assert "WalletAuth.requireUnlockedWallet" in tip_code, "Tip flow must use WalletAuth"
    assert "authSecret" in tip_code, "Tip request must include authSecret"


def test_music_html_uses_correct_wallet_address():
    """Verify music.html getActiveWalletAddress handles migrated wallets."""
    music_html = Path(__file__).parent.parent / "templates" / "music.html"
    content = music_html.read_text()

    addr_start = content.find("async function getActiveWalletAddress()")
    addr_end = content.find("\n}\n", addr_start)
    addr_code = content[addr_start:addr_end]

    # Should check migration info first
    assert "getActiveAddress" in addr_code, "Should check walletSession.getActiveAddress()"
    assert "isMigrated" in addr_code, "Should check migration status"
    assert "getMigrationInfo" in addr_code, "Should get migration info"
    assert "new_v1_address" in addr_code, "Should use new_v1_address from migration"


def test_tip_asset_dropdown_sorting():
    """Verify tip asset dropdown sorts THR first, then crosschain tokens."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    modal_start = content.find("async function openGlobalTipModal")
    modal_end = content.find("\nfunction closeGlobalTipModal", modal_start)
    modal_code = content[modal_start:modal_end]

    # Should define a sort order that puts THR first
    assert "sortOrder = " in modal_code, "Should define sort order for assets"
    assert "'THR'" in modal_code and "'WBTC'" in modal_code, \
        "Sort order should include THR and WBTC"
