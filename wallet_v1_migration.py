"""Wallet V1 legacy->secp256k1 address migration helpers."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Dict

import server as server_module
import wallet_v1_production_final as wallet_v1_prod


MIGRATION_FILE = os.path.join(getattr(server_module, "DATA_DIR", "data"), "wallet_v1_migrations.json")


def _load_map() -> Dict[str, Any]:
    data = server_module.load_json(MIGRATION_FILE, {"migrations": {}, "index_new": {}})
    if not isinstance(data, dict):
        return {"migrations": {}, "index_new": {}}
    data.setdefault("migrations", {})
    data.setdefault("index_new", {})
    return data


def _save_map(data: Dict[str, Any]) -> None:
    server_module.save_json(MIGRATION_FILE, data)


def _pledge_entry(old_thr_address: str) -> Dict[str, Any] | None:
    pledges = server_module.load_json(server_module.PLEDGE_CHAIN, [])
    if not isinstance(pledges, list):
        return None
    for p in pledges:
        if isinstance(p, dict) and p.get("thr_address") == old_thr_address:
            return p
    return None


def _mark_legacy_pledge_migrated(old_thr_address: str, new_v1_address: str, migrated_at: int, migration_tx_id: str) -> None:
    pledges = server_module.load_json(server_module.PLEDGE_CHAIN, [])
    if not isinstance(pledges, list):
        return
    changed = False
    for p in pledges:
        if isinstance(p, dict) and p.get("thr_address") == old_thr_address:
            p["status"] = "legacy_migrated"
            p["migrated_to"] = new_v1_address
            p["migrated_at"] = migrated_at
            p["migration_tx_id"] = migration_tx_id
            changed = True
    if changed:
        server_module.save_json(server_module.PLEDGE_CHAIN, pledges)


def migrate_legacy_address(old_thr_address: str, legacy_secret: str, new_compressed_public_key: str) -> Dict[str, Any]:
    old_thr_address = (old_thr_address or "").strip()
    legacy_secret = (legacy_secret or "").strip()
    new_compressed_public_key = (new_compressed_public_key or "").strip()

    if not old_thr_address:
        raise ValueError("missing_old_thr_address")
    if not legacy_secret:
        raise ValueError("missing_legacy_secret")

    try:
        new_v1_address = wallet_v1_prod.derive_thronos_address(new_compressed_public_key)
    except Exception as exc:
        raise ValueError(f"invalid_new_public_key:{exc}")

    data = _load_map()
    if old_thr_address in data["migrations"]:
        raise ValueError("already_migrated")
    if new_v1_address in data["index_new"]:
        raise ValueError("new_v1_address_already_bound")

    is_whitelisted = bool(server_module.is_wallet_whitelisted(old_thr_address))
    has_pledge = bool(server_module.has_pledge_access(old_thr_address))
    admitted = bool(has_pledge or is_whitelisted)
    if not admitted:
        raise ValueError("old_address_not_admitted")

    pledge = _pledge_entry(old_thr_address)
    if not pledge:
        raise ValueError("legacy_record_not_found")

    stored_seed_hash = pledge.get("send_seed_hash")
    if not stored_seed_hash:
        raise ValueError("legacy_seed_hash_missing")
    if hashlib.sha256(legacy_secret.encode()).hexdigest() != stored_seed_hash:
        raise ValueError("invalid_legacy_proof")

    ledger = server_module.load_json(server_module.LEDGER_FILE, {})
    old_balance = float(ledger.get(old_thr_address, 0.0))
    ledger[old_thr_address] = 0.0
    ledger[new_v1_address] = round(float(ledger.get(new_v1_address, 0.0)) + old_balance, 6)
    server_module.save_json(server_module.LEDGER_FILE, ledger)

    migration_tx_id = f"MIGRATE-{int(time.time())}-{old_thr_address[-6:]}-{new_v1_address[-6:]}"
    migration_tx = {
        "type": "wallet_v1_migration",
        "kind": "wallet_v1_migration",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "from": old_thr_address,
        "to": new_v1_address,
        "amount": round(old_balance, 6),
        "fee_burned": 0.0,
        "tx_id": migration_tx_id,
        "status": "confirmed",
        "historical_visible": True,
    }
    chain = server_module.load_json(server_module.CHAIN_FILE, [])
    chain.append(migration_tx)
    server_module.save_json(server_module.CHAIN_FILE, chain)
    if hasattr(server_module, "persist_normalized_tx"):
        server_module.persist_normalized_tx(migration_tx)

    migrated_at = int(time.time())
    _mark_legacy_pledge_migrated(old_thr_address, new_v1_address, migrated_at, migration_tx_id)

    rec = {
        "old_address": old_thr_address,
        "new_v1_address": new_v1_address,
        "new_compressed_public_key": new_compressed_public_key,
        "migrated_at": migrated_at,
        "migration_tx_id": migration_tx_id,
        "admission_source": "whitelist" if is_whitelisted else ("btc_pledge" if has_pledge else "unknown"),
        "legacy_proof_hash": hashlib.sha256(
            f"wallet_v1_migration:{old_thr_address}:{new_v1_address}:{stored_seed_hash}".encode()
        ).hexdigest(),
        "historical_visible": True,
        "old_read_only": True,
    }
    data["migrations"][old_thr_address] = rec
    data["index_new"][new_v1_address] = old_thr_address
    _save_map(data)
    return rec


def resolve_migration(address: str) -> Dict[str, Any] | None:
    address = (address or "").strip()
    data = _load_map()
    if address in data["migrations"]:
        return {"kind": "old", **data["migrations"][address]}
    old = data["index_new"].get(address)
    if old and old in data["migrations"]:
        return {"kind": "new", **data["migrations"][old]}
    return None
