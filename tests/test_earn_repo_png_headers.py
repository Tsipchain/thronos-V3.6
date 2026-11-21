"""Installed Earn web and Wallet PWA use the existing uploaded repository PNG.

The change is intentionally scoped to Earn presentation, not wallet/home,
signing, backend offerwalls, ad delivery or payouts.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "static/img/THRONOS EARN.png"
WEB = (ROOT / "templates/earn_beta.html").read_text()
WALLET_JS = (ROOT / "public/wallet-pwa/app.js").read_text()
WALLET_CSS = (ROOT / "public/wallet-pwa/app.css").read_text()
WALLET_SW = (ROOT / "public/wallet-pwa/sw.js").read_text()
MANIFEST = json.loads((ROOT / "static/earn.webmanifest").read_text())


def test_actual_uploaded_asset_is_png_and_used_without_remaking_logo():
    assert IMAGE.is_file()
    with IMAGE.open("rb") as stream:
        assert stream.read(8) == b"\x89PNG\r\n\x1a\n"
    assert 'src="/static/img/THRONOS%20EARN.png"' in WEB
    assert 'src="/static/img/THRONOS%20EARN.png"' in WALLET_JS
    assert 'ThronosLabs &amp; ENCOMM' in WEB
    assert 'ThronosLabs &amp; ENCOMM' in WALLET_JS
    assert "ENCOMM" in MANIFEST["name"]


def test_web_language_menu_is_above_logo_without_global_chain_nav():
    start = WEB.index('<header class="earn-product-header"')
    end = WEB.index('</header>', start)
    section = WEB[start:end]
    assert section.index('id="earn-language"') < section.index('class="earn-product-logo"')
    assert 'class="earn-product-toolbar"' in section
    assert 'class="earn-product-identity"' in section
    assert "body:has(.earn-beta) > .navbar" in WEB
    assert "body:has(.earn-beta) > .top-controls" in WEB


def test_wallet_earn_language_menu_is_above_logo_and_scoped_to_earn():
    earn_start = WALLET_JS.index("async function showEarn(options = {})")
    earn_end = WALLET_JS.index("const body = document.getElementById('earnPwaBody')", earn_start)
    earn = WALLET_JS[earn_start:earn_end]
    assert earn.index('id="earnPwaLanguage"') < earn.index('class="earn-pwa-brand-image"')
    assert 'id="earnBackBtn"' in earn
    assert "localStorage.setItem('thr_lang', _earnPwaLang)" in earn
    assert "_applyEarnPwaLabels();" in earn
    assert "document.getElementById('earnChristmasTimewall').addEventListener('click'" in earn
    assert ".earn-pwa-product-header" in WALLET_CSS
    assert ".earn-pwa-brand-image" in WALLET_CSS


def test_wallet_install_cache_refresh_only_updates_shell_and_logo():
    assert "thr-wallet-pwa-v29" in WALLET_SW
    assert "'/static/img/THRONOS%20EARN.png'" in WALLET_SW
    assert "if (url.pathname.startsWith('/pwa-api/') || url.pathname.startsWith('/api/')) return;" in WALLET_SW


def test_offerwall_and_ad_ids_survive_without_logic_changes():
    for value in ('id="earn-surveys"', 'id="earn-timewall"', 'id="earn-tab-advertise"',
                  'id="earn-language"', 'id="earn-ad-preview-button"'):
        assert value in WEB
    assert "window.ThronosEarnTabs.open(provider" in WEB
    assert "/api/earn/ads/impression" in WEB
    assert "/api/earn/ads/click" in WEB
