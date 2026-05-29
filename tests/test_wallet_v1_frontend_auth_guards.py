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
    assert "return localStorage.getItem(V1_ADDRESS_KEY) || localStorage.getItem(ADDRESS_KEY) || ''" in SESSION_JS


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


def test_wallet_auth_detects_missing_v1_signing_material():
    """Verify WalletAuth detects when V1 encrypted key is missing."""
    assert "hasV1SigningMaterial()" in AUTH_JS
    assert "window.walletSession.isWalletV1" in AUTH_JS


def test_wallet_auth_triggers_enrollment_when_material_missing():
    """Verify WalletAuth calls enrollSigningMaterial when signing material is missing."""
    assert "enrollSigningMaterial" in AUTH_JS
    assert "if (!hasV1SigningMaterial())" in AUTH_JS
    assert "window.walletSession.enrollSigningMaterial" in AUTH_JS


def test_wallet_session_has_enrollment_function():
    """Verify enrollSigningMaterial exists and handles credential lookup."""
    assert "async function enrollSigningMaterial" in SESSION_JS
    assert "credentialLookupAddress" in SESSION_JS
    assert "/api/v1/wallet/bind_public_key" in SESSION_JS


def test_enrollment_uses_credential_lookup_for_binding():
    """Verify enrollment includes credential lookup address in binding payload."""
    assert "body: JSON.stringify({" in SESSION_JS
    assert "address: activeAddress" in SESSION_JS
    assert "credential_lookup_address: lookupAddress" in SESSION_JS
    assert "public_key: pub" in SESSION_JS


def test_enrollment_stores_encrypted_key_only():
    """Verify enrollment stores only encrypted key + public key, not plaintext."""
    enrollment_start = SESSION_JS.find("async function enrollSigningMaterial")
    enrollment_end = SESSION_JS.find("\n  }", enrollment_start + 100)
    enrollment_code = SESSION_JS[enrollment_start:enrollment_end]

    assert "V1_ENCRYPTED_KEY, enc" in enrollment_code
    assert "V1_PUBLIC_KEY, pub" in enrollment_code
    assert "unlockedPrivateKeyHex = priv" in enrollment_code
    assert "localStorage.setItem(V1_ENCRYPTED_KEY" in enrollment_code
    assert "localStorage.setItem(V1_PUBLIC_KEY" in enrollment_code


def test_enrollment_does_not_use_raw_seed_prompt():
    """Verify enrollment does not have getSendSeed() raw seed access in wrong place."""
    enrollment_start = SESSION_JS.find("async function enrollSigningMaterial")
    enrollment_end = SESSION_JS.find("return { address: activeAddress", enrollment_start)
    enrollment_code = SESSION_JS[enrollment_start:enrollment_end]

    # Enrollment should accept getSendSeed as a param (authSecret), not prompt for it
    assert "authSecret || getSendSeed(lookupAddress)" in enrollment_code
    assert "prompt('Enter" not in enrollment_code or "enrollment" not in enrollment_code


def test_wallet_auth_shows_clear_error_when_enrollment_fails():
    """Verify clear error message when signing key enrollment is impossible."""
    assert "Wallet V1 signing key is missing" in AUTH_JS
    assert "Please unlock/migrate wallet" in AUTH_JS


def test_wallet_auth_no_session_storage_for_auth_secret():
    """Verify wallet auth does not persist plaintext secret in sessionStorage."""
    assert "sessionStorage.setItem('thr_auth_secret')" not in AUTH_JS
    assert "sessionStorage.removeItem('thr_auth_secret')" in AUTH_JS
