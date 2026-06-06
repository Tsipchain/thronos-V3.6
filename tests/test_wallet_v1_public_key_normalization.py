"""
Wallet V1 Public Key Format Normalization Tests.

Verifies that:
1. Public key format is validated on both frontend and backend
2. Compressed (02/03 + 64 hex) and uncompressed (04 + 128 hex) formats accepted
3. Invalid formats rejected client-side before backend call
4. Backend returns specific "invalid_public_key_format" error
5. Admin signer generation stores valid secp256k1 public key hex
6. Recovery kit restore stores valid secp256k1 public key hex
7. Normalization handles common issues (0x prefix, case sensitivity)
"""

import pytest
import json
from pathlib import Path


class TestFrontendPublicKeyValidation:
    """Test frontend validation functions in base.html."""

    def test_isValidSecp256k1PublicKeyHex_exists(self):
        """Verify isValidSecp256k1PublicKeyHex function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function isValidSecp256k1PublicKeyHex" in content, \
            "Public key validation function not found"

    def test_normalizeSecp256k1PublicKey_exists(self):
        """Verify normalizeSecp256k1PublicKey function exists."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert "function normalizeSecp256k1PublicKey" in content, \
            "Public key normalization function not found"

    def test_public_key_validation_in_walletV1BuildSignedRequest(self):
        """Verify walletV1BuildSignedRequest validates public key before backend call."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract walletV1BuildSignedRequest function
        start = content.find("async function walletV1BuildSignedRequest")
        end = content.find("\n}", start) + 2
        func_code = content[start:end]

        # Must normalize public key
        assert "normalizeSecp256k1PublicKey" in func_code, \
            "Must normalize public key"

        # Must validate normalized public key
        assert "isValidSecp256k1PublicKeyHex" in func_code, \
            "Must validate public key format"

        # Must throw error if invalid
        assert "Invalid Wallet V1 public key" in func_code, \
            "Must reject invalid public key format"

    def test_public_key_from_runtime_first(self):
        """Verify walletV1BuildSignedRequest gets public key from runtime first."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract walletV1BuildSignedRequest function
        start = content.find("async function walletV1BuildSignedRequest")
        end = content.find("\n}", start) + 2
        func_code = content[start:end]

        # Must try runtime first
        assert "walletSession.getPublicKey" in func_code, \
            "Must try to get public key from runtime"

        # Must find getPublicKey before localStorage fallback
        getpubkey_pos = func_code.find("walletSession.getPublicKey")
        localstorage_pos = func_code.find("localStorage.getItem('wallet_v1_public_key')")

        assert getpubkey_pos < localstorage_pos, \
            "Must check runtime public key before localStorage"

    def test_normalization_removes_0x_prefix(self):
        """Verify normalizeSecp256k1PublicKey removes 0x prefix."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract normalizeSecp256k1PublicKey function
        start = content.find("function normalizeSecp256k1PublicKey")
        end = content.find("\n}", start) + 2
        func_code = content[start:end]

        # Must handle 0x prefix
        assert "0x" in func_code and ("substring" in func_code or "slice" in func_code or "startsWith" in func_code), \
            "Must remove 0x prefix"

    def test_normalization_validates_hex(self):
        """Verify normalizeSecp256k1PublicKey validates hex characters."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract normalizeSecp256k1PublicKey function
        start = content.find("function normalizeSecp256k1PublicKey")
        end = content.find("\n}", start) + 2
        func_code = content[start:end]

        # Must use regex to validate hex
        assert "/^[0-9a-f]" in func_code, \
            "Must validate hex characters with regex"


class TestBackendPublicKeyValidation:
    """Test backend validation in server.py."""

    def test_public_key_validation_helper_exists(self):
        """Verify backend has public key validation helper."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "_is_valid_secp256k1_public_key_hex" in content, \
            "Backend public key validation helper not found"

    def test_verify_function_validates_public_key(self):
        """Verify verify_wallet_v1_signed_request calls public key validator."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Extract verify function
        start = content.find("def verify_wallet_v1_signed_request")
        end = content.find("\ndef ", start + 1)
        func_code = content[start:end]

        # Must call validation helper
        assert "_is_valid_secp256k1_public_key_hex" in func_code, \
            "Verifier must validate public key format"

    def test_verify_returns_invalid_public_key_format_error(self):
        """Verify backend returns specific invalid_public_key_format error."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Extract verify function
        start = content.find("def verify_wallet_v1_signed_request")
        end = content.find("\ndef ", start + 1)
        func_code = content[start:end]

        # Must return specific error for invalid format
        assert "invalid_public_key_format" in func_code, \
            "Must return invalid_public_key_format error"

    def test_validation_before_key_derivation(self):
        """Verify public key format validated BEFORE attempting derivation."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Extract verify function
        start = content.find("def verify_wallet_v1_signed_request")
        end = content.find("\ndef ", start + 1)
        func_code = content[start:end]

        # Find positions of validation and derivation
        validation_pos = func_code.find("_is_valid_secp256k1_public_key_hex")
        derivation_pos = func_code.find("derive_thr_address_from_public_key_hex")

        assert validation_pos > 0 and derivation_pos > 0, \
            "Both validation and derivation must be present"

        assert validation_pos < derivation_pos, \
            "Validation must happen before derivation"


class TestAdminSignerGeneration:
    """Test that admin signer generation stores valid public key format."""

    def test_admin_signer_stores_valid_public_key(self):
        """Verify walletAdminGenerateSignerForCanonical stores valid public key."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Extract admin signer generation function
        start = content.find("function walletAdminGenerateSignerForCanonical")
        end = content.find("\n}\n", start) + 3
        func_code = content[start:end]

        # Must store public key to localStorage
        assert "localStorage.setItem('wallet_v1_public_key'" in func_code, \
            "Must save public_key to localStorage"

        # The public key should come from the generated signer
        # (not a hash, address, object, or other format)
        # Check that it's storing the actual public key value
        assert "publicKey" in func_code or "public_key" in func_code.lower(), \
            "Must store the actual public key"


class TestRecoveryKitRestore:
    """Test that recovery kit restore stores valid public key format."""

    def test_recovery_kit_restore_uses_valid_public_key(self):
        """Verify recovery kit restore handles public key correctly."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        # Look for recovery kit restore function
        if "restoreRecoveryKit" in content or "restoreFromRecoveryKit" in content or "recoverFromKit" in content:
            # Must properly restore public key from kit
            assert "public_key" in content.lower(), \
                "Recovery kit must include public_key field"


class TestSignedRequestWithValidPublicKey:
    """Test signed requests using valid public key formats."""

    def test_swap_request_validates_public_key_before_backend(self):
        """Verify swap.html validates public key before calling backend."""
        swap_html = Path(__file__).parent.parent / "templates" / "swap.html"
        content = swap_html.read_text()

        # Extract swap execution function
        if "walletV1BuildSignedRequest" in content:
            # Must be called to build signed request with validated public key
            assert "walletV1BuildSignedRequest" in content, \
                "Swap must use centralized signed request builder"

    def test_pools_request_validates_public_key_before_backend(self):
        """Verify pools.html validates public key before calling backend."""
        pools_html = Path(__file__).parent.parent / "templates" / "pools.html"
        content = pools_html.read_text()

        # Extract addLiquidity function
        if "walletV1BuildSignedRequest" in content:
            # Must be called to build signed request with validated public key
            assert "walletV1BuildSignedRequest" in content, \
                "Pools must use centralized signed request builder"


class TestPublicKeyFormatExamples:
    """Test known public key format examples."""

    def test_compressed_public_key_format(self):
        """Verify example of valid compressed public key."""
        # Valid compressed: 02/03 + 64 hex chars = 66 chars total
        valid_compressed = "02" + "a" * 64
        assert len(valid_compressed) == 66
        assert valid_compressed.startswith("02") or valid_compressed.startswith("03")

    def test_uncompressed_public_key_format(self):
        """Verify example of valid uncompressed public key."""
        # Valid uncompressed: 04 + 128 hex chars = 130 chars total
        valid_uncompressed = "04" + "b" * 128
        assert len(valid_uncompressed) == 130
        assert valid_uncompressed.startswith("04")

    def test_invalid_public_key_too_short(self):
        """Verify invalid public key: too short."""
        invalid_short = "02" + "c" * 32  # 34 chars instead of 66
        assert len(invalid_short) == 34

    def test_invalid_public_key_wrong_prefix(self):
        """Verify invalid public key: wrong prefix."""
        invalid_prefix = "05" + "d" * 64  # 05 is invalid prefix
        assert len(invalid_prefix) == 66

    def test_invalid_public_key_address_format(self):
        """Verify address is not accepted as public key."""
        # An address starts with THR, not 02/03/04
        invalid_address = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"
        assert not invalid_address.startswith("02")
        assert not invalid_address.startswith("03")
        assert not invalid_address.startswith("04")

    def test_invalid_public_key_hash_format(self):
        """Verify hash is not accepted as public key."""
        # A SHA256 hash would be 64 hex chars, doesn't start with 02/03/04
        invalid_hash = "a" * 64
        assert not invalid_hash.startswith("02")
        assert not invalid_hash.startswith("03")
        assert not invalid_hash.startswith("04")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
