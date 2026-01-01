import hashlib
import importlib
import json
import os
import shutil
import tempfile
import unittest


TEST_DATA_DIR = tempfile.mkdtemp()
os.environ["DATA_DIR"] = TEST_DATA_DIR

import server  # noqa: E402

server = importlib.reload(server)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class AddLiquidityCustomTokenTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
        os.makedirs(TEST_DATA_DIR, exist_ok=True)
        for path in [
            server.CUSTOM_TOKENS_LEDGER_DIR,
            server.MEDIA_DIR,
            server.TOKEN_LOGOS_DIR,
            server.NFT_IMAGES_DIR,
        ]:
            os.makedirs(path, exist_ok=True)

        self.client = server.app.test_client()
        self.provider = "THR" + ("a" * 40)
        self.auth_secret = "secret123"
        self.send_auth_hash = hashlib.sha256(f"{self.auth_secret}:auth".encode()).hexdigest()

        pledge_entry = {
            "thr_address": self.provider,
            "send_auth_hash": self.send_auth_hash,
            "has_passphrase": False,
        }
        _write_json(server.PLEDGE_CHAIN, [pledge_entry])

    def _base_pool(self, token_a, token_b, reserves_a, reserves_b, total_shares=1000):
        pool = {
            "id": "pool-1",
            "token_a": token_a,
            "token_b": token_b,
            "reserves_a": reserves_a,
            "reserves_b": reserves_b,
            "total_shares": total_shares,
            "providers": {},
        }
        _write_json(server.POOLS_FILE, [pool])
        return pool

    def test_add_liquidity_uses_custom_ledger_first(self):
        custom_token = {
            "id": "jam-token",
            "name": "JAM Token",
            "symbol": "JAM",
            "decimals": 6,
        }
        _write_json(server.CUSTOM_TOKENS_FILE, {"JAM": custom_token})
        _write_json(os.path.join(server.CUSTOM_TOKENS_LEDGER_DIR, "jam-token.json"), {self.provider: 1000})
        _write_json(server.LEDGER_FILE, {self.provider: 1000})
        _write_json(server.WBTC_LEDGER_FILE, {})
        _write_json(server.TOKEN_BALANCES_FILE, {})

        self._base_pool("JAM", "THR", 500, 500)

        resp = self.client.post(
            "/api/v1/pools/add_liquidity",
            json={
                "pool_id": "pool-1",
                "amount_a": 100,
                "amount_b": 100,
                "provider_thr": self.provider,
                "auth_secret": self.auth_secret,
            },
        )

        self.assertEqual(resp.status_code, 200, resp.get_json())
        jam_ledger = server.load_custom_token_ledger_by_symbol("JAM")
        self.assertEqual(jam_ledger.get(self.provider), 900)

    def test_thr_wbtc_flow_unaffected(self):
        _write_json(server.CUSTOM_TOKENS_FILE, {})
        _write_json(server.LEDGER_FILE, {self.provider: 1000})
        _write_json(server.WBTC_LEDGER_FILE, {self.provider: 0.1})
        _write_json(server.TOKEN_BALANCES_FILE, {})

        self._base_pool("THR", "WBTC", 1000, 0.1)

        resp = self.client.post(
            "/api/v1/pools/add_liquidity",
            json={
                "pool_id": "pool-1",
                "amount_a": 100,
                "amount_b": 0.01,
                "provider_thr": self.provider,
                "auth_secret": self.auth_secret,
            },
        )

        self.assertEqual(resp.status_code, 200, resp.get_json())
        thr_ledger = server.load_json(server.LEDGER_FILE, {})
        wbtc_ledger = server.load_json(server.WBTC_LEDGER_FILE, {})
        self.assertAlmostEqual(thr_ledger.get(self.provider), 900)
        self.assertAlmostEqual(wbtc_ledger.get(self.provider), 0.09)


if __name__ == "__main__":
    unittest.main()
