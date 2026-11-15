"""Earn home-screen identity must remain separate from the Wallet PWA."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "static/earn.webmanifest").read_text())
EARN = (ROOT / "templates/earn_beta.html").read_text()
BASE = (ROOT / "templates/base.html").read_text()
WALLET = json.loads((ROOT / "public/wallet-pwa/manifest.json").read_text())


def test_earn_manifest_is_distinct_and_does_not_claim_wallet_routes():
    assert MANIFEST["id"] == "/earn"
    assert MANIFEST["start_url"] == "/earn"
    assert MANIFEST["scope"] == "/earn"
    assert MANIFEST["display"] == "standalone"
    assert MANIFEST["short_name"] == "Thronos Earn"
    assert MANIFEST["id"] != WALLET["id"]
    assert MANIFEST["start_url"] != WALLET["start_url"]
    assert MANIFEST["icons"][0]["src"] == "/static/img/thronos-coin.png"
    assert (ROOT / "static/img/thronos-coin.png").exists()


def test_earn_meta_only_in_opted_in_template():
    assert "{% block app_manifest %}{% endblock %}" in BASE
    assert '{% block app_manifest %}' in EARN
    assert "static', filename='earn.webmanifest'" not in BASE
    assert "filename='earn.webmanifest'" in EARN
    assert 'name="apple-mobile-web-app-title" content="Thronos Earn"' in EARN


def test_install_metadata_does_not_touch_provider_sessions_or_wallet_sw():
    assert "navigator.serviceWorker.register" not in EARN
    assert 'id="earn-surveys"' in EARN
    assert 'id="earn-timewall"' in EARN
    assert "showPromo(15)" in EARN
    assert "window.ThronosEarnTabs.open(provider" in EARN
