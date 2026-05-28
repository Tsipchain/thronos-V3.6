from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION_JS = (ROOT / "public/static/wallet_session.js").read_text()
AUTH_JS = (ROOT / "public/static/wallet_auth.js").read_text()


def test_wallet_session_resolves_migrated_credential_source():
    assert "function getCredentialLookupAddress" in SESSION_JS
    assert "info.old_address" in SESSION_JS
    assert "info.new_v1_address" in SESSION_JS
    assert "getRawSeedForAddress(info.old_address)" in SESSION_JS
    assert "getRawSeedForAddress(info.new_v1_address)" in SESSION_JS


def test_wallet_session_preserves_wallet_v1_public_api():
    for symbol in (
        "createWalletV1",
        "getPublicKey",
        "signTransaction",
        "isWalletV1",
        "migrateLegacyWallet",
        "canonicalTxMessage",
        "unlock: unlockWallet",
        "lock: lockWallet",
    ):
        assert symbol in SESSION_JS


def test_wallet_session_preserves_encrypted_v1_signing_flow():
    assert "V1_ENCRYPTED_KEY" in SESSION_JS
    assert "V1_PUBLIC_KEY" in SESSION_JS
    assert "unlockedPrivateKeyHex" in SESSION_JS
    assert "decryptPrivateKeyHex" in SESSION_JS
    assert "encryptPrivateKeyHex" in SESSION_JS
    assert "secp.sign" in SESSION_JS
    assert "canonicalTxMessage(txCore" in SESSION_JS


def test_wallet_auth_uses_active_address_and_credential_lookup():
    assert "getActiveWalletAddress()" in AUTH_JS
    assert "getCredentialLookupAddress(address)" in AUTH_JS
    assert "credentialLookupAddress" in AUTH_JS
    assert "window.walletSession.unlockWallet({ pin, address })" in AUTH_JS
    assert "buildAuthResult(address" in AUTH_JS


def test_wallet_auth_returns_signing_wrapper_fields():
    assert "getPublicKey: () =>" in AUTH_JS
    assert "window.walletSession.getPublicKey()" in AUTH_JS
    assert "signTransaction: (txCore) =>" in AUTH_JS
    assert "window.walletSession.signTransaction(txCore)" in AUTH_JS


def test_wallet_session_has_no_duplicate_legacy_shadow_functions():
    assert SESSION_JS.count("function getAddress(") == 1
    assert SESSION_JS.count("function setAddress(") == 1
    assert SESSION_JS.count("function getSendSeed(") == 1
    assert SESSION_JS.count("function setSendSeed(") == 1


def test_missing_signing_material_fails_closed_with_clear_error():
    assert "missing_wallet_signing_material" in AUTH_JS
    assert "No send seed found after unlock" not in AUTH_JS


def test_wallet_auth_does_not_persist_plaintext_secret_cache():
    assert "sessionStorage.setItem('thr_auth_secret'" not in AUTH_JS
    assert "let cachedAuthSecret = ''" in AUTH_JS
    assert "cachedAuthSecret = authSecret" in AUTH_JS


def test_safe_diagnostics_do_not_log_secret_values():
    assert "active_wallet_address" in SESSION_JS
    assert "credential_lookup_address" in SESSION_JS
    assert "migration_old_address" in SESSION_JS
    assert "migration_new_v1_address" in SESSION_JS
    assert "has_encrypted_send_seed" in SESSION_JS
    assert "has_signing_material" in SESSION_JS
    assert "console.info('[WalletAuth]'" in SESSION_JS
