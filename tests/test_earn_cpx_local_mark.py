"""CPX branding uses an in-repo static icon and does not change provider execution."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "templates/earn_beta.html").read_text()
MARK = (ROOT / "static/img/cpx-research-mark.svg").read_text()


def test_cpx_has_local_mark_with_visible_text_fallback():
    assert 'src="/static/img/cpx-research-mark.svg"' in HTML
    assert '<span class="earn-provider-letter">CPX</span>' in HTML
    assert '<svg' in MARK
    assert 'viewBox="0 0 76 76"' in MARK
    assert 'CPX Research' in MARK


def test_cpx_open_and_existing_ads_unmodified():
    for guard in (
        'id="earn-surveys"', 'id="provider-cpx"',
        "window.ThronosEarnTabs.open(provider",
        'id="promo-overlay"',
        '/api/earn/ads/impression', '/api/earn/ads/click',
    ):
        assert guard in HTML
