"""Regression tests for dedicated BSC eth_getLogs RPC routing."""
import unittest
from unittest.mock import Mock, patch

import bnb_pledge_watcher as bnb
import pool_deposit_watcher as pool


def rpc_response(body, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = body
    response.text = ""
    return response


class BscDedicatedLogsRpcTests(unittest.TestCase):
    def setUp(self):
        self.old_bnb_rpc = bnb.BSC_RPC_URL
        self.old_bnb_logs_rpc = bnb.BSC_RPC_LOGS_URL
        self.old_warn_flag = bnb._WARNED_NO_BSC_LOGS_RPC

    def tearDown(self):
        bnb.BSC_RPC_URL = self.old_bnb_rpc
        bnb.BSC_RPC_LOGS_URL = self.old_bnb_logs_rpc
        bnb._WARNED_NO_BSC_LOGS_RPC = self.old_warn_flag

    @patch("bnb_pledge_watcher.requests.post")
    def test_eth_get_logs_uses_dedicated_logs_provider(self, post):
        bnb.BSC_RPC_URL = "https://shared-a.example,https://shared-b.example"
        bnb.BSC_RPC_LOGS_URL = "https://logs-a.example,https://logs-b.example"
        post.return_value = rpc_response({"jsonrpc": "2.0", "result": []})

        self.assertEqual(bnb.bsc_rpc_call("eth_getLogs", [{}]), [])
        self.assertEqual(post.call_args.args[0], "https://logs-a.example")

    @patch("bnb_pledge_watcher.requests.post")
    def test_eth_block_number_keeps_regular_rpc_provider(self, post):
        bnb.BSC_RPC_URL = "https://shared-a.example,https://shared-b.example"
        bnb.BSC_RPC_LOGS_URL = "https://logs-a.example,https://logs-b.example"
        post.return_value = rpc_response({"jsonrpc": "2.0", "result": "0x123"})

        self.assertEqual(bnb.bsc_rpc_call("eth_blockNumber"), "0x123")
        self.assertEqual(post.call_args.args[0], "https://shared-a.example")

    @patch("bnb_pledge_watcher.requests.post")
    def test_dedicated_logs_provider_falls_back_only_to_its_own_list(self, post):
        bnb.BSC_RPC_URL = "https://shared-public.example"
        bnb.BSC_RPC_LOGS_URL = "https://logs-a.example,https://logs-b.example"
        post.side_effect = [
            rpc_response({"error": {"message": "limit exceeded"}}),
            rpc_response({"result": "[]"}),
        ]

        # JSON-RPC result must be a list, not a serialized JSON string.
        post.side_effect = [
            rpc_response({"error": {"message": "limit exceeded"}}),
            rpc_response({"result": []}),
        ]
        self.assertEqual(bnb.bsc_rpc_call("eth_getLogs", [{}]), [])
        self.assertEqual(
            [call.args[0] for call in post.call_args_list],
            ["https://logs-a.example", "https://logs-b.example"],
        )

    @patch("pool_deposit_watcher._get_evm_logs_chunked")
    @patch("pool_deposit_watcher.evm_rpc_call")
    def test_pool_scanner_uses_dedicated_logs_provider(self, rpc_call, chunked):
        rpc_call.return_value = "0x100"
        chunked.return_value = []

        transfers, safe_block = pool.get_evm_vault_transfers(
            rpc_url="https://shared-bsc.example",
            vault_address="0x" + "1" * 40,
            token_contract="0x" + "2" * 40,
            chain="bsc",
            decimals=18,
            last_scanned_block=100,
            logs_rpc_url="https://dedicated-logs.example",
        )

        self.assertEqual(transfers, [])
        self.assertEqual(safe_block, 256 - pool.POOL_WATCHER_CONFIRMATIONS)
        chunked.assert_called_once()
        self.assertEqual(chunked.call_args.args[0], "https://dedicated-logs.example")


if __name__ == "__main__":
    unittest.main()
