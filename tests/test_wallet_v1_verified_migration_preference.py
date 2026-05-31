"""
Regression tests for verified Wallet V1 migration precedence.

A verified legacy -> V1 migration must remain the canonical paid/whitelisted
identity even when a separate UI-created V1 wallet can unlock locally.
"""

import json
import subprocess
from pathlib import Path


LEGACY_SOURCE = "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a"
CANONICAL_V1 = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"
UI_CREATED_V1 = "THRE85A3E0A09A57212CDB222A9BF5B6E07A9B820E4"
SYSTEM_WALLET = "THR5DF27A86C477F381594E896F0E55357DEC5942BA"


def run_wallet_session_script(script_body: str):
    wallet_session = Path("static/wallet_session.js").read_text()
    harness = f"""
const assert = require('assert');
const store = new Map();
global.localStorage = {{
  getItem(key) {{ return store.has(key) ? store.get(key) : null; }},
  setItem(key, value) {{ store.set(key, String(value)); }},
  removeItem(key) {{ store.delete(key); }},
  clear() {{ store.clear(); }},
}};
global.window = {{ localStorage: global.localStorage }};
{wallet_session}
const walletSession = window.walletSession;
{script_body}
console.log(JSON.stringify({{ ok: true }}));
"""
    result = subprocess.run(["node", "-e", harness], text=True, capture_output=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def verified_migration_meta():
    return {
        "old_address": LEGACY_SOURCE,
        "new_v1_address": CANONICAL_V1,
        "migration_tx_id": "migration-proof-542",
        "migrated_at": "2026-05-31T00:00:00Z",
        "status": "completed",
    }


def test_thr79ca_maps_to_thr683318_when_migration_proof_exists():
    meta = json.dumps(verified_migration_meta())
    run_wallet_session_script(f"""
localStorage.setItem('wallet_v1_migration_meta', {json.dumps(meta)});
localStorage.setItem('thr_address', {json.dumps(LEGACY_SOURCE)});
assert.strictEqual(walletSession.getActiveAddress(), {json.dumps(CANONICAL_V1)});
const debug = walletSession.getDebugState();
assert.strictEqual(debug.legacy_source_address, {json.dumps(LEGACY_SOURCE)});
assert.strictEqual(debug.canonical_v1_address, {json.dumps(CANONICAL_V1)});
assert.strictEqual(debug.wallet_origin, 'migrated');
""")


def test_thre85_remains_ui_created_empty_without_verified_migration():
    run_wallet_session_script(f"""
localStorage.setItem('wallet_v1_address', {json.dumps(UI_CREATED_V1)});
localStorage.setItem('thr_address', {json.dumps(UI_CREATED_V1)});
assert.strictEqual(walletSession.getActiveAddress(), {json.dumps(UI_CREATED_V1)});
const debug = walletSession.getDebugState();
assert.strictEqual(debug.canonical_v1_address, '');
assert.strictEqual(debug.wallet_origin, 'ui_created');
assert.strictEqual(debug.wallet_identity_status, 'ui_created_empty');
""")


def test_thr5df_remains_blocked_as_system_wallet():
    run_wallet_session_script(f"""
localStorage.setItem('wallet_v1_address', {json.dumps(SYSTEM_WALLET)});
localStorage.setItem('thr_address', {json.dumps(SYSTEM_WALLET)});
assert.strictEqual(walletSession.isSystemWalletAddress({json.dumps(SYSTEM_WALLET)}), true);
assert.strictEqual(walletSession.getActiveAddress(), '');
assert.strictEqual(walletSession.getWalletOrigin({json.dumps(SYSTEM_WALLET)}), 'system');
const debug = walletSession.getDebugState();
assert.strictEqual(debug.ignored_system_wallet, true);
""")


def test_ui_created_v1_cannot_override_verified_migrated_v1():
    meta = json.dumps(verified_migration_meta())
    run_wallet_session_script(f"""
localStorage.setItem('wallet_v1_migration_meta', {json.dumps(meta)});
localStorage.setItem('wallet_v1_address', {json.dumps(UI_CREATED_V1)});
localStorage.setItem('thr_address', {json.dumps(UI_CREATED_V1)});
assert.strictEqual(walletSession.getActiveAddress(), {json.dumps(CANONICAL_V1)});
const persisted = walletSession.persistActiveUserAddress({json.dumps(UI_CREATED_V1)});
assert.strictEqual(persisted, {json.dumps(CANONICAL_V1)});
assert.strictEqual(localStorage.getItem('wallet_v1_address'), {json.dumps(CANONICAL_V1)});
assert.strictEqual(localStorage.getItem('thr_address'), {json.dumps(CANONICAL_V1)});
assert.strictEqual(walletSession.getActiveAddress(), {json.dumps(CANONICAL_V1)});
assert.strictEqual(walletSession.getDebugState().wallet_origin, 'migrated');
""")


def test_required_canonical_addresses_are_present_in_both_bundles():
    for path in ["static/wallet_session.js", "public/static/wallet_session.js"]:
        content = Path(path).read_text()
        assert LEGACY_SOURCE in content
        assert CANONICAL_V1 in content
        assert SYSTEM_WALLET in content
