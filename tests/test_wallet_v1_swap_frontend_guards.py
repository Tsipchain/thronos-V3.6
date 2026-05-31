from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWAP_HTML = (ROOT / "templates/swap.html").read_text()


def test_swap_uses_migrated_active_wallet_for_balance_fetch():
    assert "function getSwapActiveWalletAddress()" in SWAP_HTML
    assert "window.getActiveWalletAddress" in SWAP_HTML
    assert "window.walletSession.getActiveAddress" in SWAP_HTML
    assert "window.walletSession.getAddress" in SWAP_HTML
    assert "localStorage.getItem('thr_address') || ''" in SWAP_HTML
    assert "/api/balances?address=${encodeURIComponent(addr)}&show_zero=true" in SWAP_HTML


def test_swap_parses_tokens_array_and_native_balance_shapes():
    assert "function normalizeSwapBalances(data)" in SWAP_HTML
    assert "Array.isArray(data.tokens)" in SWAP_HTML
    assert "token.balance ?? token.amount ?? token.value" in SWAP_HTML
    assert "['balances', 'token_balances', 'tokens_by_symbol']" in SWAP_HTML
    assert "data.THR ?? data.thr ?? data.balance" in SWAP_HTML
    assert "data.WBTC ?? data.wbtc" in SWAP_HTML
    assert "data.L2E ?? data.l2e" in SWAP_HTML


def test_swap_known_live_custom_symbols_are_normalized_for_display():
    for symbol in ("THR", "WBTC", "L2E", "JAM", "LOUMIDIS", "HPENNIS", "CVT", "7CEB", "MAR"):
        assert symbol in SWAP_HTML
    assert "normalizeSwapSymbol" in SWAP_HTML
    assert "$('balanceFrom').textContent = fromBal.toFixed(6)" in SWAP_HTML
    assert "$('balanceTo').textContent = toBal.toFixed(6)" in SWAP_HTML


def test_swap_button_uses_parsed_v1_balance_state():
    assert "function refreshSwapButtonState()" in SWAP_HTML
    assert "const fromBalance = swapTokenBalances[tokenIn] || 0" in SWAP_HTML
    assert "fromBalance >= amount" in SWAP_HTML
    assert "Insufficient ${tokenIn} balance" in SWAP_HTML


def test_swap_auth_uses_wallet_auth_signing_wrapper():
    assert "window.WalletAuth.requireUnlockedWallet({ source: 'swap' })" in SWAP_HTML
    assert "auth.address || activeAddress" in SWAP_HTML
    assert "credential_lookup_address: auth.credentialLookupAddress || addr" in SWAP_HTML
    assert "auth.getPublicKey ? auth.getPublicKey() : ''" in SWAP_HTML
    assert "auth.signTransaction ? await auth.signTransaction(txCore) : null" in SWAP_HTML
    assert "signed_tx: signedSwapEnvelope" in SWAP_HTML
    assert "signature: typeof signedSwap === 'string' ? signedSwap : signedSwap && signedSwap.signature" in SWAP_HTML
    assert "action: 'swap'" in SWAP_HTML
    assert "option: 'swap'" in SWAP_HTML
    assert "active_wallet_address: addr" in SWAP_HTML
    assert "missing_wallet_signing_material" in SWAP_HTML


def test_swap_does_not_use_legacy_hmac_session_helpers_in_action_path():
    assert "walletSession.requirePin('swap')" not in SWAP_HTML
    assert "walletSession.getSendSeed()" not in SWAP_HTML
    # localStorage thr_address is allowed only inside the resolver fallback.
    assert SWAP_HTML.count("localStorage.getItem('thr_address')") == 1


def test_swap_payload_posts_execute_with_action_option_and_signed_swap_action():
    assert "fetch('/api/swap/execute'" in SWAP_HTML
    assert "action: 'swap'" in SWAP_HTML
    assert "option: 'swap'" in SWAP_HTML
    assert "type: 'swap'" in SWAP_HTML
    assert "signed_tx: signedSwapEnvelope" in SWAP_HTML


def test_wallet_session_signing_falls_back_when_der_option_unsupported():
    session = (ROOT / "static/wallet_session.js").read_text()
    assert "function signDigestDerHex" in session
    assert "option not supported" in session
    assert "normalizeSignatureToDerHex(await secp.sign(digestHex, privateKeyHex))" in session


def test_swap_legacy_helper_uses_swap_source_and_crypto_error_is_specific():
    assert "WalletAuth.requireUnlockedWallet({ source: 'swap' })" in SWAP_HTML
    session = (ROOT / "static/wallet_session.js").read_text()
    assert "wallet_crypto_not_ready" in session


def test_swap_wallet_ui_handler_is_defined_and_event_calls_are_guarded():
    handler_pos = SWAP_HTML.index("function updateSwapWalletUI()")
    unlocked_listener_pos = SWAP_HTML.index("thronos:wallet:v1:unlocked")
    state_listener_pos = SWAP_HTML.index("thronos:wallet:state-changed")
    assert handler_pos < unlocked_listener_pos
    assert handler_pos < state_listener_pos
    assert "if (typeof updateSwapWalletUI === 'function') updateSwapWalletUI();" in SWAP_HTML


def test_swap_crypto_error_is_not_raw_sha256async_typeerror():
    session = (ROOT / "static/wallet_session.js").read_text()
    assert "Cannot read properties of undefined" in session
    assert "wallet_crypto_not_ready" in session
    assert "fetch('/api/swap/execute'" in SWAP_HTML
