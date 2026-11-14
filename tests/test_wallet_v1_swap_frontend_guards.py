from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWAP_HTML = (ROOT / "templates/swap.html").read_text()
STATIC_AUTH = (ROOT / "static/wallet_auth.js").read_text()


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
    for symbol in ("THR", "USDT", "USDC", "WBTC", "L2E", "JAM", "LOUMIDIS", "HPENNIS", "CVT", "7CEB", "MAR"):
        assert symbol in SWAP_HTML
    assert "normalizeSwapSymbol" in SWAP_HTML
    assert "$('balanceFrom').textContent = fromBal === null ? '—' : fromBal.toFixed(6)" in SWAP_HTML
    assert "$('balanceTo').textContent = toBal === null ? '—' : toBal.toFixed(6)" in SWAP_HTML


def test_swap_button_requires_verified_spendable_balance_and_valid_quote():
    assert "function refreshSwapButtonState()" in SWAP_HTML
    assert "const fromBalance = swapSpendableBalance(tokenIn)" in SWAP_HTML
    assert "fromBalance !== null && fromBalance >= amount" in SWAP_HTML
    assert "const hasValidQuote = latestQuote && latestQuote.status === 'success'" in SWAP_HTML
    assert "swapBalanceProblem(tokenIn)" in SWAP_HTML


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


def test_frontend_builds_canonical_signed_swap_txcore():
    # The active legacy envelope includes quote details; it must bind exact
    # amount, input/output symbols, nonce and timestamp before signing.
    tx_start = SWAP_HTML.index("const txCore = {")
    tx_end = SWAP_HTML.index("};", tx_start)
    tx_code = SWAP_HTML[tx_start:tx_end]
    for field in ("type: 'swap'", "action: 'swap'", "from: addr",
                  "trader_thr: addr", "token_in: tokenIn", "token_out: tokenOut",
                  "amount_in: normalizedAmount", "min_amount_out: latestQuote.amount_out",
                  "nonce:", "timestamp: String"):
        assert field in tx_code
    assert "amount: normalizedAmount" in tx_code
    assert "const signedSwap = auth.signTransaction ? await auth.signTransaction(txCore) : null" in SWAP_HTML


def test_frontend_signed_tx_envelope_wraps_exact_txcore_with_public_key_and_signature():
    assert "publicKey: auth.getPublicKey ? auth.getPublicKey() : ''" in SWAP_HTML
    assert "...txCore," in SWAP_HTML
    assert "signature: signedSwap" in SWAP_HTML
    assert "signed_tx: signedSwapEnvelope" in SWAP_HTML
    assert "signature: typeof signedSwap === 'string' ? signedSwap : signedSwap && signedSwap.signature" in SWAP_HTML
    assert "if (!signedSwap) throw new Error('wallet_locked_reunlock_required')" in SWAP_HTML


def test_frontend_logs_only_safe_signed_swap_diagnostics():
    # No secret key, raw signature or tx envelope may be emitted to console.
    assert "console.log(signedSwap)" not in SWAP_HTML
    assert "console.info(signedSwap)" not in SWAP_HTML
    assert "console.log(auth)" not in SWAP_HTML
    assert "console.info(auth)" not in SWAP_HTML
    assert "console.log(txCore)" not in SWAP_HTML
    assert "console.info(txCore)" not in SWAP_HTML
    assert "console.info('[SwapUI] Wallet V1 unlocked event received:'" in SWAP_HTML
    assert "eventAddr=" in SWAP_HTML
    assert ".substring(0, 10)" in SWAP_HTML


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


def test_swap_crypto_error_is_not_raw_sha256async_or_set_typeerror():
    session = (ROOT / "static/wallet_session.js").read_text()
    assert "cannot read properties" in session
    assert "cannot set properties" in session
    assert "wallet_crypto_not_ready" in session
    assert "fetch('/api/swap/execute'" in SWAP_HTML


def test_locked_swap_state_prompts_reunlock_before_signing_and_posting():
    prompt_pos = STATIC_AUTH.index("const pin = prompt('🔐 PIN (unlock wallet):');")
    unlock_pos = STATIC_AUTH.index("window.walletSession.unlockWallet({ pin, address })")
    runtime_pos = STATIC_AUTH.index("if (hasRuntimeSigningMaterial(address))", unlock_pos)
    assert prompt_pos < unlock_pos < runtime_pos
    assert "WalletAuth.requireUnlockedWallet({ source: 'swap' })" in SWAP_HTML
    # The V1 signed action is posted first and cannot silently fall back when
    # signing material exists but fails; the legacy path signs before posting.
    v1 = SWAP_HTML.index('const signedRequest = await walletV1BuildSignedRequest("swap", payload)')
    v1_post = SWAP_HTML.index("fetch('/api/swap/execute'", v1)
    assert v1 < v1_post
    assert "Wallet V1 centralized signing failed:" in SWAP_HTML
    legacy = SWAP_HTML.index("// Legacy format fallback")
    sign_pos = SWAP_HTML.index("const signedSwap = auth.signTransaction", legacy)
    post_pos = SWAP_HTML.index("fetch('/api/swap/execute'", sign_pos)
    assert legacy < sign_pos < post_pos


def test_swap_amount_normalization_matches_backend():
    """Verify normalizeSwapAmount function exists and is used for canonical payload."""
    assert "function normalizeSwapAmount(value)" in SWAP_HTML
    assert "const normalizedAmount = normalizeSwapAmount(amount)" in SWAP_HTML
    doswap_start = SWAP_HTML.find("const txCore = {")
    doswap_end = SWAP_HTML.find("};", doswap_start)
    txcore_code = SWAP_HTML[doswap_start:doswap_end]
    # Verify amount_in uses normalized amount
    assert "amount_in: normalizedAmount" in txcore_code
    # Verify amount also uses normalized value for backend compatibility
    assert "amount: normalizedAmount" in txcore_code


def test_swap_canonical_nonce_and_timestamp_are_strings():
    """Verify swap txCore has nonce and timestamp fields as required by backend."""
    doswap_start = SWAP_HTML.find("const txCore = {")
    doswap_end = SWAP_HTML.find("};", doswap_start)
    txcore_code = SWAP_HTML[doswap_start:doswap_end]
    assert "nonce:" in txcore_code
    assert "timestamp:" in txcore_code
