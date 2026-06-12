"""
Documentation: Roadmap V3 & Whitepaper Wallet V1 Alignment Tests

Verifies that:
1. New roadmap_v3.html page exists and contains Wallet V1 architecture
2. /roadmap/v3 and /roadmap/wallet-v1 routes serve the page
3. /api/roadmap/status endpoint returns module status
4. Original roadmap still available and unchanged (backward compatible)
5. Documentation reflects current Phase 1, 2, 3, 4, 5, 6 status
6. Digital Legacy, Mining V1, Bridge, Pythia documented
7. External services inventory complete
"""

import pytest
import json
from pathlib import Path


class TestRoadmapV3Page:
    """Test new Wallet V1 roadmap page."""

    def test_roadmap_v3_html_exists(self):
        """Verify roadmap_v3.html template exists."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        assert template_file.exists(), "roadmap_v3.html template not found"

    def test_roadmap_v3_page_title(self):
        """Verify page has correct title."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Wallet V1" in content, "Page should mention Wallet V1"
        assert "Stage 3" in content, "Page should reference Stage 3"

    def test_roadmap_v3_contains_wallet_v1_section(self):
        """Verify page contains Wallet V1 Core section."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Canonical V1 Address" in content, "Should explain canonical address"
        assert "Bound Signer" in content, "Should explain bound signers"
        assert "Recovery Kit" in content, "Should document recovery kit"
        assert "PIN Protected" in content, "Should mention PIN protection"

    def test_roadmap_v3_contains_signed_services(self):
        """Verify page documents signed service requests."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Swap Signing" in content, "Should document swap signing"
        assert "Pools Signing" in content, "Should document pools signing"
        assert "Send Signing" in content, "Should document send signing"
        assert "Bridge Signing" in content, "Should document bridge signing"
        assert "AI Credits" in content, "Should document AI credits"
        assert "IoT Telemetry" in content, "Should document IoT"
        assert "Music Telemetry" in content, "Should document music telemetry"

    def test_roadmap_v3_contains_mining_v1(self):
        """Verify page documents Mining V1."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Mining V1" in content or "Pledge-Native" in content, "Should document Mining V1"
        assert "canonical_v1_address" in content, "Should mention canonical address as reward destination"
        assert "Stratum" in content, "Should mention Stratum protocol"

    def test_roadmap_v3_contains_digital_legacy(self):
        """Verify page documents Digital Legacy."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Digital Legacy" in content or "Digital Will" in content, "Should document Digital Legacy"
        assert "Heir" in content, "Should mention heirs"
        assert "Charity Pool" in content, "Should mention charity pool"

    def test_roadmap_v3_contains_bridge_section(self):
        """Verify page documents Bridge architecture."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "BTC Watcher" in content, "Should document BTC watcher"
        assert "Burn-to-Mint" in content or "burn.*mint" in content.lower(), "Should document burn-to-mint"
        assert "Vault" in content, "Should mention vault"

    def test_roadmap_v3_contains_pythia_ai(self):
        """Verify page documents Pythia AI Oracle."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Pythia" in content or "Oracle" in content, "Should document Pythia/Oracle"
        assert "Liquidity Agent" in content, "Should mention liquidity agent"

    def test_roadmap_v3_module_inventory(self):
        """Verify page includes module status table."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Module" in content, "Should have module table"
        assert "Status" in content, "Should show status column"
        assert "Live" in content or "live" in content, "Should show Live status"
        assert "Planned" in content or "planned" in content, "Should show Planned status"


class TestRoadmapV3Routes:
    """Test new roadmap routes."""

    def test_roadmap_v3_route_exists(self):
        """Verify /roadmap/v3 route defined."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()
        assert "@app.route(\"/roadmap/v3\")" in content, "Route /roadmap/v3 not found"

    def test_roadmap_wallet_v1_route_exists(self):
        """Verify /roadmap/wallet-v1 route defined."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()
        assert "@app.route(\"/roadmap/wallet-v1\")" in content, "Route /roadmap/wallet-v1 not found"

    def test_roadmap_v3_renders_template(self):
        """Verify routes render roadmap_v3.html."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the route function
        start = content.find("def roadmap_v3_page()")
        end = content.find("\ndef ", start + 1)
        func_code = content[start:end]

        assert "roadmap_v3.html" in func_code, "Should render roadmap_v3.html template"


class TestRoadmapStatusAPI:
    """Test /api/roadmap/status endpoint."""

    def test_api_roadmap_status_exists(self):
        """Verify /api/roadmap/status endpoint defined."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()
        assert "@app.route(\"/api/roadmap/status\"" in content, "API endpoint not found"

    def test_api_roadmap_status_returns_json(self):
        """Verify endpoint returns JSON response."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the endpoint function
        start = content.find("def api_roadmap_status()")
        end = content.find("\n@app.route", start)
        if end == -1:
            end = content.find("\ndef ", start + 1)
        func_code = content[start:end]

        assert "jsonify" in func_code, "Should return JSON"
        assert "ok" in func_code.lower(), "Should have 'ok' field"

    def test_api_roadmap_status_has_modules(self):
        """Verify endpoint includes module status."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Extract the endpoint function
        start = content.find("def api_roadmap_status()")
        end = content.find("return jsonify", start)
        func_code = content[start:end]

        expected_modules = [
            "wallet_v1", "swap", "pools", "send",
            "ai_credits", "iot_telemetry", "music_telemetry",
            "mining_v1", "digital_legacy", "bridge", "pythia"
        ]

        for module in expected_modules:
            assert module in func_code, f"Module {module} not documented in endpoint"

    def test_api_roadmap_status_has_status_legend(self):
        """Verify endpoint includes status legend."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the endpoint function
        start = content.find("def api_roadmap_status()")
        end = content.find("return jsonify", start)
        func_code = content[start:end]

        assert "live" in func_code.lower(), "Should explain 'live' status"
        assert "planned" in func_code.lower(), "Should explain 'planned' status"
        assert "in_progress" in func_code.lower(), "Should explain 'in_progress' status"

    def test_api_roadmap_status_has_progress_tracking(self):
        """Verify endpoint includes phase progress."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the endpoint function
        start = content.find("def api_roadmap_status()")
        end = content.find("return jsonify", start)
        func_code = content[start:end]

        assert "progress" in func_code.lower(), "Should track phase progress"
        assert "phase" in func_code.lower(), "Should mention phases"


class TestBackwardCompatibility:
    """Test that original roadmap still works."""

    def test_original_roadmap_still_exists(self):
        """Verify roadmap.html still exists."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap.html"
        assert template_file.exists(), "Original roadmap.html should still exist"

    def test_roadmap_route_still_works(self):
        """Verify /roadmap route still defined."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()
        assert "@app.route(\"/roadmap\")" in content, "Original /roadmap route should exist"

    def test_roadmap_renders_original_template(self):
        """Verify /roadmap still renders roadmap.html."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the original route function
        start = content.find("def roadmap_page():")
        end = content.find("\ndef ", start + 1)
        func_code = content[start:end]

        assert "roadmap.html" in func_code, "Should render original roadmap.html"

    def test_whitepaper_still_exists(self):
        """Verify whitepaper.html still exists."""
        template_file = Path(__file__).parent.parent / "templates" / "whitepaper.html"
        assert template_file.exists(), "Whitepaper should still exist"


class TestDocumentationAlignment:
    """Test that documentation aligns with implementation."""

    def test_roadmap_v3_mentions_public_key_format(self):
        """Verify documentation mentions public key format validation."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Public Key Format" in content or "compressed" in content.lower(), \
            "Should document public key format"

    def test_roadmap_v3_mentions_secp256k1(self):
        """Verify documentation mentions secp256k1 signature format."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "secp256k1" in content, "Should mention secp256k1 format"

    def test_roadmap_v3_mentions_recovery_kit_encryption(self):
        """Verify documentation mentions encrypted recovery kit."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Recovery Kit" in content, "Should mention Recovery Kit"
        assert "encrypted" in content.lower(), "Should mention encryption"

    def test_roadmap_v3_references_endpoints(self):
        """Verify documentation includes endpoint references."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "/api/" in content, "Should reference API endpoints"

    def test_api_status_endpoint_references_live_routes(self):
        """Verify API status mentions live routes."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the endpoint
        start = content.find("def api_roadmap_status()")
        end = content.find("return jsonify", start)
        func_code = content[start:end]

        assert "/api/swap/execute" in func_code, "Should reference swap endpoint"
        assert "/api/v1/pools" in func_code, "Should reference pools endpoint"


class TestExternalServicesInventory:
    """Test that external services are documented."""

    def test_roadmap_v3_includes_external_services(self):
        """Verify documentation includes external services section."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()

        services = [
            "VerifyID", "L2E", "Music", "Crypto Hunters",
            "IoT", "Bridge"
        ]

        for service in services:
            assert service in content, f"Should mention {service}"

    def test_api_status_includes_service_endpoints(self):
        """Verify API status lists service endpoints."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find the endpoint
        start = content.find("def api_roadmap_status()")
        end = content.find("return jsonify", start)
        func_code = content[start:end]

        assert "/music" in func_code or "music" in func_code.lower(), \
            "Should list music endpoints"
        assert "/hunters" in func_code or "hunters" in func_code.lower(), \
            "Should list crypto hunters endpoints"
        assert "/iot" in func_code or "iot" in func_code.lower(), \
            "Should list IoT endpoints"


class TestPhaseProgress:
    """Test phase progress tracking."""

    def test_api_status_tracks_phase_1(self):
        """Verify Phase 1 is marked as complete."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_roadmap_status()")
        end = content.find("return jsonify", start)
        func_code = content[start:end]

        assert "phase_1" in func_code.lower(), "Should track Phase 1"
        assert "100" in func_code, "Phase 1 should be 100% complete"

    def test_api_status_tracks_phase_2(self):
        """Verify Phase 2 progress tracked."""
        server_file = Path(__file__).parent.parent / "server.py"
        content = server_file.read_text()

        # Find endpoint
        start = content.find("def api_roadmap_status()")
        end = content.find("return jsonify", start)
        func_code = content[start:end]

        assert "phase_2" in func_code.lower(), "Should track Phase 2"
        assert "40" in func_code, "Phase 2 should be ~40% complete"

    def test_roadmap_v3_shows_phase_status(self):
        """Verify page shows phase completion status."""
        template_file = Path(__file__).parent.parent / "templates" / "roadmap_v3.html"
        content = template_file.read_text()
        assert "Complete" in content or "Live" in content, "Should show completion status"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
