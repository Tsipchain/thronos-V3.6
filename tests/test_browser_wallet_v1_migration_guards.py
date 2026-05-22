from pathlib import Path


def test_no_duplicate_sign_transaction_definition():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert text.count('function signTransaction') == 1


def test_no_legacy_signing_stub_error():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'wallet_v1_signing_not_available_in_legacy_session' not in text


def test_canonical_tx_message_sorted_and_compact():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'function canonicalTxMessage' in text
    assert '{"amount":' in text
    assert ',"from":' in text
    assert ',"nonce":' in text
    assert ',"timestamp":' in text
    assert ',"to":' in text
    assert ',"token":' in text


def test_sign_transaction_does_not_use_raw_json_stringify_txcore():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'sha256Hex(JSON.stringify(txCore))' not in text
    assert 'canonicalTxMessage(txCore)' in text


def test_signed_fields_exact_and_excludes_publickey_signature():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'const txForSigning = {' in text
    for required in ['from: txCore.from', 'to: txCore.to', 'amount: txCore.amount', 'token: txCore.token', 'nonce: txCore.nonce', 'timestamp: txCore.timestamp']:
        assert required in text
    assert 'publicKey' not in text[text.find('const txForSigning = {'):text.find('};', text.find('const txForSigning = {'))]
    assert 'signature' not in text[text.find('const txForSigning = {'):text.find('};', text.find('const txForSigning = {'))]


def test_migration_creates_v1_before_posting_migrate_endpoint():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    create_idx = text.find('await createWalletV1({ pin })')
    post_idx = text.find("fetch('/api/v1/wallet/migrate'")
    assert create_idx != -1 and post_idx != -1 and create_idx < post_idx


def test_sign_transaction_uses_secp_sign():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'secp.sign' in text


def test_no_sensitive_secret_fields_in_migration_payload():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    migrate_body_start = text.find('const body = { old_thr_address')
    migrate_body_end = text.find('};', migrate_body_start)
    body_seg = text[migrate_body_start:migrate_body_end]
    assert 'privateKey' not in body_seg
    assert 'mnemonic' not in body_seg
    assert 'seed' not in body_seg.lower()
    assert 'passphrase' not in body_seg
