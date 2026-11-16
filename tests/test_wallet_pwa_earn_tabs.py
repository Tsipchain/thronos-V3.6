"""Wallet PWA Earn tabs regression: navigation only, no transfer logic changes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "public/wallet-pwa/app.js").read_text()
CSS = (ROOT / "public/wallet-pwa/app.css").read_text()
SW = (ROOT / "public/wallet-pwa/sw.js").read_text()


def test_earn_pwa_has_five_grouped_panels_and_accessible_controls():
    for section in ("offers", "activity", "community", "staking", "account"):
        assert f'id="ew-tab-{section}"' in JS
        assert f'id="ew-panel-{section}"' in JS
        assert f'data-ew-tab="{section}"' in JS
    assert 'id="earnWalletTabs"' in JS
    assert "role=\"tablist\"" in JS
    assert "selectEarnWalletTab(options.focusLeaderboard ? 'community' : 'offers')" in JS
    assert "['ArrowRight', 'ArrowLeft', 'Home', 'End']" in JS


def test_existing_earn_features_remain_accessible():
    for marker in ("earnProviderGrid", "earnAvailableCard", "earnPendingCard",
                   "earnPwaMessage", "earnReferralsBtn", "earnPwaLeaderboard",
                   "earnStakingSection", "earnStakingPools", "openEarnCenterBtn",
                   "linkEarnWalletBtn", "earnChristmasTimewall", "data-earn-receipt"):
        assert marker in JS
    assert "window.ThronosEarnTabs.open(" in JS
    assert "window.ThronosEarnLeaderboard.mount(" in JS
    assert "window.ThronosEarnReceipts.open(" in JS


def test_tabs_are_scoped_to_earn_and_service_worker_updates():
    assert "#earnPwaBody .earn-wallet-tabs" in CSS
    assert "#earnPwaBody .earn-wallet-panel[hidden]" in CSS
    assert "thr-wallet-pwa-v27" in SW
    assert "if (url.pathname.startsWith('/pwa-api/') || url.pathname.startsWith('/api/')) return;" in SW
    assert "async function showWallet(" in JS
    assert "async function showEarn(" in JS


def test_challenge_switches_to_offer_tab_before_scrolling():
    needle = "document.getElementById('earnChristmasTimewall').addEventListener('click', () => {"
    a = JS.index(needle)
    section = JS[a:a + 550]
    assert "document.getElementById('ew-tab-offers')?.click();" in section
    assert "timewall.scrollIntoView(" in section


def test_wallet_pwa_daily_checkin_parity():
    for marker in (
        'id="earnPwaCheckin"',
        'id="earnPwaCheckinBtn"',
        'id="earnPwaCheckinStatus"',
        '/api/earn/dormancy/status',
        '/api/earn/checkin',
        "credentials: 'include'",
        'data-state="loading"',
    ):
        assert marker in JS


def test_wallet_pwa_daily_checkin_uses_server_authority():
    assert "earnCheckinButton?.addEventListener('click'" in JS
    assert "method: 'POST'" in JS
    assert "data.idempotent ? 'already' : 'success'" in JS
    assert "reactivation_streak" in JS
