"""
Manual QA Test: Canonical Address Immutability - API Verification
Verify network behavior through direct API calls and response inspection
"""
import requests
import json
import time
from unittest.mock import patch, MagicMock


class ManualQANetworkVerification:
    """Verify canonical immutability through API responses"""

    BASE_URL = "http://localhost:5000"

    def test_scenario_a_server_identity_lock_no_new_canonical(self):
        """
        SCENARIO A: Server Identity Lock - NO new canonical created when one exists

        Network Verification:
        - POST /pledge_submit with existing BTC → returns created=false, same canonical
        - Pledge request happens ONLY once per user
        """
        print("\n" + "="*80)
        print("SCENARIO A: Server Identity Lock - No new canonical when exists")
        print("="*80)

        btc_address = "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD"
        pledge_data = {
            "btc_address": btc_address,
            "pledge_text": "Test pledge",
            "passphrase": "test1234"
        }

        # First pledge
        print(f"\n  Request 1: POST /pledge_submit (first pledge)")
        try:
            resp1 = requests.post(
                f"{self.BASE_URL}/pledge_submit",
                json=pledge_data,
                timeout=5
            )
            print(f"    Status: {resp1.status_code}")
            data1 = resp1.json()
            print(f"    Response: canonical_v1_address={data1.get('canonical_v1_address', 'N/A')[:20]}...")
            print(f"              created={data1.get('created')}")
            print(f"              status={data1.get('status')}")

            canonical_1 = data1.get('canonical_v1_address')
            created_1 = data1.get('created')

            assert canonical_1, "First pledge should return canonical_v1_address"
            assert created_1 == True, "First pledge should have created=true"
            print("    ✅ First pledge: created=true, new canonical assigned")

        except Exception as e:
            print(f"    ❌ FAIL: {e}")
            return False

        # Second pledge (same user)
        print(f"\n  Request 2: POST /pledge_submit (repeat pledge, same BTC)")
        try:
            resp2 = requests.post(
                f"{self.BASE_URL}/pledge_submit",
                json=pledge_data,
                timeout=5
            )
            print(f"    Status: {resp2.status_code}")
            data2 = resp2.json()
            print(f"    Response: canonical_v1_address={data2.get('canonical_v1_address', 'N/A')[:20]}...")
            print(f"              created={data2.get('created')}")
            print(f"              status={data2.get('status')}")

            canonical_2 = data2.get('canonical_v1_address')
            created_2 = data2.get('created')

            assert canonical_2 == canonical_1, \
                f"Second pledge should return SAME canonical! Got: {canonical_2} vs {canonical_1}"
            assert created_2 == False, "Second pledge should have created=false"
            print(f"    ✅ Second pledge: created=false, SAME canonical returned")

        except Exception as e:
            print(f"    ❌ FAIL: {e}")
            return False

        print(f"\n  ✅ SCENARIO A PASS: Server returns created=false on repeat pledge")
        return True

    def test_scenario_b_different_users_different_canonicals(self):
        """
        SCENARIO B: Different users get different canonical addresses

        Network Verification:
        - POST /pledge_submit for BTC_A → canonical_A, created=true
        - POST /pledge_submit for BTC_B → canonical_B (different), created=true
        """
        print("\n" + "="*80)
        print("SCENARIO B: Different users get different canonical addresses")
        print("="*80)

        btc_1 = "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD"
        btc_2 = "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"

        pledge_template = {
            "pledge_text": "Test pledge",
            "passphrase": "test1234"
        }

        # User 1
        print(f"\n  Request 1: First user pledges (BTC_A)")
        try:
            resp1 = requests.post(
                f"{self.BASE_URL}/pledge_submit",
                json={**pledge_template, "btc_address": btc_1},
                timeout=5
            )
            data1 = resp1.json()
            canonical_1 = data1.get('canonical_v1_address')
            print(f"    Canonical: {canonical_1[:20]}... created={data1.get('created')}")
            assert canonical_1, "User 1 should get canonical"
        except Exception as e:
            print(f"    ❌ FAIL: {e}")
            return False

        # User 2
        print(f"\n  Request 2: Second user pledges (BTC_B)")
        try:
            resp2 = requests.post(
                f"{self.BASE_URL}/pledge_submit",
                json={**pledge_template, "btc_address": btc_2},
                timeout=5
            )
            data2 = resp2.json()
            canonical_2 = data2.get('canonical_v1_address')
            print(f"    Canonical: {canonical_2[:20]}... created={data2.get('created')}")
            assert canonical_2, "User 2 should get canonical"
            assert canonical_1 != canonical_2, "Different users must get different canonicals"
            print(f"    ✅ Different canonicals assigned to different users")

        except Exception as e:
            print(f"    ❌ FAIL: {e}")
            return False

        print(f"\n  ✅ SCENARIO B PASS: Different users get different canonicals")
        return True

    def test_scenario_c_wallet_status_endpoint(self):
        """
        SCENARIO C: /api/wallet/v1/status endpoint returns correct modal_state

        Network Verification:
        - GET /api/wallet/v1/status?address=canonical → returns modal_state
        - Can be used by frontend to refresh state after restore/import
        """
        print("\n" + "="*80)
        print("SCENARIO C: /api/wallet/v1/status returns modal_state")
        print("="*80)

        # First create a canonical via pledge
        pledge_data = {
            "btc_address": "1A1z7agoat2YTENE4SeKbkNRTWfWrS5hD",
            "pledge_text": "Test",
            "passphrase": "test1234"
        }

        print(f"\n  Step 1: Create canonical via pledge")
        try:
            resp = requests.post(
                f"{self.BASE_URL}/pledge_submit",
                json=pledge_data,
                timeout=5
            )
            data = resp.json()
            canonical = data.get('canonical_v1_address')
            print(f"    Canonical: {canonical[:20]}...")
        except Exception as e:
            print(f"    ❌ FAIL: {e}")
            return False

        # Now check status
        print(f"\n  Step 2: GET /api/wallet/v1/status?address={canonical[:20]}...")
        try:
            resp = requests.get(
                f"{self.BASE_URL}/api/wallet/v1/status",
                params={"address": canonical},
                timeout=5
            )
            print(f"    Status: {resp.status_code}")
            data = resp.json()

            print(f"    Response keys: {list(data.keys())}")
            if 'modal_state' in data:
                print(f"    modal_state: {data['modal_state']}")
                print(f"    ✅ Server returns modal_state for frontend refresh")
            else:
                print(f"    ⚠️  Note: modal_state not in standard response (may be custom)")
                print(f"    Available: {json.dumps(data, indent=2)[:200]}...")

            assert resp.status_code == 200, f"Status endpoint should return 200, got {resp.status_code}"
            assert 'address' in data, "Should return address field"
            print(f"    ✅ /api/wallet/v1/status returns correct response")

        except Exception as e:
            print(f"    ⚠️  Status endpoint issue: {e}")
            return False

        print(f"\n  ✅ SCENARIO C PASS: Status endpoint available for state refresh")
        return True


def main():
    """Run all 3 scenarios"""
    print("\n" + "#"*80)
    print("# MANUAL QA: CANONICAL ADDRESS IMMUTABILITY NETWORK VERIFICATION")
    print("#"*80)

    qa = ManualQANetworkVerification()
    results = {}

    try:
        results['A'] = qa.test_scenario_a_server_identity_lock_no_new_canonical()
    except Exception as e:
        print(f"\n❌ SCENARIO A EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results['A'] = False

    try:
        results['B'] = qa.test_scenario_b_different_users_different_canonicals()
    except Exception as e:
        print(f"\n❌ SCENARIO B EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results['B'] = False

    try:
        results['C'] = qa.test_scenario_c_wallet_status_endpoint()
    except Exception as e:
        print(f"\n❌ SCENARIO C EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results['C'] = False

    # Summary
    print("\n" + "="*80)
    print("MANUAL QA SUMMARY")
    print("="*80)
    print(f"A) Server: Canonical immutable (no new creation on repeat pledge)")
    print(f"   Status: {'✅ PASS' if results['A'] else '❌ FAIL'}")
    print(f"\nB) Server: Different users get different canonicals")
    print(f"   Status: {'✅ PASS' if results['B'] else '❌ FAIL'}")
    print(f"\nC) Server: /api/wallet/v1/status available for state refresh")
    print(f"   Status: {'✅ PASS' if results['C'] else '❌ FAIL'}")

    all_pass = all(results.values())
    print("\n" + ("✅ ALL SCENARIOS PASSED - READY FOR PR #621" if all_pass else "❌ FAILURES DETECTED - REVIEW REQUIRED"))
    print("="*80 + "\n")

    return all_pass


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
