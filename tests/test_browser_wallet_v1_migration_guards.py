from pathlib import Path


def test_base_does_not_reference_nonworking_noble_umd_dist():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert '@noble/secp256k1@2.2.3/dist/index.umd.min.js' not in text


def test_base_loads_local_secp_before_wallet_session():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    secp_idx = text.find("filename='vendor/noble-secp256k1.min.js'")
    wallet_idx = text.find("filename='wallet_session.js'")
    assert secp_idx != -1 and wallet_idx != -1 and secp_idx < wallet_idx


def test_get_secp_path_supports_real_loaded_global_and_waits_for_loader():
    text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    assert 'function _getSecp()' in text
    assert 'window.nobleSecp256k1' in text
    assert 'window.secp256k1' in text
    assert 'async function _ensureSecpLoaded()' in text
    assert 'window.__nobleSecp256k1Ready' in text


def test_create_wallet_v1_uses_ensured_secp_not_missing_stub():
    text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    assert 'const secp = await _ensureSecpLoaded();' in text
    assert 'secp256k1_library_missing' in text


def test_no_hardcoded_vercel_wallet_session_url():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'https://thrchain.vercel.app/static/wallet_session.js' not in text


def test_wallet_session_exports_window_wallet_session():
    text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    assert 'window.walletSession = {' in text


def test_no_sensitive_fields_in_migration_payload():
    text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    i0 = text.find('const body = { old_thr_address')
    i1 = text.find('};', i0)
    body = text[i0:i1]
    assert 'privateKey' not in body
    assert 'mnemonic' not in body
    assert 'seed' not in body.lower()
    assert 'passphrase' not in body
