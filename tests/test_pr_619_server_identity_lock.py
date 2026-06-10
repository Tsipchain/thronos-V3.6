"""
PR #619: Server Identity Lock - Canonical Address Immutability
Tests that the pledge endpoint never creates new canonical if one already exists
"""
import pytest
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app, PLEDGE_CHAIN, WHITELIST_FILE, load_json, save_json


class TestServerIdentityLock:
    """Test canonical address immutability at pledge/wallet boundary"""

    @pytest.fixture
    def client(self):
        """Create Flask test client"""
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def cleanup_pledges(self):
        """Clean up pledges and whitelist before/after test"""
        # Save original state
        original_pledges = load_json(PLEDGE_CHAIN, [])
        original_whitelist = load_json(WHITELIST_FILE, [])

        # Before test: clear and whitelist test addresses
        test_btc_addrs = [
            "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD",
            "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",
        ]
        save_json(PLEDGE_CHAIN, [])
        save_json(WHITELIST_FILE, test_btc_addrs)

        yield

        # After test: restore original state
        save_json(PLEDGE_CHAIN, original_pledges)
        save_json(WHITELIST_FILE, original_whitelist)

    def test_pledge_does_not_create_new_if_canonical_exists(self, client, cleanup_pledges):
        """
        CRITICAL TEST A: Pledge endpoint must NOT create new canonical if one already exists

        Scenario:
          1. First pledge call for BTC address → creates canonical=A, created=true
          2. Second pledge call (same BTC address) → returns canonical=A, created=false
          3. NO new canonical generated, NO rotation

        Security: Prevents canonical rotation at the pledge/write boundary
        """
        btc_address = "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD"
        pledge_text = "I pledge to thronos"

        # FIRST PLEDGE: should create canonical
        response1 = client.post("/pledge_submit",
            json={
                "btc_address": btc_address,
                "pledge_text": pledge_text,
                "passphrase": "test1234"
            }
        )

        assert response1.status_code == 200, f"First pledge failed: {response1.data}"
        data1 = response1.get_json()

        # Verify first response has correct schema
        assert "canonical_v1_address" in data1, "Response missing canonical_v1_address"
        assert "created" in data1, "Response missing created field"
        assert data1["created"] == True, "First pledge should have created=true"
        assert "status" in data1, "Response missing status field"
        assert data1["status"] == "newly_created", f"Expected status=newly_created, got {data1['status']}"

        canonical_a = data1["canonical_v1_address"]
        assert canonical_a.startswith("THR"), f"Invalid canonical format: {canonical_a}"

        print(f"✅ FIRST PLEDGE: created=true, canonical={canonical_a}")

        # SECOND PLEDGE: should NOT create new canonical (same BTC address)
        response2 = client.post("/pledge_submit",
            json={
                "btc_address": btc_address,
                "pledge_text": pledge_text,
                "passphrase": "test1234"
            }
        )

        assert response2.status_code == 200, f"Second pledge failed: {response2.data}"
        data2 = response2.get_json()

        # Verify second response
        assert "canonical_v1_address" in data2, "Response missing canonical_v1_address"
        assert "created" in data2, "Response missing created field"
        assert data2["created"] == False, f"Second pledge should have created=false, got {data2['created']}"
        assert "status" in data2, "Response missing status field"
        assert data2["status"] == "already_has_canonical", f"Expected status=already_has_canonical, got {data2['status']}"

        canonical_b = data2["canonical_v1_address"]

        # CRITICAL CHECK: canonical must be SAME
        assert canonical_a == canonical_b, \
            f"SECURITY BREACH: Canonical rotated! First: {canonical_a}, Second: {canonical_b}"

        print(f"✅ SECOND PLEDGE: created=false, canonical={canonical_b} (SAME as first)")
        print(f"✅ TEST PASSED: Canonical immutable across repeat pledges")

    def test_different_btc_addresses_get_different_canonicals(self, client, cleanup_pledges):
        """
        Verify that different BTC addresses get different canonicals (normal case)
        This ensures the guard only applies to the SAME user, not all users
        """
        btc_addr_1 = "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD"
        btc_addr_2 = "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"
        pledge_text = "I pledge to thronos"

        # First user pledges
        response1 = client.post("/pledge_submit",
            json={"btc_address": btc_addr_1, "pledge_text": pledge_text, "passphrase": "test1234"}
        )
        data1 = response1.get_json()
        canonical_1 = data1["canonical_v1_address"]

        # Second user pledges (different BTC address)
        response2 = client.post("/pledge_submit",
            json={"btc_address": btc_addr_2, "pledge_text": pledge_text, "passphrase": "test1234"}
        )
        data2 = response2.get_json()
        canonical_2 = data2["canonical_v1_address"]

        # Both should be created=true
        assert data1["created"] == True
        assert data2["created"] == True

        # But different canonicals
        assert canonical_1 != canonical_2, \
            f"Different users should get different canonicals: {canonical_1} vs {canonical_2}"

        print(f"✅ Different users get different canonicals (as expected)")

    def test_response_schema_is_consistent(self, client, cleanup_pledges):
        """
        TEST: All pledge responses have consistent schema with required fields
        """
        btc_address = "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD"

        # Create pledge
        response = client.post("/pledge_submit",
            json={"btc_address": btc_address, "pledge_text": "test", "passphrase": "test"}
        )
        data = response.get_json()

        # Check required fields are present in every response
        required_fields = ["ok", "canonical_v1_address", "created", "status", "thr_address"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            assert data[field] is not None, f"Field {field} is null"

        print(f"✅ Response schema consistent: all required fields present")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
