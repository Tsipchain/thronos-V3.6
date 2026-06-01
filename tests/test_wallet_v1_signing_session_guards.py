"""Guards for Wallet V1 runtime signing session sharing across header, swap and pools."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_AUTH = (ROOT / "static/wallet_auth.js").read_text()
PUBLIC_AUTH = (ROOT / "public/static/wallet_auth.js").read_text()
STATIC_SESSION = (ROOT / "static/wallet_session.js").read_text()
PUBLIC_SESSION = (ROOT / "public/static/wallet_session.js").read_text()
SWAP_HTML = (ROOT / "templates/swap.html").read_text()
POOLS_HTML = (ROOT / "templates/pools.html").read_text()
CANONICAL = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"
UI_CREATED = "THRE85A3E0A09A57212CDB222A9BF5B6E07A9B820E4"
SYSTEM = "THR5DF27A86C477F381594E896F0E55357DEC5942BA"


def run_wallet_session(script_body: str):
    harness = f"""
const assert = require('assert');
const store = new Map();
global.localStorage = {{
  getItem(key) {{ return store.has(key) ? store.get(key) : null; }},
  setItem(key, value) {{ store.set(key, String(value)); }},
  removeItem(key) {{ store.delete(key); }},
}};
global.window = {{ localStorage: global.localStorage }};
{STATIC_SESSION}
const walletSession = window.walletSession;
{script_body}
console.log(JSON.stringify({{ ok: true }}));
"""
    result = subprocess.run(["node", "-e", harness], cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_header_unlock_event_populates_walletauth_runtime_cache_guard():
    assert "thronos:wallet:v1:unlocked" in STATIC_AUTH
    assert "cachedRuntimeSigningAddress = address" in STATIC_AUTH
    assert "logAuthDiagnostics(address, 'header')" in STATIC_AUTH


def test_swap_uses_shared_walletauth_unlock_source_and_runtime_guard():
    assert "window.WalletAuth.requireUnlockedWallet({ source: 'swap' })" in SWAP_HTML
    assert "wallet_locked_reunlock_required" in SWAP_HTML
    assert "if (!signedSwap) throw new Error('wallet_locked_reunlock_required')" in SWAP_HTML


def test_pools_use_shared_walletauth_unlock_source_and_runtime_guard():
    assert "window.WalletAuth.requireUnlockedWallet({ source: 'pools' })" in POOLS_HTML
    assert "wallet_locked_reunlock_required" in POOLS_HTML
    assert "if (!signedTx) throw new Error('wallet_locked_reunlock_required')" in POOLS_HTML


def test_walletauth_prefers_runtime_signing_material_without_legacy_secret():
    runtime_pos = STATIC_AUTH.index("if (hasRuntimeSigningMaterial(address))")
    legacy_pos = STATIC_AUTH.index("const storedSecret = getSigningMaterial(address)")
    assert runtime_pos < legacy_pos
    assert "return buildAuthResult(address, '', credentialLookupAddress)" in STATIC_AUTH


def test_walletauth_auto_lock_clears_runtime_cache_and_session_runtime_only():
    assert "cachedRuntimeSigningAddress = ''" in STATIC_AUTH
    assert "window.walletSession.lockWallet()" in STATIC_AUTH
    run_wallet_session(f"""
localStorage.setItem('wallet_v1_address', {json.dumps(CANONICAL)});
localStorage.setItem('thr_address', {json.dumps(CANONICAL)});
walletSession.setBound(true);
walletSession.lockWallet();
assert.strictEqual(walletSession.getActiveAddress(), {json.dumps(CANONICAL)});
assert.strictEqual(walletSession.isBound(), true);
assert.strictEqual(walletSession.isLocked(), true);
assert.strictEqual(walletSession.hasRuntimeSigningMaterial({json.dumps(CANONICAL)}), false);
""")


def test_walletauth_reunlock_error_is_clear_not_missing_material():
    assert "function walletLockedRelockRequiredError()" in STATIC_AUTH
    assert "new Error('wallet_locked_reunlock_required')" in STATIC_AUTH
    assert "throw walletLockedRelockRequiredError()" in STATIC_AUTH


def test_walletauth_safe_diagnostics_have_required_fields_and_no_secrets():
    for content in [STATIC_AUTH, PUBLIC_AUTH]:
        assert "active_address_short" in content
        assert "has_encrypted_seed" in content
        assert "has_runtime_signing_material" in content
        assert "is_locked" in content
        assert "source: source" in content
        diag_start = content.index("console.info('[WalletAuth]'" )
        diag_block = content[diag_start:content.index("});", diag_start)]
        forbidden = ["privateKey", "private_key", "auth_secret", "send_secret", "sendSeed", "PIN", "pin:"]
        assert not any(secret in diag_block for secret in forbidden)


def test_reunlock_restores_signing_for_same_canonical_address_guard():
    assert "const ok = await window.walletSession.unlockWallet({ pin, address })" in STATIC_AUTH
    assert "if (hasRuntimeSigningMaterial(address))" in STATIC_AUTH
    assert "cachedRuntimeSigningAddress = address" in STATIC_AUTH


def test_canonical_migrated_address_cannot_be_replaced_by_ui_created_wallet():
    meta = json.dumps({
        "old_address": "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a",
        "new_v1_address": CANONICAL,
        "migration_tx_id": "proof",
        "migrated_at": "2026-05-31T00:00:00Z",
    })
    run_wallet_session(f"""
localStorage.setItem('wallet_v1_migration_meta', {json.dumps(meta)});
localStorage.setItem('wallet_v1_address', {json.dumps(UI_CREATED)});
assert.strictEqual(walletSession.persistActiveUserAddress({json.dumps(UI_CREATED)}), {json.dumps(CANONICAL)});
assert.strictEqual(walletSession.getActiveAddress(), {json.dumps(CANONICAL)});
""")


def test_system_wallet_remains_blocked():
    run_wallet_session(f"""
assert.strictEqual(walletSession.isSystemWalletAddress({json.dumps(SYSTEM)}), true);
try {{ walletSession.persistActiveUserAddress({json.dumps(SYSTEM)}); assert.fail('should reject'); }}
catch (err) {{ assert.strictEqual(err.message, 'system_wallet_not_allowed'); }}
""")


def test_static_and_public_wallet_files_stay_synchronized():
    assert STATIC_AUTH == PUBLIC_AUTH
    assert STATIC_SESSION == PUBLIC_SESSION


def test_signing_key_mismatch_displays_safe_diagnostics():
    assert "getSigningKeyMismatch" in STATIC_SESSION
    assert "derived_address" in STATIC_SESSION
    assert "active_address" in STATIC_SESSION
    assert "lastSigningKeyMismatch" in STATIC_SESSION
    # Ensure error handler captures mismatch details
    assert "lastMismatchError" in STATIC_AUTH
    assert "getSigningKeyMismatchDetails" in STATIC_AUTH


def test_signing_key_mismatch_preserves_active_canonical_address():
    assert "activeNormalized && derivedNormalized && activeNormalized !== derivedNormalized" in STATIC_SESSION
    assert "wallet_signing_address_mismatch" in STATIC_SESSION
    # Active address should not be cleared on mismatch
    assert "unlockedForAddress = null" in STATIC_SESSION


def test_signing_key_mismatch_clears_runtime_signing_material():
    assert "unlockedPrivateKeyHex = null" in STATIC_SESSION
    # Should clear on mismatch catch
    assert "if ((err.message || '').includes('wallet_signing_address_mismatch')) {" in STATIC_SESSION


def test_clear_local_signing_key_removes_encrypted_seed_but_keeps_active_address():
    assert "clearLocalSigningKey" in STATIC_SESSION
    assert "localStorage.removeItem(V1_ENCRYPTED_KEY)" in STATIC_SESSION
    assert "localStorage.removeItem(V1_PUBLIC_KEY)" in STATIC_SESSION
    assert "localStorage.removeItem(PIN_KEY)" in STATIC_SESSION
    # Should NOT remove active address keys
    assert "clearLocalSigningKey" in STATIC_SESSION


def test_import_correct_key_only_succeeds_if_derived_address_matches_active():
    assert "importSigningKeyForAddress" in STATIC_SESSION
    assert "derivedNormalized !== normalized" in STATIC_SESSION
    assert "Imported key derives" in STATIC_SESSION


def test_import_wrong_key_is_rejected():
    assert "if (derivedNormalized !== normalized)" in STATIC_SESSION
    assert "success: false, error:" in STATIC_SESSION


def test_system_wallet_cannot_have_imported_signing_key():
    assert "isSystemWalletAddress(normalized)" in STATIC_SESSION
    assert "Cannot import signing key for system wallet" in STATIC_SESSION


def test_mismatch_diagnostics_do_not_leak_secrets():
    for content in [STATIC_SESSION]:
        # Search for error handling and mismatch details
        if "lastSigningKeyMismatch" in content:
            mismatch_start = content.index("lastSigningKeyMismatch")
            # Make sure only non-secret fields are stored
            forbidden = ["privateKey", "private_key", "pin", "PIN", "send_secret", "sendSeed"]
            mismatch_section = content[mismatch_start:mismatch_start + 500]
            assert not any(secret in mismatch_section for secret in forbidden)
