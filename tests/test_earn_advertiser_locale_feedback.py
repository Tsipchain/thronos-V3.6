"""Earn advertiser localization is purely presentational and changes no payment flows."""
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "templates/earn_beta.html").read_text()


def test_campaign_dashboard_reacts_to_language_and_keeps_saved_choice():
    assert "window.ThronosEarnLocale = { current: () => lang, change, apply, message }" in PAGE
    assert "window.addEventListener('earnLocaleChanged', () => {" in PAGE
    assert "tab?.getAttribute('aria-selected') === 'true'" in PAGE
    for language in ("en", "gr", "es", "ja", "ru"):
        assert f"    {language}: {{ loading:" in PAGE
    for key in ("loading", "campaignCreated", "artworkCreated", "invalidLinks", "unavailable"):
        assert f"localized('{key}'" in PAGE


def test_error_and_campaign_id_feedback_have_localized_templates():
    assert r"text.replace(/\{([a-z]+)\}/g," in PAGE
    assert "localized('campaignCreated', {id: String(data.campaign_id || '')})" in PAGE
    assert "localized('login')" in PAGE
    assert "localized('failed')" in PAGE
    assert "localized('status')" in PAGE


def test_advertiser_actions_and_reward_rails_unmodified():
    for marker in (
        "'/api/earn/ads/campaign/list'", "'/api/earn/ads/campaign/create'",
        "'/creative/add'", "'/api/earn/ads/campaign/'",
        "/api/earn/ads/impression", "/api/earn/ads/click",
        "window.ThronosEarnTabs.open(provider", "showPromo(15)",
        'id="earn-surveys"', 'id="earn-timewall"',
    ):
        assert marker in PAGE
