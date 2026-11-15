"""Earn-only navigation and translations do not change wallet/provider behavior."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "templates/earn_beta.html").read_text()
BASE = (ROOT / "templates/base.html").read_text()


def test_earn_only_hides_global_chain_header():
    assert '{% extends "base.html" %}' in HTML
    assert "{% block styles %}" in HTML
    assert "body:has(.earn-beta) > .navbar" in HTML
    assert "body:has(.earn-beta) > .top-controls" in HTML
    assert ".navbar {" in BASE
    assert 'id="earn-language"' in HTML
    assert 'class="earn-product-header"' in HTML


def test_manual_language_is_shared_with_chain_and_survives_navigation():
    assert "localStorage.getItem('thr_lang')" in HTML
    assert "localStorage.setItem('thr_lang', normalized)" in HTML
    assert "window.setLanguage(next)" in HTML
    assert "window.addEventListener('langChanged'" in HTML
    assert "window.addEventListener('earnLocaleChanged'" in HTML
    assert "navigator.languages" in HTML
    assert "document.documentElement.lang" in HTML
    for lang in ("gr", "en", "es", "ja", "ru"):
        assert f'<option value="{lang}">' in HTML
        assert f"    {lang}: {{" in HTML


def test_new_sections_covered_by_e2e_translate_keys():
    for key in (
        "journeyHeadline", "journeyDescription", "journeyDisclaimer",
        "offersTab", "rewardsTab", "communityTab", "accountTab",
        "advertiseTab", "advertiseHeadline", "advertiseDescription",
        "newCampaign", "campaignLabel", "bidLabel", "totalLabel",
        "creativeTitle", "creativeImage", "createDraft", "submitCreative",
        "gymDescription", "gymStatus",
    ):
        assert f'data-earn-copy="{key}"' in HTML
    assert "document.querySelectorAll('.earn-beta [data-earn-copy]')" in HTML


def test_cpx_has_readable_brand_without_unverified_remote_favicon():
    assert 'earn-provider-brand--cpx' in HTML
    assert '<span class="earn-provider-letter">CPX</span>' in HTML
    assert 'https://www.cpx-research.com/favicon.ico' not in HTML


def test_provider_and_ad_workflow_untouched():
    for marker in (
        'id="earn-surveys"', 'id="earn-timewall"',
        "window.ThronosEarnTabs.open(provider",
        'id="promo-overlay"', 'id="earn-frame"',
        '/api/earn/ads/impression', '/api/earn/ads/click',
        '/api/earn/ads/campaign/create', '/api/earn/ads/campaign/list',
    ):
        assert marker in HTML
