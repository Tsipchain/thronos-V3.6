"""Source and runtime guards for Wallet V1 browser credential handling."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSION = (ROOT / "static" / "wallet_session.js").read_text()
PUBLIC_SESSION = (ROOT / "public" / "static" / "wallet_session.js").read_text()
AUTH = (ROOT / "static" / "wallet_auth.js").read_text()
PUBLIC_AUTH = (ROOT / "public" / "static" / "wallet_auth.js").read_text()
BASE = (ROOT / "templates" / "base.html").read_text()
PLEDGE = (ROOT / "templates" / "pledge_form.html").read_text()


def test_public_wallet_scripts_are_byte_identical():
    assert SESSION == PUBLIC_SESSION
    assert AUTH == PUBLIC_AUTH


def test_modern_wallet_paths_never_persist_plaintext_pin():
    combined = "\n".join((SESSION, AUTH, BASE, PLEDGE))
    assert "setItem(PIN_KEY" not in combined
    assert "setItem('wallet_pin'" not in combined
    assert 'setItem("wallet_pin"' not in combined
    assert "retireLegacyPinAfterVerifiedV1('wallet_created')" in SESSION
    assert "retireLegacyPinAfterVerifiedV1('signing_enrollment')" in SESSION
    assert "retireLegacyPinAfterVerifiedV1('signing_key_import')" in SESSION
    assert "retireLegacyPinAfterVerifiedV1?.('recovery_kit_restore')" in BASE


def test_auth_secrets_are_not_copied_to_session_storage():
    assert "sessionStorage.setItem(_SESSION_SECRET_KEY" not in AUTH
    assert "sessionStorage.setItem(_SESSION_ADDRESS_KEY" not in AUTH
    assert "sessionStorage.setItem(_SESSION_TS_KEY" not in AUTH
    assert "modernWalletV1 ? '' : getSigningMaterial(address)" in AUTH
    assert "if (hasV1SigningMaterial()) return isUnlockedFor(address)" in AUTH


def test_runtime_signer_requires_explicit_exact_address_binding():
    assert "unlockedPrivateKeyHex && normalized && boundAddress && boundAddress === normalized" in SESSION
    assert "claimed !== active || !hasRuntimeSigningMaterial(claimed)" in SESSION
    assert "assertRuntimeSignerForSender(txCore" in SESSION
    assert "assertRuntimeSignerForSender(intent && intent.from_thr)" in SESSION
    assert "unlockedForAddress = address" in SESSION
    assert "unlockedForAddress = activeAddress" in SESSION


def test_address_switch_and_lock_clear_runtime_binding():
    assert "current !== next) lockWallet()" in SESSION
    assert "normalizeAddress(unlockedForAddress) !== normalized) lockWallet()" in SESSION
    assert "unlockedPrivateKeyHex = null; unlockedForAddress = null" in SESSION


def test_missing_pin_is_not_authorization():
    require_start = SESSION.index("function requirePin")
    require_end = SESSION.index("// ── Unified user-presence", require_start)
    require_body = SESSION[require_start:require_end]
    assert "if (!stored) return false" in require_body
    assert "if(!stored) return true" not in require_body


def test_legacy_retirement_is_verified_and_non_destructive():
    assert "if (!isWalletV1()) return false" in SESSION
    assert "localStorage.removeItem(PIN_KEY)" in SESSION
    assert "localStorage.removeItem(SEND_SECRET_KEY)" not in SESSION[SESSION.index("function retireLegacyPinAfterVerifiedV1"):SESSION.index("function setPin")]
    assert "status: 'plaintext_pin_retired'" in SESSION


def test_decrypted_key_is_never_written_to_browser_storage():
    for secret_name in ("decryptedPrivKeyHex", "decryptedPrivateKey", "unlockedPrivateKeyHex"):
        assert f"localStorage.setItem({secret_name}" not in SESSION
        assert f"sessionStorage.setItem({secret_name}" not in SESSION
    assert "sessionStorage.setItem(LEGACY_SESSION_UNLOCK_KEY" not in SESSION
