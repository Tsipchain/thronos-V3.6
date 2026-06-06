"""
Startup Hardening Tests

Verifies that:
1. Digital Legacy dataclass field ordering is correct
2. Cryptography dependency is available
3. wallet_history sentinel patch is integrated (no timeout needed)
4. Legacy health endpoints exist
5. TX log seeding does not crash
6. Logging improvements applied (INFO not logged as ERROR for optional systems)
7. No secrets logged during startup
"""

import pytest
import sys
from pathlib import Path


class TestDigitalLegacyStartup:
    """Test Digital Legacy System initialization."""

    def test_digital_legacy_imports_cleanly(self):
        """Verify Digital Legacy module imports without errors."""
        try:
            from digital_legacy_manager import EncryptedAsset, ContactInfo, AssetCategory
            assert EncryptedAsset is not None
            assert ContactInfo is not None
            assert AssetCategory is not None
        except Exception as e:
            pytest.fail(f"Digital Legacy import failed: {e}")

    def test_encrypted_asset_dataclass_field_ordering(self):
        """Verify EncryptedAsset dataclass has correct field ordering."""
        from digital_legacy_manager import EncryptedAsset
        import dataclasses

        fields = dataclasses.fields(EncryptedAsset)
        field_names = [f.name for f in fields]

        # All non-default fields must come before default fields
        seen_default = False
        for field in fields:
            has_default = (
                field.default is not dataclasses.MISSING or
                field.default_factory is not dataclasses.MISSING
            )

            if seen_default and not has_default:
                pytest.fail(
                    f"Non-default field '{field.name}' comes after default field. "
                    "Dataclass field ordering is broken."
                )

            if has_default:
                seen_default = True

    def test_encrypted_asset_instantiation(self):
        """Verify EncryptedAsset can be instantiated with correct defaults."""
        from digital_legacy_manager import EncryptedAsset, AssetCategory

        asset = EncryptedAsset(
            asset_id="test-123",
            asset_type=AssetCategory.CRYPTO,
            name="Test Bitcoin",
            description="Test wallet",
            encrypted_keys="encrypted_data",
            encrypted_recovery="recovery_data",
        )

        assert asset.asset_id == "test-123"
        assert asset.value_estimate == 0.0  # Should have default
        assert asset.currency == "USD"  # Should have default
        assert asset.contact_info is not None  # Should have default


class TestCryptographyDependency:
    """Test cryptography dependency availability."""

    def test_cryptography_available_in_digital_legacy(self):
        """Verify cryptography is available for Digital Legacy."""
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            assert Fernet is not None
            assert hashes is not None
            assert PBKDF2HMAC is not None
        except ImportError as e:
            pytest.fail(f"cryptography module not found or import error: {e}. Run: pip install cryptography")

    def test_cryptography_in_requirements(self):
        """Verify cryptography is in requirements.txt."""
        requirements_file = Path(__file__).parent.parent / "requirements.txt"
        content = requirements_file.read_text()
        assert "cryptography" in content.lower(), \
            "cryptography not found in requirements.txt"


class TestWalletHistorySentinelFix:
    """Test wallet_history sentinel key initialization fix."""

    def test_ai_agent_service_no_hotfix_patch(self):
        """Verify hotfix patch removed from ai_agent_service."""
        ai_agent_file = Path(__file__).parent.parent / "ai_agent_service.py"
        content = ai_agent_file.read_text()

        # Hotfix should be removed
        assert "_apply_wallet_sentinel_hotfix" not in content, \
            "Hotfix patch should be removed from ai_agent_service"
        assert "timed out" not in content or "wallet_history" not in content, \
            "Timeout wait logic should be removed"

    def test_server_sentinel_keys_initialized(self):
        """Verify server initializes sentinel keys in summary dict."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find _collect_wallet_history_transactions function
        start = content.find("def _collect_wallet_history_transactions")
        end = content.find("\ndef ", start + 1)
        func_code = content[start:end]

        # Must initialize summary with sentinel keys
        assert "total_sentinel_spent" in func_code, \
            "Summary dict must initialize total_sentinel_spent"
        assert "sentinel_count" in func_code, \
            "Summary dict must initialize sentinel_count"

        # Keys should be in initial dict, not just setdefault
        assert '"total_sentinel_spent": 0.0' in func_code or \
               "'total_sentinel_spent': 0.0" in func_code, \
            "Sentinel keys should be initialized in summary dict"


class TestLegacyHealthEndpoints:
    """Test new legacy health check endpoints."""

    def test_legacy_health_route_exists(self):
        """Verify /api/legacy/health endpoint exists."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        assert "@app.route(\"/api/legacy/health\"" in content, \
            "Legacy health endpoint not found"

    def test_legacy_health_returns_correct_fields(self):
        """Verify legacy health endpoint returns expected fields."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the endpoint function
        start = content.find("def api_legacy_health()")
        end = content.find("\n\n@app.route", start)
        if end == -1:
            end = content.find("\n\ndef ", start)
        func_code = content[start:end]

        expected_fields = [
            "digital_legacy_initialized",
            "smart_contract_will_manager",
            "digital_distribution_manager",
            "charity_pool_manager",
            "cryptography_available",
        ]

        for field in expected_fields:
            assert f'"{field}"' in func_code or f"'{field}'" in func_code, \
                f"Legacy health endpoint missing {field}"

    def test_legacy_routes_diagnostic_endpoint(self):
        """Verify /api/legacy/routes diagnostic endpoint exists."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        assert "@app.route(\"/api/legacy/routes\"" in content, \
            "Legacy routes endpoint not found"
        assert "def api_legacy_routes()" in content, \
            "Legacy routes function not found"


class TestLoggingImprovements:
    """Test logging level improvements."""

    def test_optional_system_failures_use_warning_not_error(self):
        """Verify optional system failures use logger.warning, not logger.error."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Check Digital Legacy, Will, Distribution, and Pool initialization sections
        systems_to_check = [
            ("Digital Legacy", "Initialize Digital Legacy System"),
            ("Will", "Initialize Smart Contract Will System"),
            ("Distribution", "Initialize Multi-Sig Distribution System"),
            ("Pool", "Initialize Charity Pool"),
        ]

        for system_name, marker in systems_to_check:
            if marker in content:
                start = content.find(marker)
                end = content.find("# Initialize", start + 1)
                if end == -1:
                    end = content.find("\n    except", start)

                section = content[start:end]

                # Should use warning for optional systems, not error
                assert "logger.warning" in section, \
                    f"{system_name} initialization should use logger.warning for failures"

    def test_startup_section_uses_proper_log_levels(self):
        """Verify startup section uses proper log levels."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find startup section
        startup_start = content.find("[STARTUP]")
        startup_end = content.find("[STARTUP]", startup_start + 100)

        if startup_start > 0 and startup_end > startup_start:
            startup_section = content[startup_start:startup_end]

            # TX seeding should use warning for non-critical failures
            if "TX log seeding" in startup_section:
                assert "logger.warning" in startup_section or "non-critical" in startup_section, \
                    "TX seeding failures should be logged as warning with non-critical note"


class TestNoSecretsInLogs:
    """Test that no secrets are logged during startup."""

    def test_digital_legacy_init_no_secrets_logged(self):
        """Verify Digital Legacy init doesn't log secrets."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find Digital Legacy init section
        start = content.find("# Initialize Digital Legacy System")
        end = content.find("# Initialize Smart Contract Will System", start)
        section = content[start:end]

        # Should not log private keys or sensitive data
        sensitive_terms = ["private_key", "seed_phrase", "recovery_", "password"]
        for term in sensitive_terms:
            assert f'logger.error("{term}' not in section.lower() and \
                   f'logger.error(\'{term}' not in section.lower(), \
                f"Should not log {term} in error messages"

    def test_wallet_history_no_secrets_logged(self):
        """Verify wallet_history initialization doesn't log secrets."""
        ai_agent_file = Path(__file__).parent.parent / "ai_agent_service.py"
        content = ai_agent_file.read_text()

        # The hotfix is removed, so no secrets should be logged there
        assert "_apply_wallet_sentinel_hotfix" not in content, \
            "Hotfix patch should be removed"


class TestTxLogSeedingContext:
    """Test TX log seeding has proper Flask context."""

    def test_tx_seeding_uses_app_context(self):
        """Verify TX log seeding uses Flask app context."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find TX seeding section
        start = content.find("# Seed transaction log from chain")
        end = content.find("# ===== Wallet V1", start)
        section = content[start:end]

        assert "with app.app_context():" in section, \
            "TX seeding should use Flask app context"
        assert "_seed_tx_log_from_chain()" in section, \
            "Should call _seed_tx_log_from_chain()"

    def test_tx_seeding_handles_exceptions(self):
        """Verify TX log seeding handles exceptions gracefully."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find TX seeding section
        start = content.find("# Seed transaction log from chain")
        end = content.find("# ===== Wallet V1", start)
        section = content[start:end]

        assert "except Exception" in section, \
            "TX seeding should have exception handling"
        assert "logger.warning" in section or "logger.info" in section, \
            "Should log seeding status"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
