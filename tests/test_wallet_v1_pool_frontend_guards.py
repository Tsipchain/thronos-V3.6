from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOLS_HTML = (ROOT / "templates/pools.html").read_text()


def test_pool_actions_use_active_migrated_wallet_resolver():
    assert "function getPoolActiveWalletAddress()" in POOLS_HTML
    assert "window.getActiveWalletAddress" in POOLS_HTML
    assert "window.walletSession.getActiveAddress" in POOLS_HTML
    assert "window.walletSession.getAddress" in POOLS_HTML
    assert "localStorage.getItem('thr_address') || ''" in POOLS_HTML
    assert "const provider = getPoolActiveWalletAddress()" in POOLS_HTML
    assert "const wallet = getPoolActiveWalletAddress()" in POOLS_HTML


def test_pool_liquidity_actions_use_wallet_auth_signing_wrapper():
    assert "async function requirePoolWalletAuth" in POOLS_HTML
    assert "window.WalletAuth.requireUnlockedWallet()" in POOLS_HTML
    assert "auth.signTransaction ? await auth.signTransaction" in POOLS_HTML
    assert "auth.getPublicKey ? auth.getPublicKey() : ''" in POOLS_HTML
    assert "credential_lookup_address" in POOLS_HTML
    assert "signed_tx" in POOLS_HTML
    assert "signature" in POOLS_HTML


def test_pool_actions_do_not_use_legacy_pin_or_raw_send_seed():
    assert "walletSession.requirePin('create pool')" not in POOLS_HTML
    assert "walletSession.requirePin('add liquidity')" not in POOLS_HTML
    assert "walletSession.requirePin('remove liquidity')" not in POOLS_HTML
    assert "walletSession.getSendSeed()" not in POOLS_HTML
