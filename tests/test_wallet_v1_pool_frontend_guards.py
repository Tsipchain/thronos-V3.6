from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOLS = ROOT / "templates" / "pools.html"


def _pools() -> str:
    return POOLS.read_text(encoding="utf-8")


def test_pools_remove_legacy_secret_prompt_and_pin_paths():
    text = _pools()
    assert "prompt('Enter your auth secret:')" not in text
    assert 'prompt("Enter your auth secret:")' not in text
    assert "walletSession.getSendSeed()" not in text
    assert "walletSession.requirePin('create pool')" not in text
    assert "walletSession.requirePin('add liquidity')" not in text
    assert "walletSession.requirePin('remove liquidity')" not in text


def test_pools_use_active_wallet_resolver_and_wallet_auth():
    text = _pools()
    assert "function getPoolActiveWalletAddress()" in text
    assert "window.getActiveWalletAddress" in text
    assert "walletSession.getActiveAddress" in text
    assert "walletSession.getAddress" in text
    assert "localStorage.getItem('thr_address')" in text
    assert "async function requirePoolWalletAuth(action, txCore)" in text
    assert "WalletAuth.requireUnlockedWallet()" in text


def test_pools_send_v1_signed_auth_fields():
    text = _pools()
    for field in [
        "provider_thr",
        "credential_lookup_address",
        "public_key",
        "signed_tx",
        "signature",
        "auth_secret",
    ]:
        assert field in text
