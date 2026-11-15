"""The extension opens its existing Earn web account without touching wallet secrets."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "public" / "extension"


def test_earn_action_opens_existing_web_without_wallet_key_payload():
    html = (EXT / "popup.html").read_text()
    js = (EXT / "popup.js").read_text()
    assert 'id="actEarnWeb"' in html
    assert "document.getElementById('actEarnWeb').addEventListener('click'" in js
    assert "chrome.tabs.create({ url: API + '/earn' })" in js
    assert "const API = 'https://api.thronoschain.org'" in js


def test_existing_wallet_actions_stay_available():
    html = (EXT / "popup.html").read_text()
    for action in ("actSend", "actReceive", "actSwap", "actStake",
                   "actBridge", "actHistory", "actNetworks", "actSettings"):
        assert f'id="{action}"' in html
    assert 'id="actEarnWeb"' in html
