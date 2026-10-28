"""Regression tests for the Arbitrum native-USDC pool watcher target."""
import unittest
from unittest.mock import Mock, patch

import pool_deposit_watcher as pool


class ArbitrumPoolTargetTests(unittest.TestCase):
    def test_native_usdc_target_is_configured_for_arbitrum_one(self):
        target = next((t for t in pool.POOL_TARGETS if t["pool_id"] == "arbitrum-usdc"), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["chain"], "arbitrum")
        self.assertEqual(target["asset"], "USDC")
        self.assertEqual(target["decimals"], 6)
        self.assertEqual(
            target["token_contract"],
            "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
        )
        self.assertTrue(target["rpc_url"])
        self.assertEqual(target["rpc_url"], pool.ARBITRUM_RPC_URL)
        self.assertEqual(target["logs_rpc_url"], pool.ARBITRUM_RPC_URL)

    def test_arbitrum_requires_an_explicit_vault_and_never_uses_bsc_or_base_default(self):
        target = next(t for t in pool.POOL_TARGETS if t["pool_id"] == "arbitrum-usdc")
        self.assertIn("ARBITRUM_POOL_VAULT_ADDRESS", target["vault_env_vars"])
        if target["vault_address"]:
            self.assertRegex(target["vault_address"], r"^0x[0-9a-f]{40}$")
        self.assertNotEqual(target["vault_address"], pool._BSC_VAULT)
        self.assertNotEqual(target["vault_address"], pool._BASE_VAULT)

    def test_missing_arbitrum_vault_skips_scan_and_never_credits(self):
        target = dict(next(t for t in pool.POOL_TARGETS if t["pool_id"] == "arbitrum-usdc"))
        target["vault_address"] = ""
        old_targets = pool.POOL_TARGETS
        old_enabled = pool.POOL_WATCHER_ENABLED
        try:
            pool.POOL_TARGETS = [target]
            pool.POOL_WATCHER_ENABLED = True
            with patch.object(pool, "_load_watcher_state", return_value={
                "last_scanned_block": {}, "credited_event_ids": [], "last_error": ""
            }), patch.object(pool, "_save_watcher_state") as save_state, \
                 patch.object(pool, "evm_rpc_call") as rpc, \
                 patch.object(pool, "credit_pool_external_deposit") as credit:
                pool.scan_pool_deposits()
                rpc.assert_not_called()
                credit.assert_not_called()
                save_state.assert_called_once()
        finally:
            pool.POOL_TARGETS = old_targets
            pool.POOL_WATCHER_ENABLED = old_enabled

    @patch("pool_deposit_watcher._get_evm_logs_chunked")
    @patch("pool_deposit_watcher.evm_rpc_call")
    def test_arbitrum_log_scan_uses_arbitrum_rpc_for_logs(self, rpc_call, chunked):
        target = next(t for t in pool.POOL_TARGETS if t["pool_id"] == "arbitrum-usdc")
        rpc_call.return_value = "0x100"
        chunked.return_value = []
        transfers, safe_block = pool.get_evm_vault_transfers(
            rpc_url=target["rpc_url"],
            vault_address="0x" + "1" * 40,
            token_contract=target["token_contract"],
            chain="arbitrum",
            decimals=6,
            last_scanned_block=100,
            logs_rpc_url=target["logs_rpc_url"],
        )
        self.assertEqual(transfers, [])
        self.assertGreater(safe_block, 0)
        chunked.assert_called_once()
        self.assertEqual(chunked.call_args.args[0], pool.ARBITRUM_RPC_URL)


if __name__ == "__main__":
    unittest.main()
