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
PLEDGE_TEMPLATE = (ROOT / "templates" / "pledge_form.html").read_text()


def _extract_function(name: str, source: str = TEMPLATE) -> str:
    """Extract one top-level JS function, respecting strings and comments."""
    markers = (f"async function {name}", f"function {name}")
    start = next((source.find(marker) for marker in markers if source.find(marker) >= 0), -1)
    if start < 0:
        raise AssertionError(f"production function not found: {name}")
    brace = source.find("{", start)
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    index = brace
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
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
                return source[start : index + 1]
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
RECOVERY_JS += "\n" + _extract_function("installPledgeWalletV1", PLEDGE_TEMPLATE)


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
    bindings: dict[str, dict] = {}
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
        return jsonify(ok=True, binding=bindings.get(address))

    @app.post("/api/v1/wallet/bind_public_key")
    def bind_public_key():
        body = request.get_json(force=True)
        public_key = body["public_key"]
        binding = {
            "status": "active",
            "public_key": public_key,
            "bound_key_address": derive_thronos_address(public_key),
        }
        if body["address"] == "THR" + "D" * 40:
            binding["bound_key_address"] = "THR" + "E" * 40
        bindings[body["address"]] = binding
        return jsonify(ok=True, binding=binding)

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
          const persisted = Object.fromEntries(Object.keys(localStorage).map(key => [key, localStorage.getItem(key)]));
          return {restored, advancedOpen, expanded, unlocked: walletSession.isUnlockedFor(kit.canonical_v1_address), first: first.status, replay: replay.status, persisted};
        }""",
        material,
    )
    assert result["restored"]["success"] is True
    assert result["advancedOpen"] is True
    assert result["expanded"] == "true"
    assert result["unlocked"] is True
    assert result["first"] == 200
    assert result["replay"] == 409
    assert "wallet_pin" not in result["persisted"]
    assert material["privateKey"] not in result["persisted"].values()


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
          const mismatchedBound = {...first.kit, bound_key_address: second.kit.canonical_v1_address};
          try { await walletV1RestoreFromRecoveryKit(mismatchedBound, first.pin); } catch (e) { errors.push(e.message); }
          return {errors, identity: localStorage.getItem('wallet_v1_address'), encrypted: localStorage.getItem('wallet_v1_encrypted_priv'), pin: localStorage.getItem('wallet_pin'), original};
        }""",
        {"first": first, "second": second},
    )
    assert len(result["errors"]) == 4
    assert result["identity"] == result["original"]
    assert result["encrypted"] is None
    assert result["pin"] is None


def test_create_enroll_import_and_pledge_never_persist_plaintext_pin(wallet_page):
    imported = _make_kit(wallet_page, "8642")
    result = wallet_page.evaluate(
        """async ({imported}) => {
          const snapshots = {};
          const snapshot = (name, privateKey) => {
            const values = Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage.getItem(k)]));
            snapshots[name] = {pin: localStorage.getItem('wallet_pin'), leaksPrivateKey: Object.values(values).includes(privateKey)};
          };

          localStorage.clear();
          const created = await walletSession.createWalletV1({pin:'1234'});
          snapshot('create', 'not-returned');

          localStorage.clear();
          const importedResult = await walletSession.importSigningKeyForAddress(imported.privateKey, imported.pin, imported.kit.canonical_v1_address);
          snapshot('import', imported.privateKey);

          localStorage.clear();
          await installPledgeWalletV1(imported.kit.canonical_v1_address, 'synthetic-send-secret', imported.kit, imported.pin);
          snapshot('pledge', imported.privateKey);

          localStorage.clear();
          const canonical = 'THR' + 'A'.repeat(40);
          walletSession.setAddress(canonical);
          walletSession.setSendSeed('synthetic-legacy-secret');
          const enrolled = await walletSession.enrollSigningMaterial({address:canonical, credentialLookupAddress:canonical, pin:'9753'});
          snapshot('enroll', 'not-returned');

          localStorage.clear();
          const mismatchedCanonical = 'THR' + 'D'.repeat(40);
          walletSession.setAddress(mismatchedCanonical);
          walletSession.setSendSeed('synthetic-legacy-secret');
          let enrollmentMismatch = '';
          try { await walletSession.enrollSigningMaterial({address:mismatchedCanonical, credentialLookupAddress:mismatchedCanonical, pin:'9753'}); }
          catch (e) { enrollmentMismatch = e.message; }
          snapshot('enrollMismatch', 'not-returned');

          return {snapshots, created, importedResult, enrolledAddress:enrolled.address, enrollmentMismatch};
        }""",
        {"imported": imported},
    )
    assert result["importedResult"]["success"] is True
    assert result["enrollmentMismatch"] == "wallet_signing_enrollment_binding_mismatch"
    for snapshot in result["snapshots"].values():
        assert snapshot == {"pin": None, "leaksPrivateKey": False}


def test_legacy_credentials_survive_until_verified_v1_reauthentication(wallet_page):
    result = wallet_page.evaluate(
        """async () => {
          localStorage.clear();
          localStorage.setItem('thr_address', 'THR' + 'B'.repeat(40));
          localStorage.setItem('wallet_pin', 'legacy-pin');
          localStorage.setItem('send_secret', 'legacy-send-secret');
          const legacyPinBefore = walletSession.getPin();
          await walletSession.createWalletV1({pin:'new-v1-pin'});
          return {
            legacyPinBefore,
            pinAfter: localStorage.getItem('wallet_pin'),
            secretAfter: localStorage.getItem('send_secret'),
            migration: JSON.parse(localStorage.getItem('wallet_v1_credential_migration'))
          };
        }"""
    )
    assert result["legacyPinBefore"] == "legacy-pin"
    assert result["pinAfter"] is None
    assert result["secretAfter"] == "legacy-send-secret"
    assert result["migration"]["status"] == "plaintext_pin_retired"


def test_account_switch_clears_runtime_signer_and_fails_closed(wallet_page):
    material = _make_kit(wallet_page)
    result = wallet_page.evaluate(
        """async ({kit, pin}) => {
          localStorage.clear();
          localStorage.setItem('wallet_v1_address', kit.canonical_v1_address);
          await walletV1RestoreFromRecoveryKit(kit, pin);
          const before = walletSession.isUnlockedFor(kit.canonical_v1_address);
          const other = 'THR' + 'C'.repeat(40);
          walletSession.setAddress(other);
          let error = '';
          try { await walletSession.signTransaction({from:other, to:kit.canonical_v1_address, amount:'1', token:'THR', nonce:'switch', timestamp:1700000000}); }
          catch (e) { error = e.message; }
          return {before, oldUnlocked:walletSession.isUnlockedFor(kit.canonical_v1_address), otherUnlocked:walletSession.isUnlockedFor(other), error};
        }""",
        material,
    )
    assert result == {"before": True, "oldUnlocked": False, "otherUnlocked": False, "error": "wallet_locked"}


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


@pytest.fixture(scope="module")
def actual_auth_server(tmp_path_factory):
    """Serve the real server_ext challenge/verification routes on an isolated DB."""
    isolated = tmp_path_factory.mktemp("wallet-auth-server")
    os.environ.setdefault("SCHEDULER_ENABLED", "0")
    os.environ.setdefault("EDU_DB_PATH", str(isolated / "edu.db"))
    os.environ.setdefault("DATA_DIR", str(isolated / "data"))
    from server_ext import app

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_real_server_challenge_signature_binding_and_replay(actual_auth_server):
    playwright = pytest.importorskip("playwright.sync_api")
    noble_module = Path(os.environ.get(
        "WALLET_E2E_NOBLE_MODULE",
        "/tmp/wallet-e2e-js/node_modules/@noble/secp256k1/index.js",
    ))
    with playwright.sync_playwright() as runtime:
        executable = os.environ.get("WALLET_E2E_CHROMIUM") or shutil.which("chromium")
        options = {"headless": True, "args": ["--no-sandbox"]}
        if executable:
            options["executable_path"] = executable
        browser = runtime.chromium.launch(**options)
        page = browser.new_page()
        page.route(
            "https://cdn.jsdelivr.net/npm/@noble/secp256k1@2.2.3/+esm",
            lambda route: route.fulfill(
                status=200,
                content_type="application/javascript",
                headers={"Access-Control-Allow-Origin": "*"},
                body=noble_module.read_text(),
            ),
        )
        def fulfill_address_derivation(route):
            import json
            body = json.loads(route.request.post_data or "{}")
            public_key = body.get("public_key") or body["compressed_public_key"]
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"address": derive_thronos_address(public_key)}),
            )
        page.route("**/api/v1/address/derive", fulfill_address_derivation)
        page.goto(actual_auth_server + "/api/auth/challenge", wait_until="domcontentloaded")
        page.add_script_tag(url=actual_auth_server + "/static/vendor/noble-secp256k1.min.js")
        page.add_script_tag(url=actual_auth_server + "/static/wallet_session.js")
        page.evaluate("() => window.__nobleSecp256k1Ready")

        result = page.evaluate(
            """async () => {
              localStorage.clear();
              const created = await walletSession.createWalletV1({pin:'actual-route-pin'});
              const challengeResponse = await fetch('/api/auth/challenge', {method:'POST'});
              const challenge = (await challengeResponse.json()).challenge;
              const signed = await walletSession.signLoginChallenge(challenge);
              const payload = {challenge_response:challenge, signature:signed.signature, public_key:signed.public_key};
              const verified = await fetch('/api/auth/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
              const replay = await fetch('/api/auth/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
              return {created, verified:verified.status, replay:replay.status, pin:localStorage.getItem('wallet_pin')};
            }"""
        )
        browser.close()

    assert result["verified"] == 200
    assert result["replay"] == 400
    assert result["pin"] is None
