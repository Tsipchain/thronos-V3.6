"""Chrome extension THR visual branding regression guards."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "public" / "extension"


def test_extension_coin_art_is_bundled_and_not_network_fetched():
    asset = EXT / "icons" / "icon48.png"
    assert asset.is_file() and asset.stat().st_size > 1000
    source = (EXT / "popup.html").read_text()
    assert source.count('src="icons/icon48.png"') >= 3
    assert 'thr-coin-logo--welcome' in source
    assert 'thr-coin-logo--lock' in source


def test_swap_signing_handlers_remain_independent():
    js = (EXT / "popup.js").read_text()
    assert "async function submitSwap(" in js
    assert "/api/swap/execute" in js
    assert "async function submitSend(" in js
    assert "async function submitBridge(" in js


def test_extension_manifest_keeps_permissions_and_offline_icon():
    manifest = (EXT / "manifest.json").read_text()
    assert '"48": "icons/icon48.png"' in manifest
    assert '"service_worker": "background.js"' in manifest
    assert '"host_permissions"' in manifest
    css = (EXT / "popup.css").read_text()
    assert ".thr-coin-logo--welcome" in css
    assert ".thr-coin-logo--lock" in css
