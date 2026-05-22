from pathlib import Path


def test_no_duplicate_sign_transaction_definition():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert text.count('function signTransaction') == 1


def test_no_legacy_signing_stub_error():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'wallet_v1_signing_not_available_in_legacy_session' not in text


def test_migration_creates_v1_before_posting_migrate_endpoint():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    create_idx = text.find('await createWalletV1({ pin })')
    post_idx = text.find("fetch('/api/v1/wallet/migrate'")
    assert create_idx != -1 and post_idx != -1 and create_idx < post_idx


def test_sign_transaction_uses_secp_sign():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    assert 'secp.sign' in text


def test_no_sensitive_secret_fields_in_migration_or_tx_payload():
    text = Path('public/static/wallet_session.js').read_text(encoding='utf-8')
    # body includes only old_thr_address, legacy_secret, new_compressed_public_key (+ optional signed request)
    migrate_body_start = text.find('const body = { old_thr_address')
    migrate_body_end = text.find('};', migrate_body_start)
    body_seg = text[migrate_body_start:migrate_body_end]
    assert 'privateKey' not in body_seg
    assert 'mnemonic' not in body_seg
    assert 'seed' not in body_seg.lower()
    assert 'passphrase' not in body_seg


def test_header_still_uses_v1_migration_mode_guardrails():
    text = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'walletWidgetLegacySecret' in text
    assert 'walletWidgetSecret' not in text
