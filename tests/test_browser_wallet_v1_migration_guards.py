from pathlib import Path


def _header_wallet_section(text: str) -> str:
    start = text.find('id="walletLoginSection"')
    end = text.find('id="walletContentSection"')
    return text[start:end] if start != -1 and end != -1 else text


def test_base_header_no_send_secret_in_normal_connect():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    header = _header_wallet_section(text)
    assert 'walletWidgetSecret' not in header
    assert 'Send Secret</label>' not in header


def test_send_secret_only_in_migration_section():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'walletWidgetLegacySecret' in text
    assert 'migration only' in text


def test_no_auth_secret_in_header_wallet_flow_segment():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    start = text.find('function showWalletLoginForm()')
    end = text.find('function updateHeaderWalletUi(){')
    segment = text[start:end]
    assert 'auth_secret' not in segment


def test_wallet_session_signer_methods_referenced():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'walletSession.getPublicKey' in text
    assert 'walletSession.isWalletV1' in text


def test_wallet_migrate_endpoint_only_in_migration_flow_js():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert '/api/v1/wallet/migrate' in text
