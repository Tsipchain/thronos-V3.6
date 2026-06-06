"""
Wallet V1 Music Level Capability Tests.

Verifies that music unlock uses Wallet V1 active binding state,
not legacy V0 thr_secret flag.

Security requirements:
1. Stale thr_secret alone does NOT unlock music
2. Active binding + encrypted key + runtime unlocked DOES unlock music
3. Backend capability check verifies active binding
4. Frontend checks encrypted key + runtime signing material (not thr_secret)
"""

import pytest
import json
from pathlib import Path


def test_music_unlock_does_not_use_legacy_thr_secret():
    """Verify loadMusicTab does NOT use legacy thr_secret for unlock."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    # Find loadMusicTab function
    assert "async function loadMusicTab()" in content, "loadMusicTab function not found"

    # Extract loadMusicTab code
    start = content.find("async function loadMusicTab()")
    end = content.find("\n}\n", start) + 3  # Include closing brace
    load_music_code = content[start:end]

    # Verify thr_secret is NOT used for unlock check
    assert "localStorage.getItem('thr_secret')" not in load_music_code, \
        "loadMusicTab must NOT use legacy thr_secret for runtime unlock"

    # Verify walletSession.isUnlockedFor() IS used
    assert "walletSession.isUnlockedFor" in load_music_code, \
        "loadMusicTab must use walletSession.isUnlockedFor() for Wallet V1 runtime check"

    # Verify hasRuntimeSigningMaterial variable name is used
    assert "hasRuntimeSigningMaterial" in load_music_code, \
        "loadMusicTab must check hasRuntimeSigningMaterial (V1 signing state)"


def test_music_unlock_requires_three_conditions():
    """Verify music unlock requires: binding + encrypted_key + runtime_signing."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    # Find loadMusicTab function
    start = content.find("async function loadMusicTab()")
    end = content.find("\n}\n", start) + 3
    load_music_code = content[start:end]

    # Condition 1: Backend capability check (active binding)
    assert "checkWalletV1MusicCapability" in load_music_code, \
        "Music unlock must check backend capability (active binding)"
    assert "canUnlockMusic" in load_music_code, \
        "Must store backend binding check result"

    # Condition 2: Encrypted key exists
    assert "wallet_v1_encrypted_priv" in load_music_code, \
        "Music unlock must check for encrypted key"
    assert "hasEncryptedKey" in load_music_code, \
        "Must store encrypted key check result"

    # Condition 3: Runtime signing material
    assert "hasRuntimeSigningMaterial" in load_music_code, \
        "Music unlock must check for V1 runtime signing material"

    # All three must be combined with AND logic
    assert "isMusicUnlocked = canUnlockMusic && hasEncryptedKey && hasRuntimeSigningMaterial" in load_music_code, \
        "Music unlock must require ALL three conditions: binding AND encrypted_key AND runtime_signing"


def test_music_capability_endpoint_exists():
    """Verify GET /api/wallet/v1/music/capability endpoint is implemented."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()

    assert '@app.route("/api/wallet/v1/music/capability"' in content, \
        "Music capability endpoint not found"

    # Extract endpoint code
    start = content.find('@app.route("/api/wallet/v1/music/capability"')
    end = content.find("\n@app.route", start + 1)
    endpoint_code = content[start:end]

    # Verify it checks for active binding
    assert "has_active_binding" in endpoint_code, \
        "Endpoint must return has_active_binding flag"

    # Verify it doesn't check legacy secrets
    assert "thr_secret" not in endpoint_code, \
        "Endpoint must NOT check legacy thr_secret"

    # Verify safe logging (no secrets logged)
    assert "private_key" not in endpoint_code.lower() or "Never logs" in endpoint_code, \
        "Endpoint must not log private keys"


def test_music_capability_endpoint_validates_address():
    """Verify endpoint validates canonical address format."""
    server_py = Path(__file__).parent.parent / "server.py"
    content = server_py.read_text()

    # Extract endpoint code
    start = content.find('@app.route("/api/wallet/v1/music/capability"')
    end = content.find("\n@app.route", start + 1)
    endpoint_code = content[start:end]

    # Must validate THR prefix
    assert '"THR"' in endpoint_code or "startswith" in endpoint_code, \
        "Endpoint must validate THR address format"

    # Must handle missing address gracefully
    assert "no_canonical_address" in endpoint_code, \
        "Endpoint must handle missing address case"


def test_music_unlock_error_messages():
    """Verify appropriate error messages for different unlock failure modes."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    # Find loadMusicTab function
    start = content.find("async function loadMusicTab()")
    end = content.find("\n}\n", start) + 3
    load_music_code = content[start:end]

    # Case 1: No binding or no recovery kit
    assert "Restore Recovery Kit or unlock this device" in load_music_code, \
        "Must show recovery kit message when no binding"

    # Case 2: Wallet is locked (no runtime signing material)
    assert "Unlock Wallet V1 to enable Music Level" in load_music_code, \
        "Must show unlock prompt when wallet is locked"

    # Case 3: Music not available
    assert "Music Level not available" in load_music_code, \
        "Must show generic unavailable message for other failures"


def test_checkWalletV1MusicCapability_function():
    """Verify checkWalletV1MusicCapability calls backend endpoint."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    assert "async function checkWalletV1MusicCapability" in content, \
        "checkWalletV1MusicCapability function not found"

    # Extract function code
    start = content.find("async function checkWalletV1MusicCapability")
    end = content.find("\n}", start) + 2
    func_code = content[start:end]

    # Must call backend capability endpoint
    assert "/api/wallet/v1/music/capability" in func_code, \
        "Function must call capability endpoint"

    # Must validate address format
    assert "THR" in func_code, \
        "Function must validate address format"

    # Must handle errors gracefully
    assert "try" in func_code and "catch" in func_code, \
        "Function must handle errors gracefully"

    # Must check has_active_binding in response
    assert "has_active_binding" in func_code, \
        "Function must check has_active_binding in response"


def test_telemetry_placeholder_architecture():
    """Verify telemetry placeholder for future signed music tracking."""
    base_html = Path(__file__).parent.parent / "templates" / "base.html"
    content = base_html.read_text()

    # Telemetry placeholder must exist
    assert "MUSIC_TELEMETRY_SCHEMA_VERSION" in content, \
        "Telemetry placeholder architecture not found"

    # Extract entire placeholder (including comment block with security info)
    start = content.find("// ========== Placeholder: Signed Music Telemetry")
    end = content.find("// End placeholder", start) + 50
    telemetry_code = content[start:end]

    # Must mention security requirements
    assert "Never sends" in telemetry_code, \
        "Telemetry must document what NOT to send"

    # Must mention consent requirement for geohash
    assert "opt-in" in telemetry_code.lower() or "consent" in telemetry_code.lower(), \
        "Telemetry must mention opt-in for location data"

    # Must NOT have raw location by default
    assert "no raw location" in telemetry_code.lower() or "no raw location by default" in telemetry_code, \
        "Telemetry must explicitly state no raw location by default"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
