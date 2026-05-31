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
