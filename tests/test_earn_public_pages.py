"""Public CPX publisher-information page contracts.

These checks keep the required information visible without coupling it to an
Earn session or exposing account data.
"""
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_public_earn_policy_routes_are_registered():
    source = (ROOT / "server.py").read_text()
    for route, template in (
        ("/terms", "earn_terms.html"),
        ("/privacy", "earn_privacy.html"),
        ("/contact", "earn_contact.html"),
    ):
        assert f'@app.get("{route}")' in source
        assert f'render_template("{template}")' in source


def test_earn_page_links_to_public_information():
    earn = (ROOT / "templates" / "earn_beta.html").read_text()
    for route in ("/terms", "/privacy", "/contact"):
        assert f'href="{route}"' in earn


def test_terms_do_not_claim_unreleased_money_movement():
    terms = (ROOT / "templates" / "earn_terms.html").read_text().lower()
    assert "cash-out" in terms
    assert "not enable" in terms
    assert "private key" in terms
    assert "pending record is not spendable" in terms


def test_privacy_page_describes_account_and_provider_boundaries():
    privacy = (ROOT / "templates" / "earn_privacy.html").read_text().lower()
    assert "password hash" in privacy
    assert "opaque provider identifier" in privacy
    assert "do not send the earn email address or optional wallet address to cpx" in privacy
    assert "do not request or store private keys" in privacy


def test_contact_page_has_a_real_support_channel_and_secret_warning():
    contact = (ROOT / "templates" / "earn_contact.html").read_text()
    assert "admin@thronoschain.org" in contact
    assert "Do not send passwords, private keys, seed phrases" in contact
