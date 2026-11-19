"""Real-browser Wallet V1 recovery and signing acceptance.

The harness serves the production wallet session script and the recovery
functions extracted verbatim from base.html. It uses an in-memory nonce store
and synthetic transactions only; no ledger or broadcaster is reachable.
"""

from __future__ import annotations

import threading
import os
import shutil
from pathlib import Path

import pytest
from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.serving import make_server

from wallet_v1_production_final import (
    derive_thronos_address,
    verify_ecdsa_signature,
    verify_publickey_matches_address,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates" / "base.html").read_text()


def _extract_function(name: str) -> str:
    """Extract one top-level JS function, respecting strings and comments."""
    markers = (f"async function {name}", f"function {name}")
    start = next((TEMPLATE.find(marker) for marker in markers if TEMPLATE.find(marker) >= 0), -1)
    if start < 0:
        raise AssertionError(f"production function not found: {name}")
    brace = TEMPLATE.find("{", start)
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    index = brace
    while index < len(TEMPLATE):
        char = TEMPLATE[index]
        nxt = TEMPLATE[index + 1] if index + 1 < len(TEMPLATE) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char == "/" and nxt == "/":
            line_comment = True
            index += 1
        elif char == "/" and nxt == "*":
            block_comment = True
            index += 1
        elif char in ("'", '"', "`"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return TEMPLATE[start : index + 1]
        index += 1
    raise AssertionError(f"unterminated production function: {name}")


RECOVERY_JS = "\n".join(
    _extract_function(name)
    for name in (
        "isValidSecp256k1PublicKeyHex",
        "walletV1DetectMissingSigningKeyState",
        "walletV1ShowRecoveryKitRestorePrimary",
        "walletV1ShowAdvancedRecovery",
        "walletV1RestoreFromRecoveryKit",
        "walletV1HandleRecoveryKitRestore",
    )
)


HARNESS_HTML = f"""<!doctype html>
<meta charset="utf-8">
<h5>Wallet Recovery</h5>
<div id="walletV1ImportMode">
  <div id="walletV1RecoveryKitRestoreForm" style="display:none">
    <input type="file" id="walletV1RecoveryKitFileInput">
    <textarea id="walletV1RecoveryKitPasteInput"></textarea>
    <input id="walletV1RecoveryKitPin" type="password">
    <div id="walletV1RecoveryKitStatus"></div>
  </div>
  <button id="walletV1AdvancedRecoveryToggle" aria-controls="walletV1AdvancedRecoveryDetails"
          aria-expanded="false" onclick="walletV1ShowAdvancedRecovery()">Advanced Options</button>
  <details id="walletV1AdvancedRecoveryDetails" aria-label="walletV1AdvancedImport"><summary>Advanced</summary></details>
  <div id="walletV1LegacyRecoveryForm"></div>
  <div id="walletV1RekeyCeremonyForm"></div>
</div>
<script>window.updateHeaderWalletUi=()=>{{}}; window.refreshWalletStateFromServer=async()=>{{}}; window.switchWalletV1Mode=()=>{{}};</script>
<script src="/static/vendor/noble-secp256k1.min.js"></script>
<script src="/static/wallet_session.js"></script>
<script>{RECOVERY_JS}</script>
"""


@pytest.fixture(scope="module")
def wallet_browser_server():
    app = Flask(__name__, static_folder=None)
    used_nonces: set[str] = set()
    noble_module = Path(
        os.environ.get(
            "WALLET_E2E_NOBLE_MODULE",
            "/tmp/wallet-e2e-js/node_modules/@noble/secp256k1/index.js",
        )
    )
    if not noble_module.is_file():
        pytest.fail(
            "Browser E2E dependency missing; install @noble/secp256k1@2.2.3 "
            "and set WALLET_E2E_NOBLE_MODULE"
        )

    @app.get("/")
    def index():
        return HARNESS_HTML

    @app.get("/static/<path:filename>")
    def static_file(filename):
        if filename == "vendor/noble-secp256k1.min.js":
            loader = (ROOT / "static" / filename).read_text().replace(
                "https://cdn.jsdelivr.net/npm/@noble/secp256k1@2.2.3/+esm",
                "/test-vendor/secp256k1.js",
            )
            return Response(loader, mimetype="application/javascript")
        return send_from_directory(ROOT / "static", filename)

    @app.get("/test-vendor/secp256k1.js")
    def noble_secp256k1():
        return send_from_directory(noble_module.parent, noble_module.name)

    @app.post("/api/v1/address/derive")
    def derive():
        body = request.get_json(force=True)
        return jsonify(address=derive_thronos_address(body.get("public_key") or body["compressed_public_key"]))

    @app.get("/api/wallet/v1/key-binding/<address>")
    def no_binding(address):
        return jsonify(ok=True, binding=None)

    @app.get("/test/pledge/<address>")
    def pledge(address):
        return jsonify(verified=address.startswith("THR"), canonical_v1_address=address)

    @app.post("/test/verify")
    def verify():
        signed = request.get_json(force=True)
        identity_ok, identity_error = verify_publickey_matches_address(signed)
        signature_ok, signature_error = verify_ecdsa_signature(signed)
        if not identity_ok or not signature_ok:
            return jsonify(ok=False, error=identity_error or signature_error), 400
        nonce = str(signed.get("nonce") or "")
        if nonce in used_nonces:
            return jsonify(ok=False, error="duplicate_nonce"), 409
        used_nonces.add(nonce)
        return jsonify(ok=True, synthetic=True)

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def wallet_page(wallet_browser_server):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        executable = os.environ.get("WALLET_E2E_CHROMIUM") or shutil.which("chromium")
        launch_options = {"headless": True, "args": ["--no-sandbox"]}
        if executable:
            launch_options["executable_path"] = executable
        browser = runtime.chromium.launch(**launch_options)
        page = browser.new_page()
        page.goto(wallet_browser_server, wait_until="networkidle")
        page.evaluate("() => window.__nobleSecp256k1Ready")
        yield page
        browser.close()


def _make_kit(page, pin="2468"):
    return page.evaluate(
        """async ({pin}) => {
          const generated = await walletSession.generateV1KeyPair();
          if (!generated.success) throw new Error(generated.error);
          const encrypted = await walletSession.encryptPrivateKeyHex(generated.privateKey, pin);
          return {pin, privateKey: generated.privateKey, kit: {
            version: 'wallet-v1-recovery-kit',
            canonical_v1_address: generated.address,
            public_key: generated.publicKey,
            encrypted_private_key_backup: encrypted
          }};
        }""",
        {"pin": pin},
    )


def test_fresh_pledged_wallet_recovery_signing_and_replay(wallet_page):
    material = _make_kit(wallet_page)
    address = material["kit"]["canonical_v1_address"]
    pledge = wallet_page.evaluate("addr => fetch('/test/pledge/' + addr).then(r => r.json())", address)
    assert pledge == {"canonical_v1_address": address, "verified": True}

    result = wallet_page.evaluate(
        """async ({kit, pin}) => {
          localStorage.clear();
          localStorage.setItem('wallet_v1_address', kit.canonical_v1_address);
          walletV1ShowRecoveryKitRestorePrimary();
          walletV1ShowAdvancedRecovery();
          const advancedOpen = document.querySelector('#walletV1AdvancedRecoveryDetails').open;
          const expanded = document.querySelector('#walletV1AdvancedRecoveryToggle').getAttribute('aria-expanded');
          const restored = await walletV1RestoreFromRecoveryKit(kit, pin);
          const tx = {from: kit.canonical_v1_address, to: 'THR_SYNTHETIC_DESTINATION_00000001', amount: '1', token: 'THR', nonce: 'browser-fresh-1', timestamp: 1700000000};
          const signature = await walletSession.signTransaction(tx);
          const signed = {...tx, signature, publicKey: kit.public_key};
          const first = await fetch('/test/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(signed)});
          const replay = await fetch('/test/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(signed)});
          return {restored, advancedOpen, expanded, unlocked: walletSession.isUnlockedFor(kit.canonical_v1_address), first: first.status, replay: replay.status};
        }""",
        material,
    )
    assert result["restored"]["success"] is True
    assert result["advancedOpen"] is True
    assert result["expanded"] == "true"
    assert result["unlocked"] is True
    assert result["first"] == 200
    assert result["replay"] == 409


def test_wrong_pin_wrong_kit_and_signing_key_mismatch_fail_closed(wallet_page):
    first = _make_kit(wallet_page, "2468")
    second = _make_kit(wallet_page, "1357")
    result = wallet_page.evaluate(
        """async ({first, second}) => {
          localStorage.clear();
          localStorage.setItem('wallet_v1_address', first.kit.canonical_v1_address);
          const original = localStorage.getItem('wallet_v1_address');
          const errors = [];
          try { await walletV1RestoreFromRecoveryKit(first.kit, '0000'); } catch (e) { errors.push(e.message); }
          const malformed = {...first.kit, encrypted_private_key_backup: '{not-json'};
          try { await walletV1RestoreFromRecoveryKit(malformed, first.pin); } catch (e) { errors.push(e.message); }
          const mismatched = {...first.kit, public_key: second.kit.public_key};
          try { await walletV1RestoreFromRecoveryKit(mismatched, first.pin); } catch (e) { errors.push(e.message); }
          return {errors, identity: localStorage.getItem('wallet_v1_address'), encrypted: localStorage.getItem('wallet_v1_encrypted_priv'), original};
        }""",
        {"first": first, "second": second},
    )
    assert len(result["errors"]) == 3
    assert result["identity"] == result["original"]
    assert result["encrypted"] is None


def test_reload_expiry_cancelled_signing_and_legacy_access(wallet_page):
    material = _make_kit(wallet_page)
    preserved = wallet_page.evaluate(
        """async ({kit, pin}) => {
          localStorage.clear();
          localStorage.setItem('wallet_v1_address', kit.canonical_v1_address);
          localStorage.setItem('wallet_v1_migration_meta', JSON.stringify({status:'verified', legacy:'preserve'}));
          localStorage.setItem('send_seed', 'synthetic-legacy-seed');
          localStorage.setItem('send_secret', 'synthetic-legacy-secret');
          await walletV1RestoreFromRecoveryKit(kit, pin);
          walletSession.lockWallet();
          let expiryError = '';
          try { await walletSession.signTransaction({from:kit.canonical_v1_address, nonce:'expired'}); } catch (e) { expiryError = e.message; }
          return {expiryError, migration: localStorage.getItem('wallet_v1_migration_meta'), seed: localStorage.getItem('send_seed'), secret: localStorage.getItem('send_secret')};
        }""",
        material,
    )
    assert preserved["expiryError"] == "wallet_locked"
    assert '"legacy":"preserve"' in preserved["migration"]
    assert preserved["seed"] == "synthetic-legacy-seed"
    assert preserved["secret"] == "synthetic-legacy-secret"

    wallet_page.reload(wait_until="networkidle")
    wallet_page.evaluate("() => window.__nobleSecp256k1Ready")
    reloaded = wallet_page.evaluate(
        """async ({kit, pin}) => {
          const before = walletSession.isUnlockedFor(kit.canonical_v1_address);
          const unlocked = await walletSession.unlockWallet({pin, address:kit.canonical_v1_address, prompt:false});
          return {before, unlocked, after:walletSession.isUnlockedFor(kit.canonical_v1_address)};
        }""",
        material,
    )
    assert reloaded == {"before": False, "unlocked": True, "after": True}

    wallet_page.once("dialog", lambda dialog: dialog.dismiss())
    assert wallet_page.evaluate("() => walletSession.confirmUserPresence('synthetic signing')") is False
