#!/usr/bin/env python3
"""
Setup Wallet V1 Migration Mapping
Links legacy pledge address → canonical (mirage) address with KYC identifiers
"""

import json
import os
from pathlib import Path

# Configuration
LEGACY_ADDRESS = "THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a"
CANONICAL_ADDRESS = "THR683318ACF083723B3EDFE6C0A30AD62670F00353"
BTC_ADDRESS = "3KUGVJ96T3JHuUrEHMeAvDKSo1zM9tD9nF"
BOUND_KEY_ADDRESS = "THR67D5D8E0E0497881993446B7B8693ACE338860D36"

DATA_DIR = Path('/app/data')
MIGRATIONS_FILE = DATA_DIR / 'wallet_v1_migrations.json'
KYC_FILE = DATA_DIR / 'kyc_verified.json'
RECOVERY_KIT_DIR = DATA_DIR / 'recovery_kits'

def setup_migration_record():
    """Create/update migration record"""
    print(f"[1/3] Setting up migration record: {LEGACY_ADDRESS} → {CANONICAL_ADDRESS}")
    
    # Load existing migrations
    migrations = {}
    if MIGRATIONS_FILE.exists():
        migrations = json.loads(MIGRATIONS_FILE.read_text())
        if isinstance(migrations, dict) and 'migrations' in migrations:
            migrations = migrations['migrations']
    
    # Add/update this migration
    migrations[LEGACY_ADDRESS] = {
        "version": 3,
        "old_address": LEGACY_ADDRESS,
        "new_v1_address": CANONICAL_ADDRESS,
        "btc_address": BTC_ADDRESS,
        "bound_key_address": BOUND_KEY_ADDRESS,
        "status": "confirmed",
        "created_at": "2026-06-05T06:51:42.239Z",
        "has_signing_material": True,
        "verified": True,
    }
    
    # Save with index
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index_new = {CANONICAL_ADDRESS: LEGACY_ADDRESS}
    MIGRATIONS_FILE.write_text(json.dumps({
        'migrations': migrations,
        'index_new': index_new
    }, indent=2))
    
    print(f"   ✓ Migration record created")

def setup_kyc_mapping():
    """Create KYC verified mapping"""
    print(f"[2/3] Setting up KYC mapping")
    
    kyc = {}
    if KYC_FILE.exists():
        kyc = json.loads(KYC_FILE.read_text())
    
    # Link all three addresses
    kyc[LEGACY_ADDRESS] = {
        "canonical_v1_address": CANONICAL_ADDRESS,
        "btc_address": BTC_ADDRESS,
        "verified": True,
        "verification_date": "2026-06-05T06:51:42.239Z",
    }
    
    kyc[CANONICAL_ADDRESS] = {
        "legacy_address": LEGACY_ADDRESS,
        "btc_address": BTC_ADDRESS,
        "verified": True,
        "verification_date": "2026-06-05T06:51:42.239Z",
    }
    
    kyc[BTC_ADDRESS] = {
        "legacy_address": LEGACY_ADDRESS,
        "canonical_v1_address": CANONICAL_ADDRESS,
        "verified": True,
        "verification_date": "2026-06-05T06:51:42.239Z",
    }
    
    KYC_FILE.write_text(json.dumps(kyc, indent=2))
    print(f"   ✓ KYC mapping created")

def verify_recovery_kit():
    """Verify recovery kit has proper structure"""
    print(f"[3/3] Verifying recovery kit structure")
    
    # List recovery kits
    RECOVERY_KIT_DIR.mkdir(parents=True, exist_ok=True)
    kits = list(RECOVERY_KIT_DIR.glob('*.json'))
    
    if not kits:
        print(f"   ⚠ No recovery kits found in {RECOVERY_KIT_DIR}")
        print(f"   Recovery kit should include:")
        print(f"   - canonical_v1_address: {CANONICAL_ADDRESS}")
        print(f"   - legacy_address: {LEGACY_ADDRESS}")
        print(f"   - btc_address: {BTC_ADDRESS}")
        return
    
    for kit_file in kits:
        kit_data = json.loads(kit_file.read_text())
        if kit_data.get('canonical_v1_address') == CANONICAL_ADDRESS:
            print(f"   ✓ Found recovery kit: {kit_file.name}")
            # Verify it has legacy_address
            if 'legacy_address' not in kit_data:
                print(f"   ⚠ Recovery kit missing legacy_address field")
                kit_data['legacy_address'] = LEGACY_ADDRESS
                kit_data['btc_address'] = BTC_ADDRESS
                kit_file.write_text(json.dumps(kit_data, indent=2))
                print(f"   ✓ Updated recovery kit with legacy address")
            else:
                print(f"   ✓ Recovery kit has legacy address: {kit_data['legacy_address']}")

def main():
    print(f"""
╔════════════════════════════════════════════════════════════╗
║  Wallet V1 Migration Setup                                 ║
╚════════════════════════════════════════════════════════════╝

Legacy Address:     {LEGACY_ADDRESS}
Canonical Address:  {CANONICAL_ADDRESS}
BTC Address:        {BTC_ADDRESS}
Bound Key Address:  {BOUND_KEY_ADDRESS}
Data Directory:     {DATA_DIR}

    """)
    
    setup_migration_record()
    setup_kyc_mapping()
    verify_recovery_kit()
    
    print(f"""
╔════════════════════════════════════════════════════════════╗
║  ✅ Migration setup complete!                              ║
╠════════════════════════════════════════════════════════════╣
║  Now the system can:                                       ║
║  1. Map pledge → mirage via /api/wallet/v1/restore-migration
║  2. Verify addresses are linked via KYC                    ║
║  3. Restore wallet from recovery kit                       ║
╚════════════════════════════════════════════════════════════╝
    """)

if __name__ == '__main__':
    main()
