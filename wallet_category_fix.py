#!/usr/bin/env python3
"""Wallet History Category Persistence Fix

Backfills missing 'category' fields in TX_LOG to fix wallet modal tabs.
Run this once to repair existing transactions, then import in server.py.

Usage:
    python wallet_category_fix.py

Or in server.py startup:
    import wallet_category_fix
    wallet_category_fix.backfill_categories()
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
TX_LOG = DATA_DIR / "tx_log.jsonl"

def categorize_transaction(tx):
    """Detect transaction category from fields"""
    kind = str(tx.get('kind', tx.get('type', ''))).lower()
    category = str(tx.get('category', '')).lower()
    
    # Already has valid category
    if category and category not in ['', 'other', 'unknown']:
        return category
    
    # Category map (same as frontend getCanonicalCategory)
    category_map = {
        'transfer': 'thr',
        'thr_transfer': 'thr',
        'mining': 'mining',
        'block_reward': 'mining',
        'mining_reward': 'mining',
        'mined': 'mining',
        'token_transfer': 'tokens',
        'swap': 'swaps',
        'pool_swap': 'swaps',
        'liquidity_add': 'liquidity',
        'liquidity_remove': 'liquidity',
        'liquidity': 'liquidity',
        'pool_add': 'liquidity',
        'pool_remove': 'liquidity',
        'bridge': 'bridge',
        'bridge_deposit': 'bridge',
        'bridge_withdraw': 'bridge',
        'l2e': 'l2e',
        'l2e_reward': 'l2e',
        'ai_credit': 'ai_credits',
        'ai_credits': 'ai_credits',
        'ai_credits_earned': 'ai_credits',
        'ai_credits_spent': 'ai_credits',
        'architect': 'architect_job',
        'architect_job': 'architect_job',
        'ai_job_created': 'architect_job',
        'ai_job_progress': 'architect_job',
        'ai_job_completed': 'architect_job',
        'ai_job_reward': 'architect_job',
        'iot': 'iot',
        'iot_parking': 'iot',
        'iot_parking_reservation': 'iot',
        'iot_autopilot': 'iot',
        'gateway': 'gateway',
        'gateway_deposit': 'gateway',
        'gateway_withdraw': 'gateway',
        'fiat_buy': 'gateway',
        'fiat_deposit': 'gateway',
        'fiat_onramp': 'gateway',
        'fiat_sell_request': 'gateway',
        'fiat_withdrawal': 'gateway',
        'fiat_offramp': 'gateway',
        'iot_purchase': 'gateway',
        'music': 'music',
        'music_tip': 'music',
        'music_purchase': 'music',
        'music_stream': 'music',
        'music_royalty': 'music',
        'music_play_reward': 'music',
        't2e_reward': 't2e',
        't2e_reward_thr': 't2e_reward_thr',
        'train_reward': 't2e',
        'network_reward': 'network',
        'validator_reward': 'network',
    }
    
    detected = category_map.get(kind, None)
    
    # Additional heuristics
    if not detected:
        meta = tx.get('meta', {})
        if meta.get('is_ai_credit') or meta.get('billing_unit') == 'credits':
            detected = 'ai_credits'
        elif tx.get('fiat_amount') or tx.get('stripe_id'):
            detected = 'gateway'
        elif meta.get('source') == 'music_player':
            detected = 'music'
    
    return detected or 'other'

def backfill_categories():
    """Read TX_LOG, add missing categories, rewrite file"""
    if not TX_LOG.exists():
        logger.info("[Category Fix] TX_LOG not found, skipping")
        return 0
    
    logger.info(f"[Category Fix] Loading {TX_LOG}...")
    
    transactions = []
    fixed_count = 0
    
    try:
        with open(TX_LOG, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tx = json.loads(line)
                    
                    # Check if category is missing or generic
                    current_category = str(tx.get('category', '')).lower()
                    if not current_category or current_category in ['', 'other', 'unknown']:
                        new_category = categorize_transaction(tx)
                        if new_category and new_category != 'other':
                            tx['category'] = new_category
                            fixed_count += 1
                            logger.debug(f"[Category Fix] {tx.get('tx_id', 'unknown')[:16]}: {new_category}")
                    
                    transactions.append(tx)
                except json.JSONDecodeError as e:
                    logger.warning(f"[Category Fix] Skipping invalid JSON line: {e}")
                    continue
        
        if fixed_count > 0:
            # Write back
            logger.info(f"[Category Fix] Rewriting {len(transactions)} transactions with {fixed_count} fixes...")
            backup_path = TX_LOG.with_suffix('.jsonl.bak')
            TX_LOG.rename(backup_path)
            
            with open(TX_LOG, 'w') as f:
                for tx in transactions:
                    f.write(json.dumps(tx) + '\n')
            
            logger.info(f"[Category Fix] ✅ Fixed {fixed_count} transactions (backup: {backup_path.name})")
        else:
            logger.info("[Category Fix] ✅ All transactions already have categories")
        
        return fixed_count
    
    except Exception as e:
        logger.error(f"[Category Fix] ❌ Failed: {e}")
        return 0

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fixed = backfill_categories()
    print(f"✅ Fixed {fixed} transactions")
