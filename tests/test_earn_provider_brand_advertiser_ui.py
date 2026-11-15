"""Earn frontend presentation and advertiser CTA regression guards.

Ad-approval/escrow/payout code and all provider journeys must remain unchanged.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "templates/earn_beta.html").read_text()


def test_provider_names_and_official_domain_icons_with_text_fallback():
    expected = {
        "cpx": ("CPX Research", "www.cpx-research.com"),
        "timewall": ("TimeWall", "timewall.io"),
        "bitcotasks": ("BitcoTasks", "bitcotasks.com"),
        "pure": ("PureSpectrum", "www.purespectrum.com"),
    }
    for provider, (name, origin) in expected.items():
        assert 'earn-provider-brand--' + provider in PAGE
        assert name in PAGE
        assert origin + '/favicon.ico' in PAGE
    assert 'onerror="this.hidden=true"' in PAGE
    assert 'loading="lazy"' in PAGE


def test_existing_provider_open_ids_and_ad_impression_flow_retained():
    for provider in ("earn-surveys", "earn-timewall", "earn-bitcotasks", "earn-pure"):
        assert PAGE.count(f'id="{provider}"') == 1
    for marker in (
        'id="earn-ad-banner"', "window.ThronosEarnTabs.open(provider",
        "/api/earn/ads/impression", "/api/earn/ads/click",
        'id="promo-overlay"', 'id="earn-frame"', "showPromo(15)",
        'id="earn-referral"', 'id="earn-leaderboard"'
    ):
        assert marker in PAGE
    # Gym reward and real ad funding must stay closed until verified.
    assert 'id="provider-train2earn"' in PAGE
    assert 'Coming soon</button>' in PAGE
    assert 'Δεν δίνει ακόμη THC' in PAGE


def test_advertiser_console_uses_existing_authenticated_campaign_endpoints():
    for marker in (
        'id="earn-tab-advertise"', 'id="earn-panel-advertise"',
        'id="earn-advertiser-form"', 'id="earn-advertiser-creative-form"',
        'id="earn-advertiser-list"', 'id="earn-advertiser-refresh"',
        "'/api/earn/ads/campaign/create'", "'/api/earn/ads/campaign/list'",
        "'/creative/add'", "placement: 'earn'", "credentials: 'same-origin'",
    ):
        assert marker in PAGE
    assert "pending_review" in PAGE.lower() or "pending review" in PAGE.lower()
    assert "not live until approved and funded" in PAGE.lower()


def test_advertiser_user_content_is_rendered_as_text_not_html():
    assert "child.textContent = String(value ?? '')" in PAGE
    assert "row.appendChild" not in PAGE or "list.appendChild(row)" in PAGE
    assert "campaign.name || 'Campaign'" in PAGE
    assert "url.protocol === 'https:'" in PAGE
    assert 'id="earn-tab-account"' in PAGE
