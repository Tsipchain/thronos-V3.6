import json
from datetime import datetime, UTC
from pathlib import Path

MIGRATION_FILE = Path('data/wallet_v1_migrations.json')


def _now():
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def _load_map():
    if not MIGRATION_FILE.exists():
        return {}
    try:
        return json.loads(MIGRATION_FILE.read_text())
    except Exception:
        return {}


def _save_map(m):
    MIGRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    MIGRATION_FILE.write_text(json.dumps(m, indent=2, sort_keys=True))


def _server():
    import server
    return server


def _get_thr_balance(addr):
    s = _server()
    if hasattr(s, 'get_wallet_balance'):
        return float(s.get_wallet_balance(addr) or 0.0), 'get_wallet_balance'
    ledger = getattr(s, 'load_json')(getattr(s, 'LEDGER_FILE')) if hasattr(s, 'load_json') else {}
    return float((ledger or {}).get(addr, 0.0) or 0.0), 'LEDGER_FILE'


def _get_token_balances(addr):
    s = _server()
    fn = getattr(s, 'get_all_token_balances', None)
    return dict(fn(addr) or {}) if fn else {}


def _collect_assets(addr):
    s = _server()
    thr, thr_source = _get_thr_balance(addr)
    tokens = _get_token_balances(addr)
    pledge = getattr(s, 'get_pledge_record', lambda _a: None)(addr)
    whitelist = bool(getattr(s, 'is_whitelisted_address', lambda _a: False)(addr))
    pools = getattr(s, 'get_pool_rewards_state', lambda _a: None)(addr)
    nfts = getattr(s, 'get_nft_ownership', lambda _a: [])(addr) or []
    mining = getattr(s, 'get_mining_payout_state', lambda _a: None)(addr)
    return {
        'thr_balance': float(thr),
        'thr_source': thr_source,
        'token_balances': tokens,
        'pledge_record': pledge,
        'whitelist': whitelist,
        'pool_rewards': pools,
        'nft_ownership': nfts,
        'mining_state': mining,
    }


def _has_transferable_state(a):
    if a['thr_balance'] > 0:
        return True
    if any(float(v or 0) > 0 for v in (a['token_balances'] or {}).values()):
        return True
    return bool(a['nft_ownership'] or a['pool_rewards'] or a['mining_state'])


def migrate_legacy_address(old_address, legacy_secret, new_public_key, new_v1_address):
    if not old_address or not legacy_secret or not new_public_key or not new_v1_address:
        raise ValueError('missing_migration_fields')

    mmap = _load_map()
    if mmap.get(old_address, {}).get('status') == 'completed':
        raise ValueError('already_migrated')

    assets = _collect_assets(old_address)
    admission_only = not _has_transferable_state(assets)

    # Preflight verifier hook
    s = _server()
    verify = getattr(s, 'verify_legacy_secret_once', None)
    if verify and not verify(old_address, legacy_secret):
        raise ValueError('invalid_legacy_proof')

    pending = {
        'old_address': old_address,
        'new_v1_address': new_v1_address,
        'status': 'pending',
        'created_at': _now(),
        'old_balance_source': assets['thr_source'],
        'migrated_thr_amount': 0.0,
        'migrated_token_count': 0,
        'pledge_status_preserved': bool(assets['pledge_record'] or assets['whitelist']),
        'admission_only': admission_only,
        'assets_migrated': False,
    }

    if not admission_only and assets['thr_balance'] <= 0 and not any(float(v or 0) > 0 for v in assets['token_balances'].values()):
        raise ValueError('no_transferable_state')

    try:
        # transfer THR first
        moved_thr = 0.0
        if assets['thr_balance'] > 0:
            mover = getattr(s, 'transfer_balance_atomic', None)
            if not mover:
                raise RuntimeError('transfer_balance_atomic_missing')
            mover(old_address, new_v1_address, assets['thr_balance'])
            moved_thr = float(assets['thr_balance'])

        # transfer tokens
        moved_tokens = 0
        token_mover = getattr(s, 'transfer_all_tokens_atomic', None)
        if token_mover:
            moved_tokens = int(token_mover(old_address, new_v1_address) or 0)

        # preserve admission markers (without marking old migrated yet until success)
        preserve = getattr(s, 'preserve_admission_to_new_address', None)
        if preserve:
            preserve(old_address, new_v1_address)

        rec = dict(pending)
        rec.update({
            'status': 'completed',
            'completed_at': _now(),
            'migrated_thr_amount': moved_thr,
            'migrated_token_count': moved_tokens,
            'assets_migrated': (moved_thr > 0 or moved_tokens > 0),
            'migration_tx': {
                'type': 'wallet_v1_migration',
                'old_address': old_address,
                'new_v1_address': new_v1_address,
                'old_balance_source': assets['thr_source'],
                'migrated_thr_amount': moved_thr,
                'migrated_token_count': moved_tokens,
                'pledge_status_preserved': pending['pledge_status_preserved'],
                'repair_of': None,
            }
        })

        mark = getattr(s, 'mark_legacy_migrated', None)
        if mark:
            mark(old_address, new_v1_address, rec['migration_tx'])

        mmap[old_address] = rec
        _save_map(mmap)
        return rec
    except Exception as e:
        # rollback hooks
        rollback = getattr(s, 'rollback_partial_migration', None)
        if rollback:
            rollback(old_address, new_v1_address)
        # do not save migration map on failure
        raise RuntimeError(f'migration_failed:{e}')


def repair_migration(old_address, new_v1_address):
    mmap = _load_map()
    rec = mmap.get(old_address)
    if not rec:
        raise ValueError('migration_record_not_found')
    if rec.get('new_v1_address') != new_v1_address:
        raise ValueError('migration_record_mismatch')

    s = _server()
    assets_old = _collect_assets(old_address)
    if _has_transferable_state(assets_old):
        # repair by moving missing
        if assets_old['thr_balance'] > 0 and hasattr(s, 'transfer_balance_atomic'):
            s.transfer_balance_atomic(old_address, new_v1_address, assets_old['thr_balance'])
        if hasattr(s, 'transfer_all_tokens_atomic'):
            s.transfer_all_tokens_atomic(old_address, new_v1_address)
        rec['status'] = 'repaired'
        rec['repair_of'] = rec.get('status')
        rec['repaired_at'] = _now()
        mmap[old_address] = rec
        _save_map(mmap)
        return {'ok': True, 'action': 'moved_missing_assets', 'status': 'repaired'}

    # or rollback marker if no assets to move and inconsistent
    rollback = getattr(s, 'unmark_legacy_migrated', None)
    if rollback:
        rollback(old_address)
    rec['status'] = 'failed'
    rec['failed_at'] = _now()
    mmap[old_address] = rec
    _save_map(mmap)
    return {'ok': True, 'action': 'rolled_back_marker', 'status': 'failed'}


def resolve_migration(address):
    mmap = _load_map()
    if address in mmap:
        return mmap[address]
    for rec in mmap.values():
        if rec.get('new_v1_address') == address:
            return rec
    return None
