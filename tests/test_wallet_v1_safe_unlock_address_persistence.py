"""
Static guard tests for safe Wallet V1 unlock address persistence.

The header unlock flow may persist only the user-entered THR address after a
successful unlock, and it must continue to reject system wallets and avoid
storing decrypted private keys in browser storage.
"""

import re
from pathlib import Path


SAFE_USER_WALLET = "THRE85A3E0A09A57212CDB222A9BF5B6E07A9B820E4"
SYSTEM_WALLET = "THR5DF27A86C477F381594E896F0E55357DEC5942BA"


def read(path: str) -> str:
    return Path(path).read_text()


def unlock_function() -> str:
    content = read("templates/base.html")
    match = re.search(
        r"async function unlockWalletV1FromHeader\(\)\{[\s\S]*?\n\}",
        content,
    )
    assert match is not None, "unlockWalletV1FromHeader must exist"
    return match.group(0)


def test_successful_unlock_reads_thr_address_field():
    body = unlock_function()
    assert "document.getElementById('walletWidgetThrAddress')" in body


def test_successful_unlock_persists_wallet_v1_address():
    session = read("static/wallet_session.js")
    assert "function persistActiveUserAddress(addr)" in session
    assert "localStorage.setItem(V1_ADDRESS_KEY, normalized)" in session
    assert "wallet_v1_address" in session


def test_successful_unlock_persists_thr_address():
    session = read("static/wallet_session.js")
    assert "localStorage.setItem(ADDRESS_KEY, normalized)" in session
    assert "thr_address" in session


def test_successful_unlock_dispatches_events_with_detail_address():
    body = unlock_function()
    assert "thronos:wallet:v1:unlocked" in body
    assert "detail: { address: activeAddress }" in body
    assert "thronos:wallet:state-changed" in body


def test_failed_unlock_returns_before_address_persistence():
    body = unlock_function()
    failed_unlock_index = body.index("if (!ok)")
    persist_index = body.index("persistActiveUserAddress")
    assert failed_unlock_index < persist_index
    failed_block = body[failed_unlock_index:persist_index]
    assert "localStorage.setItem('wallet_v1_address'" not in failed_block
    assert "localStorage.setItem('thr_address'" not in failed_block
    assert "wallet_v1_migration_meta" not in failed_block


def test_missing_address_rejected_before_unlock_and_persistence():
    body = unlock_function()
    missing_index = body.index("wallet_address_required")
    unlock_index = body.index("walletSession.unlockWallet")
    persist_index = body.index("persistActiveUserAddress")
    assert missing_index < unlock_index < persist_index


def test_system_wallet_rejected_before_unlock_and_persistence():
    body = unlock_function()
    system_guard_index = body.index("system_wallet_not_allowed")
    unlock_index = body.index("walletSession.unlockWallet")
    persist_index = body.index("persistActiveUserAddress")
    assert system_guard_index < unlock_index < persist_index


def test_thr5df_system_wallet_remains_blocked():
    for path in ["static/wallet_session.js", "public/static/wallet_session.js"]:
        content = read(path)
        assert SYSTEM_WALLET in content
        assert "isSystemWalletAddress(normalized)" in content
        assert "throw new Error('system_wallet_not_allowed')" in content


def test_no_decrypted_private_key_stored_in_browser_storage():
    for path in ["templates/base.html", "static/wallet_session.js", "public/static/wallet_session.js"]:
        content = read(path)
        assert not re.search(r"(?:localStorage|sessionStorage)\.setItem\([^\)]*(?:unlockedPrivateKeyHex|privateKeyHex|private_key|privateKey)", content)


def test_diagnostics_include_expected_success_fields():
    content = read("templates/base.html")
    assert "active_wallet_address: active || ''" in content
    assert "local_storage_thr_address: localAddr || ''" in content
    assert "ignored_system_wallet: ignoredSystemWallet" in content


def test_safe_user_wallet_format_is_valid_test_fixture():
    assert SAFE_USER_WALLET.startswith("THR")
    assert 20 <= len(SAFE_USER_WALLET) <= 100
    assert SAFE_USER_WALLET != SYSTEM_WALLET
