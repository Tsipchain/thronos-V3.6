"""Security acceptance for Wallet V1 full-payload signed requests."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from flask import Flask, Response, jsonify, request as flask_request, send_from_directory
from werkzeug.serving import make_server

import server
from wallet_v1_signed_request_verifier import (
    FULL_PAYLOAD_CHAIN_ID,
    FULL_PAYLOAD_CONTRACT,
    FULL_PAYLOAD_DOMAIN,
    FULL_PAYLOAD_PROTOCOL_VERSION,
    FULL_PAYLOAD_SIGNATURE_FORMAT,
    canonical_signed_request_bytes,
    derive_thr_address_from_public_key_hex,
    verify_signed_request,
)


NOW = 1_800_000_000


def _key_material(private_value=41):
    private_key = ec.derive_private_key(private_value, ec.SECP256K1())
    numbers = private_key.public_key().public_numbers()
    public_key = ("02" if numbers.y % 2 == 0 else "03") + f"{numbers.x:064x}"
    return private_key, public_key, derive_thr_address_from_public_key_hex(public_key)


def _sign(request, private_key):
    message, contract = canonical_signed_request_bytes(request)
    assert contract == FULL_PAYLOAD_CONTRACT
    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    request["signature"] = f"{r:064x}{s:064x}"
    request["signing_payload_hash"] = hashlib.sha256(message).hexdigest()
    return request


def _request(action="swap", payload=None, nonce="v2-nonce-1", issued_at=NOW):
    private_key, public_key, address = _key_material()
    request = {
        "signature_format": FULL_PAYLOAD_SIGNATURE_FORMAT,
        "protocol_version": FULL_PAYLOAD_PROTOCOL_VERSION,
        "domain": FULL_PAYLOAD_DOMAIN,
        "chain_id": FULL_PAYLOAD_CHAIN_ID,
        "action": action,
        "canonical_v1_address": address,
        "from": address,
        "signer_address": address,
        "bound_key_address": None,
        "public_key": public_key,
        "payload": payload
        or {
            "amount_in": "1.25",
            "metadata": {"route": ["THR", "USDT"], "strict": True},
            "min_amount_out": "1.20",
            "pool_id": "pool-7",
            "quote": {"id": "quote-9", "max_slippage_bps": "50"},
            "recipient": "THRRECIPIENT00000000000000000000000000000",
            "token_in": "THR",
            "token_out": "USDT",
        },
        "issued_at": str(issued_at),
        "expires_at": str(issued_at + 120),
        "nonce": nonce,
    }
    return _sign(request, private_key)


class LockedNonceGuard:
    def __init__(self):
        self._lock = threading.Lock()
        self._seen = set()

    def __call__(self, address, nonce, _timestamp):
        with self._lock:
            key = (address, nonce)
            if key in self._seen:
                return False, "nonce_replay_detected"
            self._seen.add(key)
            return True, ""


def _verify(request, expected_action="swap", guard=None, now=NOW):
    return verify_signed_request(
        request,
        expected_action,
        binding_lookup=lambda _address: None,
        nonce_guard=guard or LockedNonceGuard(),
        now=now,
    )


def test_v2_golden_vector_canonical_bytes_are_recursive_and_portable():
    request = _request()
    message, contract = canonical_signed_request_bytes(request)
    decoded = json.loads(message)
    assert contract == FULL_PAYLOAD_CONTRACT
    assert message == json.dumps(
        decoded, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    assert decoded["payload"]["metadata"]["route"] == ["THR", "USDT"]
    assert decoded["payload"]["amount_in"] == "1.25"


def test_browser_and_python_canonical_serialization_match_byte_for_byte():
    node = shutil.which("node")
    if not node:
        pytest.skip("node runtime unavailable")
    request = _request()
    python_bytes, _ = canonical_signed_request_bytes(request)
    module_path = Path(__file__).parents[1] / "static" / "wallet_v1_full_payload_contract.js"
    fields = {
        key: request[key]
        for key in (
            "action",
            "canonical_v1_address",
            "expires_at",
            "issued_at",
            "nonce",
            "payload",
            "signer_address",
        )
    }
    script = (
        "const c=require(process.argv[1]);"
        "const f=JSON.parse(process.argv[2]);"
        "process.stdout.write(c.canonicalJson(c.buildEnvelope(f)));"
    )
    completed = subprocess.run(
        [node, "-e", script, str(module_path), json.dumps(fields)],
        check=True,
        capture_output=True,
        text=False,
    )
    assert completed.stdout == python_bytes


def test_v2_valid_signature_binds_complete_nested_payload_and_identity():
    ok, details = _verify(_request())
    assert ok is True
    assert details["signature_contract"] == FULL_PAYLOAD_CONTRACT
    assert details["payload_cryptographically_bound"] is True
    assert details["signer_address"] == details["canonical_v1_address"]


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("payload", "amount_in"), "99"),
        (("payload", "token_in"), "WBTC"),
        (("payload", "token_out"), "L2E"),
        (("payload", "recipient"), "THRATTACKER0000000000000000000000000000"),
        (("payload", "pool_id"), "pool-attacker"),
        (("payload", "min_amount_out"), "0"),
        (("payload", "quote", "id"), "quote-attacker"),
        (("payload", "quote", "max_slippage_bps"), "9999"),
        (("payload", "metadata", "route"), ["THR", "WBTC"]),
        (("action",), "add_liquidity"),
        (("domain",), "attacker.wallet.request"),
        (("chain_id",), "thronos-testnet"),
        (("signer_address",), "THR" + "E" * 40),
        (("canonical_v1_address",), "THR" + "F" * 40),
    ],
)
def test_any_operation_or_envelope_tampering_fails(path, replacement):
    request = _request()
    target = request
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    ok, details = _verify(request)
    assert ok is False
    assert details["error"] in {
        "action_mismatch",
        "chain_id_mismatch",
        "domain_mismatch",
        "signing_payload_hash_mismatch",
    }


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (["not-an-object"], "payload_must_be_object"),
        ({"amount": 1.25}, "payload_numbers_must_be_strings"),
        ({"amount": float("inf")}, "payload_numbers_must_be_strings"),
    ],
)
def test_malformed_or_nonportable_payload_fails_closed(payload, error):
    request = _request()
    request["payload"] = payload
    with pytest.raises(ValueError, match=error):
        canonical_signed_request_bytes(request)


def test_expiry_and_protocol_version_fail_before_nonce_consumption():
    guard = LockedNonceGuard()
    expired = _request()
    ok, details = _verify(expired, guard=guard, now=NOW + 121)
    assert ok is False
    assert details["error"] == "request_expired"
    version_changed = _request(nonce="v2-version")
    version_changed["protocol_version"] = "1"
    ok, details = _verify(version_changed, guard=guard)
    assert ok is False
    assert details["error"] == "protocol_version_mismatch"
    assert guard._seen == set()


def test_duplicate_and_concurrent_duplicate_are_exactly_once():
    request = _request()
    guard = LockedNonceGuard()
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: _verify(copy.deepcopy(request), guard=guard), range(16)))
    assert sum(1 for ok, _ in results if ok) == 1
    assert sum(1 for ok, details in results if not ok and details["error"] == "nonce_replay_detected") == 15


def test_v2_active_bound_signer_preserves_canonical_migrated_identity():
    canonical_private, _, canonical_address = _key_material(private_value=61)
    del canonical_private
    signer_private, signer_public, signer_address = _key_material(private_value=62)
    request = _request(nonce="v2-bound")
    request.update({
        "canonical_v1_address": canonical_address,
        "signer_address": signer_address,
        "bound_key_address": signer_address,
        "public_key": signer_public,
        "from": canonical_address,
    })
    _sign(request, signer_private)
    binding = {"public_key": signer_public, "public_key_address": signer_address}
    ok, details = verify_signed_request(
        request,
        "swap",
        binding_lookup=lambda address: binding if address == canonical_address else None,
        nonce_guard=LockedNonceGuard(),
        now=NOW,
    )
    assert ok is True
    assert details["canonical_v1_address"] == canonical_address
    assert details["signer_address"] == signer_address
    assert details["is_bound_signer"] is True


def test_re_signed_false_signer_claim_is_rejected_cryptographically():
    request = _request(nonce="v2-false-signer")
    request["signer_address"] = "THR" + "E" * 40
    private_key, _, _ = _key_material()
    _sign(request, private_key)
    ok, details = _verify(request)
    assert ok is False
    assert details["error"] == "signer_address_mismatch"


@pytest.mark.parametrize(
    ("action", "payload", "shadow_field"),
    [
        ("swap", {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "0.9"}, "amount_in"),
        ("create_pool", {"token_a": "THR", "token_b": "WBTC", "amount_a": "1", "amount_b": "0.1", "fee_bps": "30"}, "amount_a"),
        ("add_liquidity", {"pool_id": "pool-1", "amount_a": "1", "amount_b": "0.1"}, "amount_b"),
        ("remove_liquidity", {"pool_id": "pool-1", "shares": "0.5"}, "shares"),
        ("tip", {"track_id": "track-1", "amount": "2", "token_symbol": "THR"}, "amount"),
    ],
)
def test_each_v2_execution_boundary_accepts_nested_fields_and_rejects_shadowing(
    monkeypatch, tmp_path, action, payload, shadow_field
):
    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / f"{action}.sqlite3"),
    )
    now = int(time.time())
    request = _request(action=action, payload=payload, nonce=f"{action}-ok", issued_at=now)
    ok, error, address = server._verify_walletv1_new_format(
        request, action, require_full_payload=True
    )
    assert ok is True and error == {} and address == request["canonical_v1_address"]

    shadowed = _request(
        action=action, payload=payload, nonce=f"{action}-shadow", issued_at=now
    )
    shadowed[shadow_field] = "attacker-value"
    ok, error, address = server._verify_walletv1_new_format(
        shadowed, action, require_full_payload=True
    )
    assert ok is False
    assert error["error"] == "unsigned_top_level_fields"
    assert address is None


def test_financial_boundary_rejects_legacy_contract_and_top_level_shadow_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / "wallet_v1_signed_request_nonces.sqlite3"),
    )
    swap_payload = {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "0.9"}
    request = _request(payload=swap_payload, issued_at=int(time.time()))
    ok, error, address = server._verify_walletv1_new_format(
        request, "swap", require_full_payload=True
    )
    assert ok is True and error == {} and address == request["canonical_v1_address"]

    shadowed = _request(payload=swap_payload, nonce="v2-shadow", issued_at=int(time.time()))
    shadowed["amount_in"] = "999"
    ok, error, address = server._verify_walletv1_new_format(
        shadowed, "swap", require_full_payload=True
    )
    assert ok is False
    assert error["error"] == "unsigned_top_level_fields"
    assert address is None
    shadowed.pop("amount_in")
    ok, error, address = server._verify_walletv1_new_format(
        shadowed, "swap", require_full_payload=True
    )
    assert ok is True and error == {} and address == shadowed["canonical_v1_address"]

    private_key, public_key, address = _key_material(private_value=52)
    legacy = {
        "canonical_v1_address": address,
        "from": address,
        "public_key": public_key,
        "signature_format": "secp256k1_compact",
        "action": "swap",
        "payload": {"amount_in": "1", "token_in": "THR", "token_out": "USDT"},
        "timestamp": str(int(time.time())),
        "nonce": "legacy-financial-rejected",
    }
    message, _ = canonical_signed_request_bytes(legacy)
    der = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    legacy["signature"] = f"{r:064x}{s:064x}"
    legacy["signing_payload_hash"] = hashlib.sha256(message).hexdigest()
    ok, error, address = server._verify_walletv1_new_format(
        legacy, "swap", require_full_payload=True
    )
    assert ok is False
    assert error["error"] == "wallet_v1_full_payload_upgrade_required"
    assert address is None


@pytest.mark.parametrize(
    ("action", "valid_payload", "unsupported_field"),
    [
        ("swap", {"token_in": "THR", "token_out": "USDT", "amount_in": "1", "min_amount_out": "0.9"}, "quote_id"),
        ("add_liquidity", {"pool_id": "pool-1", "amount_a": "1", "amount_b": "0.1"}, "max_slippage_bps"),
        ("remove_liquidity", {"pool_id": "pool-1", "shares": "0.5"}, "min_amount_a"),
    ],
)
def test_unsupported_signed_constraints_fail_before_nonce_consumption(
    monkeypatch, tmp_path, action, valid_payload, unsupported_field
):
    monkeypatch.setattr(server, "REDIS_CLIENT", None)
    monkeypatch.setattr(
        server,
        "_WALLET_V1_SIGNED_NONCES_DB",
        str(tmp_path / f"unsupported-{action}.sqlite3"),
    )
    now = int(time.time())
    invalid_payload = dict(valid_payload)
    invalid_payload[unsupported_field] = "must-not-be-ignored"
    invalid = _request(
        action=action, payload=invalid_payload, nonce=f"{action}-constraint", issued_at=now
    )
    ok, error, _ = server._verify_walletv1_new_format(
        invalid, action, require_full_payload=True
    )
    assert ok is False
    assert error["error"] == "unsupported_signed_payload_fields"
    assert error["fields"] == [unsupported_field]

    valid = _request(
        action=action, payload=valid_payload, nonce=f"{action}-constraint", issued_at=now
    )
    ok, error, address = server._verify_walletv1_new_format(
        valid, action, require_full_payload=True
    )
    assert ok is True and error == {} and address == valid["canonical_v1_address"]


def test_modern_failure_cannot_downgrade_to_legacy_in_pool_ui():
    source = (Path(__file__).parents[1] / "templates" / "pools.html").read_text()
    assert "Centralized format failed, trying legacy format" not in source
    assert "A V1 failure must never downgrade" in source


def test_public_and_server_wallet_contract_copies_are_identical():
    root = Path(__file__).parents[1]
    assert (root / "static" / "wallet_v1_full_payload_contract.js").read_bytes() == (
        root / "public" / "static" / "wallet_v1_full_payload_contract.js"
    ).read_bytes()
    assert (root / "static" / "wallet_session.js").read_bytes() == (
        root / "public" / "static" / "wallet_session.js"
    ).read_bytes()


def test_pwa_direct_swap_fallback_uses_v2_and_offline_shell_caches_contract():
    root = Path(__file__).parents[1]
    app_source = (root / "public" / "wallet-pwa" / "app.js").read_text()
    service_worker = (root / "public" / "wallet-pwa" / "sw.js").read_text()
    fallback_start = app_source.index("} else if (_pwaSigningCtx?.privHex) {")
    fallback_end = app_source.index("      } else {\n        throw new Error('wallet_locked');", fallback_start)
    fallback = app_source[fallback_start:fallback_end]
    assert "contract.buildEnvelope" in fallback
    assert "signature_format: contract.SIGNATURE_FORMAT" in fallback
    assert "payload: {}" not in fallback
    assert "'/static/wallet_v1_full_payload_contract.js'" in service_worker
    assert "thr-wallet-pwa-v28" in service_worker


def _extract_js_function(source, name):
    start = source.index(f"function {name}")
    if source[max(0, start - 6):start] == "async ":
        start -= 6
    brace = source.index("{", start)
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
                return source[start:index + 1]
        index += 1
    raise AssertionError(f"unterminated JS function {name}")


def test_real_chromium_builds_signs_and_backend_verifies_v2_envelope():
    playwright = pytest.importorskip("playwright.sync_api")
    root = Path(__file__).parents[1]
    noble_module = Path(os.environ.get(
        "WALLET_E2E_NOBLE_MODULE",
        "/tmp/wallet-e2e-js/node_modules/@noble/secp256k1/index.js",
    ))
    if not noble_module.is_file():
        pytest.fail("real browser secp256k1 dependency is unavailable")

    base_source = (root / "templates" / "base.html").read_text()
    helper_source = "\n".join(
        _extract_js_function(base_source, name)
        for name in (
            "normalizeSecp256k1PublicKey",
            "isValidSecp256k1PublicKeyHex",
            "walletV1BuildSignedRequest",
        )
    )
    app = Flask(__name__, static_folder=None)
    guard = LockedNonceGuard()

    @app.get("/")
    def browser_harness():
        return Response(
            "<!doctype html><script src='/static/vendor/noble-secp256k1.min.js'></script>"
            "<script src='/static/wallet_v1_full_payload_contract.js'></script>"
            "<script src='/static/wallet_session.js'></script>"
            f"<script>{helper_source}</script>",
            mimetype="text/html",
        )

    @app.get("/static/<path:filename>")
    def static_file(filename):
        if filename == "vendor/noble-secp256k1.min.js":
            loader = (root / "static" / filename).read_text().replace(
                "https://cdn.jsdelivr.net/npm/@noble/secp256k1@2.2.3/+esm",
                "/test-vendor/secp256k1.js",
            )
            return Response(loader, mimetype="application/javascript")
        return send_from_directory(root / "static", filename)

    @app.get("/test-vendor/secp256k1.js")
    def noble_secp256k1():
        return send_from_directory(noble_module.parent, noble_module.name)

    @app.post("/api/v1/address/derive")
    def derive_address():
        body = flask_request.get_json(force=True)
        public_key = body.get("public_key") or body["compressed_public_key"]
        return jsonify(address=derive_thr_address_from_public_key_hex(public_key))

    @app.get("/api/wallet/v1/key-binding/<address>")
    def no_binding(address):
        del address
        return jsonify(ok=True, binding=None)

    @app.post("/verify-v2")
    def verify_v2():
        body = flask_request.get_json(force=True)
        ok, details = verify_signed_request(
            body,
            "swap",
            binding_lookup=lambda _address: None,
            nonce_guard=guard,
            now=time.time(),
        )
        return jsonify(ok=ok, details=details), 200 if ok else 400

    test_server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=test_server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runtime:
            executable = os.environ.get("WALLET_E2E_CHROMIUM") or shutil.which("chromium")
            options = {"headless": True, "args": ["--no-sandbox"]}
            if executable:
                options["executable_path"] = executable
            browser = runtime.chromium.launch(**options)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{test_server.server_port}", wait_until="networkidle")
            page.evaluate("() => window.__nobleSecp256k1Ready")
            result = page.evaluate(
                """async () => {
                  localStorage.clear();
                  const created = await walletSession.createWalletV1({pin:'synthetic-browser-pin'});
                  const signed = await walletV1BuildSignedRequest('swap', {
                    token_in:'THR', token_out:'USDT', amount_in:1.25,
                    min_amount_out:'1.20', quote:{id:'q-browser', route:['THR','USDT']}
                  });
                  const accepted = await fetch('/verify-v2', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(signed)});
                  const acceptedBody = await accepted.json();
                  const tampered = JSON.parse(JSON.stringify(signed));
                  tampered.payload.quote.route[1] = 'WBTC';
                  const rejected = await fetch('/verify-v2', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(tampered)});
                  const rejectedBody = await rejected.json();
                  return {created, signed, accepted:accepted.status, acceptedBody, rejected:rejected.status, rejectedBody};
                }"""
            )
            browser.close()
    finally:
        test_server.shutdown()
        thread.join(timeout=5)

    assert result["accepted"] == 200
    assert result["acceptedBody"]["details"]["payload_cryptographically_bound"] is True
    assert result["rejected"] == 400
    assert result["rejectedBody"]["details"]["error"] == "signing_payload_hash_mismatch"
    assert result["signed"]["payload"]["amount_in"] == "1.25"
    assert result["signed"]["signature_format"] == FULL_PAYLOAD_SIGNATURE_FORMAT
    assert len(result["signed"]["signature"]) == 128

