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
