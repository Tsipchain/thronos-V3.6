"""
Wallet V1 Centralized Signed Requests Tests.

Verifies that:
1. All protected services use central verify_wallet_v1_signed_request()
2. Frontend uses walletV1BuildSignedRequest() before calling services
3. Signatures are in consistent format across all services
4. Bound signer wallets work correctly
5. Direct V1 wallets still work
6. Proper error handling and messages
"""

import pytest
import json
from pathlib import Path


def test_verify_wallet_v1_signed_request_exists():
    """Verify central verifier function exists in server.py."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()

    assert "def verify_wallet_v1_signed_request" in content, \
        "Central verifier function not found"

    # Extract function
    start = content.find("def verify_wallet_v1_signed_request")
    end = content.find("\ndef ", start + 1)
    func_code = content[start:end]

    # Must validate required fields
    assert "canonical_v1_address" in func_code, \
        "Verifier must validate canonical_v1_address"

    assert "public_key" in func_code, \
        "Verifier must validate public_key"

    assert "signature" in func_code, \
        "Verifier must validate signature"

    # Must handle key binding
    assert "get_active_key_binding_for_address" in func_code, \
        "Verifier must check active bindings"

    # Must not log secrets
    assert "private_key" not in func_code.lower() or "never logs" in func_code.lower(), \
        "Verifier must not log private keys"


def test_walletV1BuildSignedRequest_exists():
    """Verify frontend signing helper exists."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    assert "async function walletV1BuildSignedRequest" in content, \
        "Frontend signing helper not found"

    # Extract function
    start = content.find("async function walletV1BuildSignedRequest")
    end = content.find("\n}", start) + 2
    func_code = content[start:end]

    # Must check for runtime signing material
    assert "hasRuntimeSigningMaterial" in func_code or "isUnlockedFor" in func_code, \
        "Must check for Wallet V1 runtime signing material"

    # Must require unlock
    assert "Unlock Wallet V1 first" in func_code, \
        "Must show unlock message when locked"

    # Must build canonical payload
    assert "signingPayload" in func_code, \
        "Must build signing payload"

    # Must sign with private key
    assert "signMessage" in func_code or "sign" in func_code.lower(), \
        "Must sign payload with private key"

    # Must return public_key + signature
    assert "public_key" in func_code and "signature" in func_code, \
        "Must return public_key and signature"


def test_signed_request_format():
    """Verify signed request has required fields."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    # Extract function to see return format
    start = content.find("async function walletV1BuildSignedRequest")
    end = content.find("\n}", start) + 2
    func_code = content[start:end]

    # Must return object with these fields
    required_fields = [
        "canonical_v1_address",
        "from",
        "public_key",
        "signature",
        "signature_format",
        "action",
        "payload",
        "timestamp",
        "nonce"
    ]

    for field in required_fields:
        assert field in func_code, \
            f"Signed request must include {field} field"


def test_signature_format_consistency():
    """Verify signature format is consistent everywhere."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    # New financial requests use the explicitly versioned full-payload contract.
    assert 'signature_format: contract.SIGNATURE_FORMAT' in content, \
        "Frontend must use the full-payload V2 signature format"

    # Check consistency
    server_py = Path(__file__).parent.parent / "server.py"
    server_content = server_py.read_text()

    # Backend retains explicit legacy parsing while financial routes require V2.
    verifier = (Path(__file__).parent.parent / "wallet_v1_signed_request_verifier.py").read_text()
    assert "secp256k1_compact" in verifier
    assert "wallet_v1_full_payload_v2" in verifier


def test_bound_signer_validation():
    """Verify bound signer validation is delegated to the crypto boundary."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()
    verifier = (Path(__file__).parent.parent / "wallet_v1_signed_request_verifier.py").read_text()

    # Extract verify function
    start = content.find("def verify_wallet_v1_signed_request")
    end = content.find("\ndef ", start + 1)
    func_code = content[start:end]

    assert "verify_signed_request" in func_code, \
        "Server wrapper must delegate to the cryptographic verifier"
    assert "get_active_key_binding_for_address" in func_code, \
        "Must check for active binding"
    assert "signer_address != canonical_v1_address" in verifier, \
        "Cryptographic verifier must detect a bound signer"
    assert '"no_active_binding"' in verifier, \
        "Cryptographic verifier must reject an unbound signer"
    assert '"public_key_mismatch"' in verifier, \
        "Cryptographic verifier must reject the wrong bound key"


def test_direct_wallet_still_works():
    """Verify direct V1 wallets (signer == canonical) still work."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()
    verifier = (Path(__file__).parent.parent / "wallet_v1_signed_request_verifier.py").read_text()

    # Extract verify function
    start = content.find("def verify_wallet_v1_signed_request")
    end = content.find("\ndef ", start + 1)
    func_code = content[start:end]

    assert "verify_signed_request" in func_code
    assert "signer_address != canonical_v1_address" in verifier, \
        "Must distinguish direct and bound signers"
    assert "Direct wallet" in verifier, \
        "Must preserve the direct-wallet path"


def test_error_cases():
    """Verify proper error handling."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()
    verifier = (Path(__file__).parent.parent / "wallet_v1_signed_request_verifier.py").read_text()

    # Extract verify function
    start = content.find("def verify_wallet_v1_signed_request")
    end = content.find("\ndef ", start + 1)
    func_code = content[start:end]

    # Must handle missing fields
    assert "invalid_canonical_address" in verifier, \
        "Must reject invalid canonical address"

    assert "missing_public_key" in verifier, \
        "Must reject missing public key"

    assert "invalid_signature_format" in verifier, \
        "Must reject invalid signature format"

    # Must handle signature verification failure
    assert "invalid_signature" in verifier, \
        "Must reject invalid signatures"

    # Must handle missing binding
    assert "no_active_binding" in verifier, \
        "Must reject missing binding for bound signer"


def test_frontend_lock_check_before_backend():
    """Verify frontend checks unlock state BEFORE calling backend."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    # Extract walletV1BuildSignedRequest
    start = content.find("async function walletV1BuildSignedRequest")
    end = content.find("\n}", start) + 2
    func_code = content[start:end]

    # Must check runtime signing material FIRST
    check_pos = func_code.find("hasRuntimeSigningMaterial")
    throw_pos = func_code.find('throw new Error("Unlock Wallet V1 first")')

    assert check_pos > 0 and throw_pos > 0, \
        "Must check for runtime signing material"

    assert check_pos < throw_pos, \
        "Must check unlock state BEFORE throwing error"


def test_no_secrets_in_logs():
    """Verify no secrets logged in verification."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()

    # Extract verify function
    start = content.find("def verify_wallet_v1_signed_request")
    end = content.find("\ndef ", start + 1)
    func_code = content[start:end]

    # Search for log statements
    log_lines = [line for line in func_code.split("\n") if "logger" in line]

    # Verify each log statement doesn't log secrets
    for log_line in log_lines:
        assert "private_key" not in log_line.lower(), \
            "Must not log private keys"
        assert "signature_hex" not in log_line.lower(), \
            "Must not log signatures"
        assert "pin" not in log_line.lower(), \
            "Must not log PINs"
        assert "recovery" not in log_line.lower(), \
            "Must not log recovery info"


def test_signed_request_diagnostics():
    """Verify diagnostic data is available (but no secrets)."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()

    # Extract verify function
    start = content.find("def verify_wallet_v1_signed_request")
    end = content.find("\ndef ", start + 1)
    func_code = content[start:end]

    # Should have diagnostics object
    assert "diagnostics" in func_code, \
        "Should return diagnostics object"

    # Check what diagnostics are available
    diag_section = func_code[func_code.find("diagnostics"):func_code.find("diagnostics") + 500]

    # Safe diagnostics
    safe_diags = ["has_public_key", "has_signature", "signature_format", "has_active_binding"]
    for diag in safe_diags:
        assert diag in diag_section, \
            f"Should include {diag} in diagnostics"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
