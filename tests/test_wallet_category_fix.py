#!/usr/bin/env python3
"""Unit tests for wallet category fix utility"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from wallet_category_fix import categorize_transaction

def test_categorize_transaction():
    """Test transaction categorization logic"""
    
    test_cases = [
        # THR transfers
        ({'kind': 'thr_transfer', 'from': 'THR123', 'to': 'THR456', 'amount': 10}, 'thr'),
        ({'kind': 'transfer', 'asset': 'THR'}, 'thr'),
        
        # Mining
        ({'kind': 'mining_reward', 'amount': 5}, 'mining'),
        ({'kind': 'block_reward'}, 'mining'),
        
        # Tokens
        ({'kind': 'token_transfer', 'asset_symbol': 'USDT'}, 'tokens'),
        
        # Gateway (fiat)
        ({'kind': 'fiat_buy', 'fiat_amount': 100}, 'gateway'),
        ({'kind': 'fiat_onramp'}, 'gateway'),
        ({'kind': 'iot_purchase', 'stripe_id': 'pi_xxx'}, 'gateway'),
        
        # Music
        ({'kind': 'music_tip', 'artist': 'John Doe'}, 'music'),
        ({'kind': 'music_play_reward', 'track_id': '123'}, 'music'),
        ({'meta': {'source': 'music_player'}}, 'music'),
        
        # L2E
        ({'kind': 'l2e_reward', 'course': 'Bitcoin 101'}, 'l2e'),
        
        # T2E
        ({'kind': 't2e_reward_thr', 'contribution': 'whitepaper'}, 't2e_reward_thr'),
        
        # IoT
        ({'kind': 'iot_parking', 'location': 'Athens'}, 'iot'),
        
        # Bridge
        ({'kind': 'bridge_deposit', 'chain': 'ethereum'}, 'bridge'),
        
        # Swaps
        ({'kind': 'swap', 'from_token': 'THR', 'to_token': 'USDT'}, 'swaps'),
        
        # Liquidity
        ({'kind': 'liquidity_add', 'pool': 'THR/USDT'}, 'liquidity'),
        
        # AI Credits
        ({'kind': 'ai_credits_earned', 'amount': 100}, 'ai_credits'),
        ({'meta': {'is_ai_credit': True}}, 'ai_credits'),
        
        # Architect Jobs
        ({'kind': 'architect_job', 'job_id': 'job-123'}, 'architect_job'),
        ({'kind': 'ai_job_completed'}, 'architect_job'),
    ]
    
    passed = 0
    failed = 0
    
    print("🧪 Testing wallet category detection...\n")
    
    for tx, expected_category in test_cases:
        result = categorize_transaction(tx)
        status = "✅" if result == expected_category else "❌"
        
        if result == expected_category:
            passed += 1
        else:
            failed += 1
            print(f"{status} FAILED: {tx.get('kind', 'unknown')}")
            print(f"   Expected: {expected_category}")
            print(f"   Got: {result}")
            print()
    
    print(f"\n📊 Results: {passed} passed, {failed} failed\n")
    
    if failed > 0:
        print("❌ Some tests failed!")
        sys.exit(1)
    else:
        print("🎉 All tests passed!")

if __name__ == '__main__':
    test_categorize_transaction()
