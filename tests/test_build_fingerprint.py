"""
Test Build Fingerprint Endpoints

Verifies that /api/health and /api/build return build/commit information.
"""

import pytest
from pathlib import Path


class TestBuildFingerprint:
    """Test build fingerprint endpoints."""

    def test_api_health_includes_build_info(self):
        """Verify /api/health endpoint includes build_id and git_commit."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Check that /api/health includes build info
        health_start = content.find("@app.route(\"/api/health\"")
        health_end = content.find("@app.route(", health_start + 1)
        health_func = content[health_start:health_end]

        assert "build_id" in health_func, "Should include build_id in health response"
        assert "git_commit" in health_func, "Should include git_commit in health response"
        assert "build_time" in health_func, "Should include build_time in health response"

    def test_api_build_endpoint_exists(self):
        """Verify /api/build endpoint exists."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "/api/build" in content, "Should have /api/build endpoint"
        assert "def api_build()" in content, "Should have api_build function"

    def test_api_build_returns_required_fields(self):
        """Verify /api/build returns build_id, git_commit, build_time."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        build_start = content.find("def api_build()")
        build_end = content.find("@app.route", build_start + 1)
        build_func = content[build_start:build_end]

        assert "build_id" in build_func, "Should return build_id"
        assert "git_commit" in build_func, "Should return git_commit"
        assert "build_time" in build_func, "Should return build_time"

    def test_build_id_initialized(self):
        """Verify BUILD_ID variable is initialized."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "BUILD_ID" in content, "Should initialize BUILD_ID"
        assert "GIT_COMMIT_SHORT" in content, "Should initialize GIT_COMMIT_SHORT"
        assert "BUILD_TIMESTAMP" in content, "Should initialize BUILD_TIMESTAMP"

    def test_build_info_in_footer(self):
        """Verify footer has build-info div."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        assert 'id="build-info"' in content, "Footer should have build-info div"
        assert "hydrateBuild()" in content, "Should call hydrateBuild function"

    def test_hydrate_build_fetches_from_api(self):
        """Verify hydrateBuild fetches from /api/health."""
        base_html = Path(__file__).parent.parent / "templates" / "base.html"
        content = base_html.read_text()

        hydrate_start = content.find("function hydrateBuild()")
        # Search for the next closing of a bigger block or function
        hydrate_section = content[hydrate_start:hydrate_start + 2000]

        assert "/api/health" in hydrate_section, "Should fetch from /api/health"
        # Check that the function looks for either build_id or git_commit
        assert ("build_id" in hydrate_section or "git_commit" in hydrate_section), \
            "Should check for build_id or git_commit in response"

    def test_build_id_format(self):
        """Verify BUILD_ID has expected format (sha-timestamp)."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        # Find BUILD_ID initialization
        build_id_line = None
        for line in content.split('\n'):
            if 'BUILD_ID = ' in line and '==' not in line:
                build_id_line = line
                break

        assert build_id_line is not None, "Should initialize BUILD_ID"
        assert 'GIT_COMMIT_SHORT' in build_id_line, "BUILD_ID should include GIT_COMMIT_SHORT"
        assert 'BUILD_TIMESTAMP' in build_id_line, "BUILD_ID should include BUILD_TIMESTAMP"


class TestBuildFingerprintIntegration:
    """Test that build info is properly integrated."""

    def test_git_commit_short_function_exists(self):
        """Verify _get_git_commit_short function exists."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        assert "def _get_git_commit_short():" in content, "Should have function to get short git SHA"

    def test_both_endpoints_accessible(self):
        """Verify both /api/health and /api/build are defined."""
        server_py = Path(__file__).parent.parent / "server.py"
        content = server_py.read_text()

        health_count = content.count('@app.route("/api/health"')
        build_count = content.count('@app.route("/api/build"')

        assert health_count > 0, "Should have /api/health endpoint"
        assert build_count > 0, "Should have /api/build endpoint"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
