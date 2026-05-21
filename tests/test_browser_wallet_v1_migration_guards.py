from pathlib import Path


def test_send_html_no_auth_secret_and_no_send_thr():
    content = Path('templates/send.html').read_text(encoding='utf-8')
    assert 'auth_secret' not in content
    assert '/send_thr' not in content
    assert '/api/v1/tx/send' in content


def test_fetch_utils_preserves_wallet_v1_paths():
    content = Path('static/fetch_utils.js').read_text(encoding='utf-8')
    assert '/api/v1/tx/send' in content
    assert '/api/v1/wallet/health' in content
    assert '/api/v1/address/derive' in content
    assert "path = path.replace(/^/api/v1/".replace('/', '\\/') not in content
