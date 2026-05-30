"""
Tests for Wallet V1 signed pool actions and legacy auth fallback.

Verifies that pool endpoints (create_pool, add_liquidity, remove_liquidity)
accept both Wallet V1 signed transactions and legacy auth_secret auth.

Key: Signature verification must occur BEFORE any pool state mutation.
"""
import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import (
    app, verify_pool_wallet_v1_or_legacy,
    load_json, save_json, POOLS_FILE,
    LEDGER_FILE, WBTC_LEDGER_FILE, L2E_LEDGER_FILE,
    PLEDGE_FILE
)


class TestVerifyPoolWalletV1OrLegacy:
    """Test the core verification helper."""

    def test_missing_signature_rejected_before_mutation(self):
        """Verify V1 payload without signature is rejected."""
        payload = {
            "provider_thr": "THR1234567890",
            "public_key": "0x123456",
            # Missing signed_tx and signature
            "action": "create_pool"
        }

        ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

        assert ok is False
        assert err["error"] in ("invalid_auth", "missing_provider", "invalid_signature")

    def test_action_mismatch_rejected_before_signature_check(self):
        """Verify action mismatch is rejected before signature verification."""
        payload = {
            "provider_thr": "THR1234567890",
            "action": "add_liquidity",  # Wrong action
            "signed_tx": {
                "from": "THR1234567890",
                "signature": "0x789012"
            }
        }

        ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

        assert ok is False
        assert err["error"] == "unsupported_pool_action"
        assert err["expected"] == "create_pool"
        assert err["got"] == "add_liquidity"

    def test_v1_signature_verification_called(self):
        """Verify that actual Wallet V1 signature verification is invoked."""
        payload = {
            "provider_thr": "THR1234567890",
            "action": "create_pool",
            "signed_tx": {
                "from": "THR1234567890",
                "action": "create_pool",
                "publicKey": "0x123456",
                "signature": "0x789012"
            }
        }

        # Mock the wallet_v1_prod verification
        with patch('server.wallet_v1_production_final') as mock_v1:
            # Test invalid signature
            mock_v1.verify_signed_transaction_core.return_value = (False, "Invalid signature")
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

            # Should reject and call the verifier
            assert ok is False
            assert err["error"] == "invalid_signature"
            mock_v1.verify_signed_transaction_core.assert_called_once()

    def test_v1_signature_verification_valid(self):
        """Verify that valid signature is accepted."""
        payload = {
            "provider_thr": "THR1234567890",
            "action": "create_pool",
            "signed_tx": {
                "from": "THR1234567890",
                "action": "create_pool",
                "publicKey": "0x123456",
                "signature": "0x789012"
            }
        }

        # Mock successful verification
        with patch('server.wallet_v1_production_final') as mock_v1:
            mock_v1.verify_signed_transaction_core.return_value = (True, None)
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

            # Should accept
            assert ok is True
            assert wallet == "THR1234567890"
            mock_v1.verify_signed_transaction_core.assert_called_once()

    def test_missing_from_field_in_signed_tx_rejected(self):
        """Verify signed_tx without 'from' field is rejected."""
        payload = {
            "provider_thr": "THR1234567890",
            "action": "create_pool",
            "signed_tx": {
                # Missing 'from' field
                "publicKey": "0x123456",
                "signature": "0x789012"
            }
        }

        with patch('server.wallet_v1_production_final') as mock_v1:
            mock_v1.verify_signed_transaction_core.return_value = (True, None)
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

            # Should fail before/after signature check
            assert ok is False
            assert "from" in err["message"] or "must include" in err["message"]

    def test_provider_thr_mismatch_rejected(self):
        """Verify provider_thr mismatch with signed wallet is rejected."""
        payload = {
            "provider_thr": "THR1111111111",  # Different from signed wallet
            "action": "create_pool",
            "signed_tx": {
                "from": "THR2222222222",  # Different
                "action": "create_pool",
                "publicKey": "0x123456",
                "signature": "0x789012"
            }
        }

        with patch('server.wallet_v1_production_final') as mock_v1:
            mock_v1.verify_signed_transaction_core.return_value = (True, None)
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

            # Should reject wallet mismatch
            assert ok is False
            assert err["error"] == "wallet_mismatch"

    def test_action_alias_normalization(self):
        """Verify action aliases are normalized before verification."""
        test_cases = [
            ("create", "create_pool"),
            ("add", "add_liquidity"),
            ("remove", "remove_liquidity"),
        ]

        for alias, expected in test_cases:
            payload = {
                "provider_thr": "THR1234567890",
                "action": alias,
                "signed_tx": {
                    "from": "THR1234567890",
                    "action": expected,
                    "signature": "0x789012"
                }
            }

            with patch('server.wallet_v1_production_final') as mock_v1:
                mock_v1.verify_signed_transaction_core.return_value = (True, None)
                ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, expected)

                # Should normalize and accept
                assert ok is True
                assert err == {}

    def test_option_field_as_alias_for_action(self):
        """Verify 'option' field works as alias for 'action'."""
        payload = {
            "provider_thr": "THR1234567890",
            "option": "add_liquidity",  # Using 'option' instead of 'action'
            "signed_tx": {
                "from": "THR1234567890",
                "action": "add_liquidity",
                "signature": "0x789012"
            }
        }

        with patch('server.wallet_v1_production_final') as mock_v1:
            mock_v1.verify_signed_transaction_core.return_value = (True, None)
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "add_liquidity")

            # Should recognize and use 'option' field
            assert ok is True

    def test_legacy_auth_fallback_when_no_v1_fields(self):
        """Verify legacy auth_secret is used when no V1 fields present."""
        payload = {
            "provider_thr": "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a",
            "auth_secret": "test_secret"
        }

        # Mock validate_effective_auth for legacy path
        with patch('server.validate_effective_auth') as mock_auth:
            mock_auth.return_value = (True, {}, None)
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "add_liquidity")

            # Should use legacy auth
            assert ok is True
            assert wallet == payload["provider_thr"]
            mock_auth.assert_called_once()

    def test_legacy_auth_failed_rejected(self):
        """Verify failed legacy auth is rejected."""
        payload = {
            "provider_thr": "THR1234567890",
            "auth_secret": "wrong_secret"
        }

        with patch('server.validate_effective_auth') as mock_auth:
            mock_auth.return_value = (False, {}, "invalid_auth")
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "add_liquidity")

            # Should reject
            assert ok is False
            assert err["error"] == "invalid_auth"

    def test_signature_verification_exception_handled(self):
        """Verify exceptions during signature verification are caught."""
        payload = {
            "provider_thr": "THR1234567890",
            "action": "create_pool",
            "signed_tx": {
                "from": "THR1234567890",
                "signature": "0x789012"
            }
        }

        with patch('server.wallet_v1_production_final') as mock_v1:
            mock_v1.verify_signed_transaction_core.side_effect = RuntimeError("secp256k1 library error")
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

            # Should gracefully reject with error detail
            assert ok is False
            assert "signature_verification_failed" in err.get("error", "")

    def test_signed_tx_not_dict_rejected(self):
        """Verify non-dict signed_tx is rejected."""
        payload = {
            "provider_thr": "THR1234567890",
            "action": "create_pool",
            "signed_tx": "0xabcd1234"  # String instead of dict
        }

        ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

        # Should reject non-dict
        assert ok is False
        assert "must be an object" in err["message"]

    def test_public_key_signature_merged_into_signed_tx(self):
        """Verify public_key and signature fields are merged into signed_tx before verification."""
        payload = {
            "provider_thr": "THR1234567890",
            "action": "create_pool",
            "signed_tx": {
                "from": "THR1234567890",
                "action": "create_pool"
                # publicKey and signature will be added separately
            },
            "public_key": "0x123456",
            "signature": "0x789012"
        }

        with patch('server.wallet_v1_production_final') as mock_v1:
            mock_v1.verify_signed_transaction_core.return_value = (True, None)
            ok, err, wallet = verify_pool_wallet_v1_or_legacy(payload, "create_pool")

            # Verify the verifier was called with merged signed_tx
            assert ok is True
            called_with = mock_v1.verify_signed_transaction_core.call_args[0][0]
            assert called_with.get("publicKey") == "0x123456"
            assert called_with.get("signature") == "0x789012"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

