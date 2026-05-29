from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_AUTH = ROOT / "static" / "wallet_auth.js"
PUBLIC_AUTH = ROOT / "public" / "static" / "wallet_auth.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_wallet_auth_copies_are_synchronized():
    assert _read(STATIC_AUTH) == _read(PUBLIC_AUTH)


def test_require_unlocked_wallet_returns_v1_compatible_contract():
    text = _read(STATIC_AUTH)
    assert "address," in text
    assert "authSecret," in text
    assert "credentialLookupAddress," in text
    assert "getPublicKey:" in text
    assert "signTransaction:" in text


def test_wallet_auth_fails_closed_without_signing_material_and_keeps_secret_memory_only():
    text = _read(STATIC_AUTH)
    assert "missing_wallet_signing_material" in text
    assert "sessionStorage.setItem('thr_auth_secret'" not in text
    assert 'sessionStorage.setItem("thr_auth_secret"' not in text


def test_wallet_auth_prefers_session_lookup_then_active_address():
    text = _read(STATIC_AUTH)
    assert "getCredentialLookupAddress(activeAddress)" in text
    assert "return activeAddress || info.new_v1_address || info.old_address || '';" in text
    assert "return info.old_address || info.new_v1_address || activeAddress || '';" not in text

SESSION_STATIC = ROOT / "static" / "wallet_session.js"
SESSION_PUBLIC = ROOT / "public" / "static" / "wallet_session.js"


def test_wallet_session_copies_are_synchronized_for_signing_enrollment():
    assert _read(SESSION_STATIC) == _read(SESSION_PUBLIC)


def test_wallet_auth_triggers_signing_enrollment_when_legacy_credential_exists():
    text = _read(STATIC_AUTH)
    assert "ensureSigningMaterial(address, credentialLookupAddress, authSecret)" in text
    assert "Wallet V1 signing upgrade required. Unlock with PIN to create encrypted V1 signing key." in text
    assert "walletSession.enrollSigningMaterial" in text


def test_wallet_session_enrolls_encrypted_key_and_does_not_store_plaintext_private_key():
    text = _read(SESSION_STATIC)
    assert "async function enrollSigningMaterial" in text
    assert "'/api/v1/wallet/bind_public_key'" in text
    assert "localStorage.setItem(V1_ENCRYPTED_KEY, enc)" in text
    assert "localStorage.setItem(V1_PUBLIC_KEY, pub)" in text
    assert "unlockedPrivateKeyHex = priv" in text
    assert "localStorage.setItem('private" not in text
    assert "localStorage.setItem(\"private" not in text
    assert "sessionStorage.setItem('thr_auth_secret'" not in text
    assert 'sessionStorage.setItem("thr_auth_secret"' not in text


def test_music_uses_active_migrated_wallet_address_for_music_state():
    music = (ROOT / "templates" / "music.html").read_text(encoding="utf-8")
    assert "ws.getActiveAddress" in music
    assert "m.new_v1_address" in music
