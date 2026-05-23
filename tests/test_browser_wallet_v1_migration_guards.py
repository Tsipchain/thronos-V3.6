from pathlib import Path


def test_fetch_normalizer_preserves_wallet_v1_exact_paths():
    text = Path('static/fetch_utils.js').read_text(encoding='utf-8')
    for path in [
        '/api/v1/address/derive',
        '/api/v1/tx/send',
        '/api/v1/wallet/migrate',
        '/api/v1/wallet/health',
        '/api/v1/wallet/fee-estimate',
    ]:
        assert path in text
    assert 'function isWalletV1ExactPath' in text


def test_wallet_session_uses_exact_v1_derive_path():
    text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    assert "fetch('/api/v1/address/derive'" in text
    assert '/api/address/derive' not in text


def test_no_rewrite_codepath_to_legacy_derive():
    text = Path('static/fetch_utils.js').read_text(encoding='utf-8')
    assert "path = path.replace(/^/api/v1/".replace('^/','^\\/') not in text  # sanity no-op
    assert "path = path.replace(/^\\/api\\/v1\\//, \"/api/\")" in text
    # and exact-preserve guard exists before generic rewrite
    guard_idx = text.find('if (isWalletV1ExactPath(path))')
    rewrite_idx = text.find('path = path.replace(/^\\/api\\/v1\\//, "/api/")')
    assert guard_idx != -1 and rewrite_idx != -1 and guard_idx < rewrite_idx


def test_no_hardcoded_vercel_wallet_session_url():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'https://thrchain.vercel.app/static/wallet_session.js' not in text


def test_no_sensitive_fields_in_migration_payload():
    text = Path('static/wallet_session.js').read_text(encoding='utf-8')
    i0 = text.find('const body = { old_thr_address')
    i1 = text.find('};', i0)
    body = text[i0:i1]
    assert 'privateKey' not in body
    assert 'mnemonic' not in body
    assert 'seed' not in body.lower()
    assert 'passphrase' not in body
