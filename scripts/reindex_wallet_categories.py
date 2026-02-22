#!/usr/bin/env python3
"""Reindex wallet transaction categories in TX_LOG.

This script re-categorizes all transactions in tx_log.jsonl
using the improved _categorize_transaction logic.

Usage:
    python3 scripts/reindex_wallet_categories.py

After running:
    sudo systemctl restart thronos-web
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import server modules
sys.path.insert(0, str(Path(__file__).parent.parent))

TX_LOG = "data/tx_log.jsonl"
BACKUP_SUFFIX = datetime.now().strftime("%Y%m%d_%H%M%S")


def _categorize_transaction(tx: dict) -> str:
    """Categorize transaction based on amount, addresses, and context.
    
    Categories:
    - music: Play rewards (<0.01 THR) or artist tips (>0.1 THR)
    - gateway: Bridge deposits/withdrawals
    - l2e: Learn-to-Earn rewards (fixed 1.0 THR)
    - ai_credits: AI service payments (0.1 THR)
    - mining: Block rewards from coinbase
    - tokens: Custom token transfers
    - other: Everything else
    """
    amount = float(tx.get("amount", 0))
    from_addr = str(tx.get("from", "")).lower()
    to_addr = str(tx.get("to", "")).lower()
    
    # Mining rewards (from coinbase address)
    if from_addr == "coinbase" or "mining" in from_addr:
        return "mining"
    
    # Play rewards (micro-payments from music streaming)
    # Typically 0.005 THR per play
    if amount <= 0.01 and ("music" in from_addr or "streaming" in from_addr or "play" in from_addr):
        return "music"
    
    # Artist tips (larger payments to music addresses)
    # Typically 0.5 THR or more
    if amount >= 0.1 and ("music" in to_addr or "artist" in to_addr or "nft" in to_addr):
        return "music"
    
    # Gateway payments (bridge deposits/withdrawals)
    if "gateway" in to_addr or "gateway" in from_addr or "bridge" in to_addr or "bridge" in from_addr:
        return "gateway"
    
    # L2E rewards (fixed 1.0 THR typically)
    if "l2e" in from_addr or "learn" in from_addr or (amount == 1.0 and "reward" in from_addr):
        return "l2e"
    
    # AI credits (0.1 THR per credit typically)
    if "ai" in to_addr or "assistant" in to_addr or (amount == 0.1 and "credit" in to_addr):
        return "ai_credits"
    
    # Token transfers (has token_symbol field)
    if tx.get("token_symbol") or tx.get("token_name"):
        return "tokens"
    
    # Default category
    return "other"


def backup_tx_log():
    """Create backup of TX_LOG before reindexing."""
    if not os.path.exists(TX_LOG):
        print(f"⚠️  TX_LOG not found: {TX_LOG}")
        return False
    
    backup_path = f"{TX_LOG}.backup_{BACKUP_SUFFIX}"
    try:
        with open(TX_LOG, "r", encoding="utf-8") as src:
            with open(backup_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        print(f"✅ Backup created: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False


def reindex_categories():
    """Force re-categorize all transactions in TX_LOG."""
    if not os.path.exists(TX_LOG):
        print(f"❌ TX_LOG not found: {TX_LOG}")
        print(f"   Expected location: {os.path.abspath(TX_LOG)}")
        return
    
    print(f"🔍 Reading TX_LOG: {TX_LOG}")
    
    fixed_txs = []
    stats = {
        "total": 0,
        "fixed": 0,
        "music": 0,
        "gateway": 0,
        "l2e": 0,
        "ai_credits": 0,
        "mining": 0,
        "tokens": 0,
        "other": 0
    }
    
    try:
        with open(TX_LOG, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    tx = json.loads(line)
                    stats["total"] += 1
                    
                    old_category = tx.get("category", "")
                    new_category = _categorize_transaction(tx)
                    
                    if old_category != new_category:
                        stats["fixed"] += 1
                        print(f"  Line {line_num}: {old_category or 'NONE'} → {new_category}")
                    
                    tx["category"] = new_category
                    stats[new_category] = stats.get(new_category, 0) + 1
                    fixed_txs.append(tx)
                    
                except json.JSONDecodeError as e:
                    print(f"⚠️  Line {line_num} invalid JSON: {e}")
                    continue
        
        # Rewrite TX_LOG with fixed categories
        print(f"\n💾 Writing {len(fixed_txs)} transactions back to TX_LOG...")
        with open(TX_LOG, "w", encoding="utf-8") as f:
            for tx in fixed_txs:
                f.write(json.dumps(tx) + "\n")
        
        print(f"\n✅ TX_LOG reindexed successfully!")
        print(f"\n📊 Statistics:")
        print(f"   Total transactions: {stats['total']}")
        print(f"   Fixed categories:   {stats['fixed']}")
        print(f"\n   By category:")
        print(f"   - Music:      {stats['music']}")
        print(f"   - Gateway:    {stats['gateway']}")
        print(f"   - L2E:        {stats['l2e']}")
        print(f"   - AI Credits: {stats['ai_credits']}")
        print(f"   - Mining:     {stats['mining']}")
        print(f"   - Tokens:     {stats['tokens']}")
        print(f"   - Other:      {stats['other']}")
        
    except Exception as e:
        print(f"❌ Error during reindexing: {e}")
        raise


if __name__ == "__main__":
    print("🔧 Wallet Category Reindexing Tool")
    print("=" * 50)
    print()
    
    # Create backup first
    if backup_tx_log():
        print()
        # Run reindexing
        reindex_categories()
        print()
        print("🎯 Next steps:")
        print("   1. Verify categories: tail -100 data/tx_log.jsonl | grep category")
        print("   2. Restart web service: sudo systemctl restart thronos-web")
        print("   3. Test wallet history modal in browser")
    else:
        print("❌ Reindexing aborted due to backup failure")
