from pathlib import Path


def test_send_flow_no_legacy_secret_or_send_thr():
    text = Path('templates/send.html').read_text(encoding='utf-8')
    assert '/send_thr' not in text
    assert 'auth_secret' not in text
    assert 'getSendSeed' not in text


def test_send_flow_uses_v1_paths_and_signer():
    text = Path('templates/send.html').read_text(encoding='utf-8')
    assert '/api/v1/tx/send' in text
    assert '/api/v1/wallet/fee-estimate' in text
    assert 'walletSession.signTransaction' in text
    assert 'walletSession.getPublicKey' in text


def test_wallet_session_exposes_v1_signer_methods():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'function getPublicKey' in text
    assert 'async function signTransaction' in text
