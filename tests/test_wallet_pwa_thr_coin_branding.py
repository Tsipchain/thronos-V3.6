"""Regression guards for THR coin branding in the existing Wallet PWA.

Only visual changes are allowed; the native wallet and APK code must remain
untouched. These tests deliberately inspect the PWA presentation boundary.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PWA = ROOT / "public" / "wallet-pwa"
COIN = "/static/img/thronos-coin.png"


def test_existing_official_coin_art_is_reused():
    assert (ROOT / COIN.lstrip("/")).is_file()
    assert (ROOT / COIN.lstrip("/")).stat().st_size > 1024


def test_logo_is_present_in_import_unlock_and_wallet_header():
    js = (PWA / "app.js").read_text()
    assert f"const THR_COIN_LOGO_URL = '{COIN}';" in js
    assert "thr-brand--large" in js
    assert "thr-brand--unlock" in js
    assert js.count("thr-brand--small") >= 2
    assert "const THR_COIN_MARK" in js
    assert "function tokenIcon(symbol)" in js


def test_thr_token_uses_coin_image_without_altering_other_asset_icons():
    js = (PWA / "app.js").read_text()
    assert "(symbol || '').toUpperCase() === 'THR' ? THR_COIN_MARK" in js
    assert "String(sym).toUpperCase() === 'THR' ? THR_COIN_LOGO_URL" in js
    assert "BTC: '₿'" in js
    assert "function renderBalances(data)" in js
    assert "showTokenDetail(JSON.parse(row.dataset.token))" in js


def test_service_worker_version_and_offline_branding_asset():
    sw = (PWA / "sw.js").read_text()
    assert "thr-wallet-pwa-v28" in sw
    assert f"'{COIN}'" in sw
    assert "if (url.pathname.startsWith('/pwa-api/') || url.pathname.startsWith('/api/')) return;" in sw
    manifest = (PWA / "manifest.json").read_text()
    assert '"/wallet-pwa/"' in manifest
    assert '"/static/img/thronos-token.png"' in manifest


def test_no_unscoped_global_visual_rewrite():
    css = (PWA / "app.css").read_text()
    assert ".thr-brand" in css
    assert ".thr-coin-mark" in css
    assert ".token-icon .thr-coin-mark" in css
    assert "#balancesArea .token-tap-row img" in css
