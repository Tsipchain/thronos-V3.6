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


def test_wallet_auth_uses_active_address_and_credential_lookup():
    assert "getActiveWalletAddress()" in AUTH_JS
    assert "getCredentialLookupAddress(address)" in AUTH_JS
    assert "credentialLookupAddress" in AUTH_JS
    assert "window.walletSession.unlockWallet({ pin, address })" in AUTH_JS
    assert "return { address, authSecret, credentialLookupAddress }" in AUTH_JS


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
