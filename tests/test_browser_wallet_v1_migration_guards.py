from pathlib import Path


def test_base_wallet_session_path_points_to_existing_repo_file():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert "filename='wallet_session.js'" in text
    assert Path('static/wallet_session.js').exists()


def test_no_hardcoded_vercel_wallet_session_url():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'https://thrchain.vercel.app/static/wallet_session.js' not in text


def test_base_loads_secp_before_wallet_session():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    secp_idx = text.find('@noble/secp256k1')
    wallet_idx = text.find("filename='wallet_session.js'")
    assert secp_idx != -1 and wallet_idx != -1 and secp_idx < wallet_idx


def test_wallet_session_exports_window_wallet_session():
    pub_text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    static_text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    assert 'window.walletSession = {' in pub_text
    assert 'window.walletSession = {' in static_text


def test_create_wallet_v1_path_present_and_no_walletsession_missing_error_literal():
    text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    assert 'async function createWalletV1' in text
    assert 'walletSession is not defined' not in text
