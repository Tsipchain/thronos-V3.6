from pathlib import Path
import re


def _template_sources():
    for p in Path('templates').glob('*.html'):
        text = p.read_text(encoding='utf-8')
        for m in re.finditer(r'<script[^>]+src="([^"]+)"', text):
            yield p, m.group(1)


def test_no_template_references_missing_wallet_sdk_static():
    refs = [(p, s) for p, s in _template_sources() if 'wallet_sdk.js' in s]
    assert refs, 'expected at least one wallet_sdk.js reference'
    assert Path('static/wallet_sdk.js').exists()


def test_no_template_references_missing_wallet_auth_static():
    refs = [(p, s) for p, s in _template_sources() if 'wallet_auth.js' in s]
    assert refs, 'expected at least one wallet_auth.js reference'
    assert Path('static/wallet_auth.js').exists()


def test_wallet_session_still_loaded_from_local_static():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert "filename='wallet_session.js'" in text


def test_no_hardcoded_vercel_wallet_session_url_any_template():
    for p in Path('templates').glob('*.html'):
        text = p.read_text(encoding='utf-8')
        assert 'https://thrchain.vercel.app/static/wallet_session.js' not in text, p
