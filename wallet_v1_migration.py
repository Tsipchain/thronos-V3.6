import hashlib
import json
from datetime import datetime, UTC
from pathlib import Path

from wallet_v1_address_derivation import derive_thronos_address

MIGRATION_FILE = Path('data/wallet_v1_migrations.json')
MIGRATION_RECORD_VERSION = 3


class MigrationError(RuntimeError):
    pass


def _now():
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def _server():
    import server
    return server


def _load_map_raw():
    if not MIGRATION_FILE.exists():
        return {}
    try:
        data = json.loads(MIGRATION_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_map():
    data = _load_map_raw()
    if 'migrations' in data and isinstance(data.get('migrations'), dict):
        return data['migrations']
    return data


def _save_map_compat(m):
    idx = {rec.get('new_v1_address'): old for old, rec in m.items() if rec.get('new_v1_address')}
    MIGRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    MIGRATION_FILE.write_text(json.dumps({'migrations': m, 'index_new': idx}, indent=2, sort_keys=True))


def _require_server_attrs(*names):
    s = _server()
    missing = [n for n in names if not hasattr(s, n)]
    if missing:
        raise MigrationError(f"missing_required_hook:{','.join(missing)}")
    return s


def get_send_seed_hash(old_address):
    s = _require_server_attrs('load_json', 'PLEDGE_CHAIN')
    pledges = s.load_json(s.PLEDGE_CHAIN, [])
    p = next((x for x in pledges if x.get('thr_address') == old_address), None)
    if not p:
        return None
    return p.get('send_seed_hash')


def verify_legacy_secret_once(old_address, legacy_secret):
    s = _server()
    if hasattr(s, 'verify_legacy_secret_once') and callable(s.verify_legacy_secret_once):
        return bool(s.verify_legacy_secret_once(old_address, legacy_secret))
    stored = get_send_seed_hash(old_address)
    if not stored:
        raise MigrationError('missing_legacy_seed_hash')
    submitted = hashlib.sha256((legacy_secret or '').encode()).hexdigest()
    return submitted == stored


def get_wallet_balance(old_address):
    s = _require_server_attrs('get_wallet_balance')
    return float(s.get_wallet_balance(old_address) or 0.0), 'get_wallet_balance'


def get_all_token_balances(old_address):
    s = _server()
    if hasattr(s, 'get_all_token_balances'):
        return dict(s.get_all_token_balances(old_address) or {})
    if hasattr(s, 'load_token_balances'):
        tb = s.load_token_balances() or {}
        return dict(tb.get(old_address, {}) or {})
    raise MigrationError('missing_authoritative_token_source')


def transfer_balance_atomic(old_address, new_v1_address, amount):
    s = _server()
    if hasattr(s, 'transfer_balance_atomic') and callable(s.transfer_balance_atomic):
        return s.transfer_balance_atomic(old_address, new_v1_address, amount)
    s = _require_server_attrs('load_json', 'save_json', 'LEDGER_FILE')
    ledger = s.load_json(s.LEDGER_FILE, {}) or {}
    oldb = float(ledger.get(old_address, 0.0) or 0.0)
    if oldb < amount:
        raise MigrationError('insufficient_old_balance_for_migration')
    ledger[old_address] = oldb - amount
    ledger[new_v1_address] = float(ledger.get(new_v1_address, 0.0) or 0.0) + amount
    s.save_json(s.LEDGER_FILE, ledger)


def transfer_all_tokens_atomic(old_address, new_v1_address):
    s = _server()
    if hasattr(s, 'transfer_all_tokens_atomic') and callable(s.transfer_all_tokens_atomic):
        return int(s.transfer_all_tokens_atomic(old_address, new_v1_address) or 0)
    if hasattr(s, 'load_token_balances') and hasattr(s, 'save_token_balances'):
        tb = s.load_token_balances() or {}
        old = tb.get(old_address, {}) or {}
        new = tb.get(new_v1_address, {}) or {}
        moved = 0
        for sym, amt in list(old.items()):
            v = float(amt or 0)
            if v > 0:
                new[sym] = float(new.get(sym, 0) or 0) + v
                old[sym] = 0
                moved += 1
        tb[old_address] = old
        tb[new_v1_address] = new
        s.save_token_balances(tb)
        return moved
    raise MigrationError('missing_authoritative_token_source')


def preserve_admission_to_new_address(old_address, new_v1_address):
    s = _server()
    if hasattr(s, 'preserve_admission_to_new_address') and callable(s.preserve_admission_to_new_address):
        return s.preserve_admission_to_new_address(old_address, new_v1_address)
    s = _require_server_attrs('load_json', 'save_json', 'PLEDGE_CHAIN')
    # copy pledge entry (without secrets) to new address if old has pledge
    pledges = s.load_json(s.PLEDGE_CHAIN, [])
    oldp = next((p for p in pledges if p.get('thr_address') == old_address), None)
    if oldp:
        if not any(p.get('thr_address') == new_v1_address for p in pledges):
            np = dict(oldp)
            np['thr_address'] = new_v1_address
            np.pop('send_seed_hash', None)
            np.pop('send_auth_hash', None)
            pledges.append(np)
        s.save_json(s.PLEDGE_CHAIN, pledges)


def mark_legacy_migrated(old_address, new_v1_address, tx):
    s = _server()
    if hasattr(s, 'mark_legacy_migrated') and callable(s.mark_legacy_migrated):
        return s.mark_legacy_migrated(old_address, new_v1_address, tx)
    s = _require_server_attrs('load_json', 'save_json', 'PLEDGE_CHAIN')
    pledges = s.load_json(s.PLEDGE_CHAIN, [])
    changed = False
    for p in pledges:
        if p.get('thr_address') == old_address:
            p['status'] = 'legacy_migrated'
            p['migrated_to'] = new_v1_address
            p['migrated_at'] = _now()
            p['migration_tx_id'] = tx.get('tx_id') or tx.get('id') or tx.get('nonce') or ''
            changed = True
    if changed:
        s.save_json(s.PLEDGE_CHAIN, pledges)


def unmark_legacy_migrated(old_address):
    s = _server()
    if hasattr(s, 'unmark_legacy_migrated') and callable(s.unmark_legacy_migrated):
        return s.unmark_legacy_migrated(old_address)
    s = _require_server_attrs('load_json', 'save_json', 'PLEDGE_CHAIN')
    pledges = s.load_json(s.PLEDGE_CHAIN, [])
    for p in pledges:
        if p.get('thr_address') == old_address:
            p.pop('status', None)
            p.pop('migrated_to', None)
            p.pop('migrated_at', None)
            p.pop('migration_tx_id', None)
    s.save_json(s.PLEDGE_CHAIN, pledges)


def rollback_partial_migration(old_address, new_v1_address):
    # Best effort: remove migrated marker only; balance/token rollback requires source snapshots
    try:
        unmark_legacy_migrated(old_address)
    except Exception:
        pass


def _collect_assets(addr):
    thr, src = get_wallet_balance(addr)
    tokens = get_all_token_balances(addr)
    s = _server()
    pledge = getattr(s, 'get_pledge_for_auth', lambda _a: None)(addr)
    whitelist = bool(getattr(s, 'is_wallet_whitelisted', lambda _a: False)(addr) or getattr(s, 'is_whitelisted_address', lambda _a: False)(addr))
    pools = getattr(s, 'get_pool_rewards_state', lambda _a: None)(addr)
    nfts = getattr(s, 'get_nft_ownership', lambda _a: [])(addr) or []
    mining = getattr(s, 'get_mining_payout_state', lambda _a: None)(addr)
    return {'thr_balance': thr, 'thr_source': src, 'token_balances': tokens, 'pledge_record': pledge, 'whitelist': whitelist, 'pool_rewards': pools, 'nft_ownership': nfts, 'mining_state': mining}


def _has_transferable_state(a):
    return a['thr_balance'] > 0 or any(float(v or 0) > 0 for v in a['token_balances'].values()) or bool(a['nft_ownership'] or a['pool_rewards'] or a['mining_state'])


def migrate_legacy_address(old_address, legacy_secret, new_compressed_public_key):
    if not old_address or not legacy_secret or not new_compressed_public_key:
        raise ValueError('missing_migration_fields')
    new_v1_address = derive_thronos_address(new_compressed_public_key)
    mmap = _load_map()
    if mmap.get(old_address, {}).get('status') in ('completed', 'repaired'):
        raise ValueError('already_migrated')
    if not verify_legacy_secret_once(old_address, legacy_secret):
        raise ValueError('invalid_legacy_proof')

    assets = _collect_assets(old_address)
    admission_only = not _has_transferable_state(assets)

    moved_thr = 0.0
    moved_tokens = 0
    try:
        if assets['thr_balance'] > 0:
            transfer_balance_atomic(old_address, new_v1_address, assets['thr_balance'])
            moved_thr = assets['thr_balance']
        moved_tokens = transfer_all_tokens_atomic(old_address, new_v1_address)
        preserve_admission_to_new_address(old_address, new_v1_address)
        tx = {
            'type': 'wallet_v1_migration', 'old_address': old_address, 'new_v1_address': new_v1_address,
            'old_balance_source': assets['thr_source'], 'migrated_thr_amount': moved_thr,
            'migrated_token_count': moved_tokens, 'pledge_status_preserved': bool(assets['pledge_record'] or assets['whitelist']),
            'repair_of': None,
        }
        mark_legacy_migrated(old_address, new_v1_address, tx)
        rec = {
            'version': MIGRATION_RECORD_VERSION, 'old_address': old_address, 'new_v1_address': new_v1_address,
            'status': 'completed', 'created_at': _now(), 'completed_at': _now(), 'old_balance_source': assets['thr_source'],
            'migrated_thr_amount': moved_thr, 'migrated_token_count': moved_tokens,
            'pledge_status_preserved': bool(assets['pledge_record'] or assets['whitelist']),
            'admission_only': admission_only, 'assets_migrated': (moved_thr > 0 or moved_tokens > 0), 'migration_tx': tx,
        }
        mmap[old_address] = rec
        _save_map_compat(mmap)
        return rec
    except Exception as e:
        rollback_partial_migration(old_address, new_v1_address)
        raise MigrationError(f'migration_failed:{e}')


def repair_migration(old_address, new_v1_address):
    mmap = _load_map()
    rec = mmap.get(old_address)
    if not rec:
        raise ValueError('migration_record_not_found')
    if rec.get('new_v1_address') != new_v1_address:
        raise ValueError('migration_record_mismatch')

    assets_old = _collect_assets(old_address)
    moved_thr = 0.0
    moved_tokens = 0
    if _has_transferable_state(assets_old):
        if assets_old['thr_balance'] > 0:
            transfer_balance_atomic(old_address, new_v1_address, assets_old['thr_balance'])
            moved_thr = assets_old['thr_balance']
        moved_tokens = transfer_all_tokens_atomic(old_address, new_v1_address)
        preserve_admission_to_new_address(old_address, new_v1_address)
        rec['status'] = 'repaired'
        rec['repaired_at'] = _now()
        mmap[old_address] = rec
        _save_map_compat(mmap)
        return {
            'ok': True, 'old_address': old_address, 'new_v1_address': new_v1_address,
            'action': 'moved_missing_assets', 'moved_thr_amount': moved_thr,
            'moved_token_count': moved_tokens, 'status': 'repaired', 'repair_tx_id': f'repair:{old_address}:{_now()}'
        }

    unmark_legacy_migrated(old_address)
    rec['status'] = 'failed'
    rec['failed_at'] = _now()
    mmap[old_address] = rec
    _save_map_compat(mmap)
    return {
        'ok': True, 'old_address': old_address, 'new_v1_address': new_v1_address,
        'action': 'rolled_back_marker', 'moved_thr_amount': 0.0,
        'moved_token_count': 0, 'status': 'failed', 'repair_tx_id': ''
    }


def resolve_migration(address):
    mmap = _load_map()
    if address in mmap:
        return mmap[address]
    for rec in mmap.values():
        if rec.get('new_v1_address') == address:
            return rec
    return None
