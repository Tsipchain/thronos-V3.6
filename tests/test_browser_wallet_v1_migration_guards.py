from pathlib import Path


def test_base_loads_secp_before_wallet_session():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    secp_idx = text.find('@noble/secp256k1')
    wallet_idx = text.find("filename='wallet_session.js'")
    assert secp_idx != -1 and wallet_idx != -1 and secp_idx < wallet_idx


def test_base_does_not_hardcode_vercel_wallet_session():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'https://thrchain.vercel.app/static/wallet_session.js' not in text


def test_get_secp_supports_loaded_global_variants():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'window.nobleSecp256k1' in text
    assert 'window.secp256k1' in text


def test_wallet_session_exports_required_signer_methods():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'createWalletV1' in text
    assert 'getPublicKey' in text
    assert 'signTransaction' in text


def test_no_sensitive_fields_in_migration_payload():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    i0 = text.find('const body = { old_thr_address')
    i1 = text.find('};', i0)
    body = text[i0:i1]
    assert 'privateKey' not in body
    assert 'mnemonic' not in body
    assert 'seed' not in body.lower()
    assert 'passphrase' not in body
