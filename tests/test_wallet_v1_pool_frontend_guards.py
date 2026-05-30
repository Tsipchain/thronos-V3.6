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


def test_pool_no_duplicate_require_wallet_auth_definitions():
    """Verify only one requirePoolWalletAuth function definition exists."""
    count = POOLS_HTML.count("async function requirePoolWalletAuth(")
    assert count == 1, f"Expected 1 requirePoolWalletAuth definition, found {count}"


def test_create_pool_uses_correct_action_string():
    """Verify submitCreatePool uses 'create_pool' (underscore), not 'create pool' (space)."""
    create_start = POOLS_HTML.find("async function submitCreatePool")
    create_end = POOLS_HTML.find("\n}", create_start + 100)
    create_code = POOLS_HTML[create_start:create_end]

    assert "requirePoolWalletAuth('create_pool'" in create_code, \
        "submitCreatePool must use 'create_pool' with underscore"
    assert "action: 'create_pool'" in create_code, \
        "submitCreatePool payload must include action: 'create_pool'"
    # Ensure no duplicate calls with wrong action string
    assert "requirePoolWalletAuth('create pool'" not in create_code, \
        "submitCreatePool must not use 'create pool' with space"


def test_add_liquidity_uses_correct_action_string():
    """Verify addLiquidity uses 'add_liquidity' (underscore), not 'add liquidity' (space)."""
    add_start = POOLS_HTML.find("async function addLiquidity")
    add_end = POOLS_HTML.find("\n}", add_start + 100)
    add_code = POOLS_HTML[add_start:add_end]

    assert "requirePoolWalletAuth('add_liquidity'" in add_code, \
        "addLiquidity must use 'add_liquidity' with underscore"
    assert "action: 'add_liquidity'" in add_code, \
        "addLiquidity payload must include action: 'add_liquidity'"
    # Ensure no duplicate calls with wrong action string
    assert "requirePoolWalletAuth('add liquidity'" not in add_code, \
        "addLiquidity must not use 'add liquidity' with space"


def test_remove_liquidity_uses_correct_action_string():
    """Verify removeLiquidity uses 'remove_liquidity' (underscore), not 'remove liquidity' (space)."""
    remove_start = POOLS_HTML.find("async function removeLiquidity")
    remove_end = POOLS_HTML.find("\n}", remove_start + 100)
    remove_code = POOLS_HTML[remove_start:remove_end]

    assert "requirePoolWalletAuth('remove_liquidity'" in remove_code, \
        "removeLiquidity must use 'remove_liquidity' with underscore"
    # Ensure no duplicate calls with wrong action string
    assert "requirePoolWalletAuth('remove liquidity'" not in remove_code, \
        "removeLiquidity must not use 'remove liquidity' with space"


def test_pool_signed_action_payloads_include_required_fields():
    """Verify create, add, remove pool payloads include public_key, signature, signed_tx, credential_lookup_address."""
    # Create pool payload
    assert "public_key: poolAuth.publicKey" in POOLS_HTML or "public_key: poolAuth.getPublicKey()" in POOLS_HTML
    assert "signature: poolAuth.signature" in POOLS_HTML
    assert "signed_tx: poolAuth.signedTx" in POOLS_HTML
    assert "credential_lookup_address: poolAuth.credentialLookupAddress" in POOLS_HTML


def test_pool_diagnostics_log_action_and_endpoint():
    """Verify pool actions log diagnostics with action string and endpoint (no secrets)."""
    assert "[CreatePool] Diagnostics:" in POOLS_HTML
    assert "[AddLiquidity] Diagnostics:" in POOLS_HTML
    assert "[RemoveLiquidity] Diagnostics:" in POOLS_HTML
    assert "action: 'create_pool'" in POOLS_HTML
    assert "action: 'add_liquidity'" in POOLS_HTML
    assert "action: 'remove_liquidity'" in POOLS_HTML


def test_pool_diagnostics_do_not_expose_secrets():
    """Verify diagnostics don't log plaintext secrets, PIN, or auth_secret."""
    # Extract all console.log calls with 'Diagnostics'
    diag_start = POOLS_HTML.find("'[CreatePool] Diagnostics'")
    diag_end = POOLS_HTML.find("});", diag_start) + 3
    diag_section = POOLS_HTML[diag_start:diag_end]

    assert "authSecret" not in diag_section, "Diagnostics must not expose authSecret"
    assert "pin" not in diag_section.lower(), "Diagnostics must not expose PIN"
    assert "send_seed" not in diag_section, "Diagnostics must not expose seed"


def test_static_wallet_files_synchronized():
    """Verify static/wallet_auth.js matches public/static/wallet_auth.js."""
    static_auth = (ROOT / "static/wallet_auth.js").read_text()
    public_static_auth = (ROOT / "public/static/wallet_auth.js").read_text()
    assert static_auth == public_static_auth, \
        "static/wallet_auth.js must match public/static/wallet_auth.js"


def test_static_wallet_session_synchronized():
    """Verify static/wallet_session.js matches public/static/wallet_session.js."""
    static_session = (ROOT / "static/wallet_session.js").read_text()
    public_static_session = (ROOT / "public/static/wallet_session.js").read_text()
    assert static_session == public_static_session, \
        "static/wallet_session.js must match public/static/wallet_session.js"
