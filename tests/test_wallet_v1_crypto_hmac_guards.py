"""Guards for Wallet V1 secp256k1 crypto helper setup and signing errors."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_SESSION = (ROOT / "static/wallet_session.js").read_text()
PUBLIC_SESSION = (ROOT / "public/static/wallet_session.js").read_text()
STATIC_AUTH = (ROOT / "static/wallet_auth.js").read_text()
PUBLIC_AUTH = (ROOT / "public/static/wallet_auth.js").read_text()
SWAP_HTML = (ROOT / "templates/swap.html").read_text()
POOLS_HTML = (ROOT / "templates/pools.html").read_text()


def test_vendor_loader_uses_noble_secp256k1_v223():
    vendor = (ROOT / "static/vendor/noble-secp256k1.min.js").read_text()
    assert "@noble/secp256k1@2.2.3" in vendor
    assert "__nobleSecp256k1Ready" in vendor


def test_secp_async_crypto_helpers_are_configured_in_both_session_bundles():
    for content in (STATIC_SESSION, PUBLIC_SESSION):
        assert "function ensureSecpAsyncCrypto(secp)" in content
        assert "secp.etc.sha256Async" in content
        assert "secp.etc.hmacSha256Async" in content
        assert "secp.hashes.sha256Async" in content
        assert "secp.hashes.hmacSha256Async" in content
        assert "crypto.subtle.importKey('raw'" in content
        assert "crypto.subtle.sign('HMAC'" in content


def test_signing_prefers_async_signing_and_normalizes_der_hex():
    for content in (STATIC_SESSION, PUBLIC_SESSION):
        assert "typeof secp.signAsync === 'function'" in content
        assert "normalizeSignatureToDerHex(await secp.signAsync" in content
        assert "function derEncodeCompactSignature" in content
        assert "function normalizeSignatureToDerHex" in content


def test_sign_digest_does_not_surface_option_or_hmac_errors():
    for content in (STATIC_SESSION, PUBLIC_SESSION):
        assert "function isSecpCryptoHelperError" in content
        assert "option not supported" in content
        assert "hmacsha256sync" in content
        assert "sha256sync" in content
        assert "throw new Error('wallet_crypto_not_ready')" in content


def test_wallet_auth_autolock_wrapper_preserves_source_options_for_pools_and_swap():
    for content in (STATIC_AUTH, PUBLIC_AUTH):
        assert "WalletAuth.requireUnlockedWallet = async function(options = {})" in content
        assert "originalRequire.call(this, options)" in content
    assert "WalletAuth.requireUnlockedWallet({ source: 'swap' })" in SWAP_HTML
    assert "window.WalletAuth.requireUnlockedWallet({ source: 'pools' })" in POOLS_HTML


def test_swap_signing_posts_execute_after_signed_envelope_is_created():
    sign_pos = SWAP_HTML.index("const signedSwap = auth.signTransaction")
    post_pos = SWAP_HTML.index("fetch('/api/swap/execute'")
    assert sign_pos < post_pos
    assert "signed_tx: signedSwapEnvelope" in SWAP_HTML
    assert "action: 'swap'" in SWAP_HTML
    assert "option: 'swap'" in SWAP_HTML


def test_no_secret_values_are_logged_by_crypto_or_auth_diagnostics():
    for content in (STATIC_SESSION, PUBLIC_SESSION, STATIC_AUTH, PUBLIC_AUTH):
        diagnostics = "\n".join(line for line in content.splitlines() if "console." in line or "[WalletAuth]" in line)
        forbidden = ["privateKey", "private_key", "auth_secret", "send_secret", "signature", "pin:", "PIN:"]
        assert not any(secret in diagnostics for secret in forbidden)
