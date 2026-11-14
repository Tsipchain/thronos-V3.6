"""Keep standalone Earn presentation distinct from Wallet PWA and reward logic."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_standalone_earn_hero_stays_in_web_template():
    web = (ROOT / "templates/earn_beta.html").read_text()
    assert 'class="earn-journey"' in web
    for marker in ("earn-journey-heading", "earn-journey-steps", "earn-journey-disclaimer"):
        assert marker in web
    assert "verified provider receipts" in web.lower()
    assert "No wallet is required to start" in web


def test_earn_auth_and_provider_bindings_are_preserved():
    web = (ROOT / "templates/earn_beta.html").read_text()
    for marker in ('id="earn-auth"', 'id="earn-main"', 'id="earn-submit"',
                   'id="earn-surveys"', 'id="earn-timewall"',
                   'id="earn-balance-value"', 'id="earn-pending-value"'):
        assert marker in web


def test_hero_not_added_to_wallet_home_or_wallet_pwa_shell():
    wallet_css = (ROOT / "public/wallet-pwa/app.css").read_text()
    wallet_js = (ROOT / "public/wallet-pwa/app.js").read_text()
    assert "earn-journey-steps" not in wallet_css
    assert "earn-journey-steps" not in wallet_js
