"""BitcoTasks is a sponsored direct-link only, not an Earn offerwall.

Historical receipt handling remains in the backend for audit/clearing.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "templates" / "earn_beta.html").read_text()
PWA = (ROOT / "public" / "wallet-pwa" / "app.js").read_text()
TABS = (ROOT / "public" / "wallet-pwa" / "earn-provider-tabs.js").read_text()
SERVICE = (ROOT / "services" / "earn_account.py").read_text()


def test_bitcotasks_not_in_earn_offerwall_surface():
    assert 'id="provider-bitcotasks"' not in PAGE
    assert 'id="earn-bitcotasks"' not in PAGE
    assert "openProvider('bitcotasks'" not in PAGE
    assert 'data-earn-provider="bitcotasks"' not in PWA
    assert "bitcotasks: { endpoint:" not in PWA
    assert "cpx|bitcotasks" not in TABS


def test_existing_direct_sponsor_link_is_preserved_without_earn_claims():
    assert "https://bitcotasks.com/promote/81663" in PAGE
    assert "badge: 'Sponsor'" in PAGE
    assert "thronos_bitcotasks_sponsor_last_shown" in PAGE
    assert "86400000" in PAGE
    assert "not a Thronos Earn offerwall" in PAGE


def test_earn_backend_offerwall_is_retired_but_historical_receipts_remain():
    assert 'error="bitcotasks_offerwall_retired"' in SERVICE
    assert 'def record_bitcotasks_receipt(' in SERVICE
    assert 'bitcotasks_receipts' in SERVICE


def test_other_provider_buttons_and_advertiser_funding_are_preserved():
    for marker in ('id="earn-surveys"', 'id="earn-timewall"', 'id="earn-pure"',
                   'id="earn-advertiser-form"', 'id="earn-advertiser-refresh"'):
        assert marker in PAGE
