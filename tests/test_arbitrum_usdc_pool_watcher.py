import os
import unittest
from unittest.mock import patch

os.environ.setdefault('POOL_WATCHER_ENABLED', '0')

import pool_deposit_watcher as pool


class ArbitrumUSDCPoolWatcherTests(unittest.TestCase):
    def test_arbitrum_native_usdc_target_is_registered(self):
        target = next(t for t in pool.POOL_TARGETS if t['chain'] == 'arbitrum')
        self.assertEqual(target['pool_id'], 'arb-usdc')
        self.assertEqual(target['asset'], 'USDC')
        self.assertEqual(target['decimals'], 6)
        self.assertEqual(target['token_contract'], '0xaf88d065e77c8cc2239327c5edb3a432268e5831')
        self.assertEqual(target['rpc_env_var'], 'ARBITRUM_RPC_URL')
        self.assertIn('ARB_POOL_VAULT_ADDRESS', target['vault_env_vars'])

    @patch('pool_deposit_watcher._get_evm_logs_chunked')
    @patch('pool_deposit_watcher.evm_rpc_call')
    def test_arbitrum_usdc_transfer_is_decoded_with_six_decimals(self, rpc, logs):
        rpc.return_value = hex(1000)
        vault = '0x' + '11' * 20
        sender = '0x' + '22' * 20
        amount_raw = 12_345_678
        logs.return_value = [{
            'transactionHash': '0x' + 'ab' * 32,
            'logIndex': '0x2',
            'blockNumber': hex(980),
            'topics': [
                pool.TRANSFER_EVENT_SIG,
                '0x' + sender[2:].zfill(64),
                '0x' + vault[2:].zfill(64),
            ],
            'data': hex(amount_raw),
        }]
        transfers, safe_block = pool.get_evm_vault_transfers(
            'https://arb.example', vault,
            '0xaf88d065e77c8cc2239327c5edb3a432268e5831',
            'arbitrum', 6, 0,
            logs_rpc_url='https://arb-logs.example',
        )
        self.assertEqual(safe_block, 985)
        self.assertEqual(len(transfers), 1)
        self.assertAlmostEqual(transfers[0]['amount'], 12.345678)
        self.assertEqual(transfers[0]['from_address'], sender)
        args = logs.call_args.args
        self.assertEqual(args[0], 'https://arb-logs.example')
        self.assertEqual(args[1], 'arbitrum')


if __name__ == '__main__':
    unittest.main()
