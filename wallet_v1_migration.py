import hashlib
import json
from datetime import datetime, UTC
from pathlib import Path

from wallet_v1_address_derivation import derive_thronos_address

MIGRATION_FILE = Path('data/wallet_v1_migrations.json')
MIGRATION_RECORD_VERSION = 2


class MigrationError(RuntimeError):
    pass


def _now():
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def _load_map():
    if not MIGRATION_FILE.exists():
        return {}
    try:
        data = json.loads(MIGRATION_FILE.read_text())
        if not isinstance(data, dict):
            return {}
        # Compatibility with old format: {"migrations": {}, "index_new": {}}
        if 'migrations' in data and isinstance(data.get('migrations'), dict):
            return data['migrations']
        return data
    except Exception:
        return {}


def _save_map(m):
    MIGRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    MIGRATION_FILE.write_text(json.dumps(m, indent=2, sort_keys=True))


def _save_map_compat(m):
    """Write new format while preserving compatibility with old readers if needed."""
    MIGRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    index_new = {}
    for old, rec in m.items():
        nv = rec.get('new_v1_address')
        if nv:
            index_new[nv] = old
    MIGRATION_FILE.write_text(json.dumps({'migrations': m, 'index_new': index_new}, indent=2, sort_keys=True))


def _server():
    import server
    return server


def _require_hook(name):
    fn = getattr(_server(), name, None)
    if not callable(fn):
        raise MigrationError(f'missing_required_hook:{name}')
    return fn


def _balance_source(addr):
    s = _server()
    # Prefer production balance source
    fn = getattr(s, 'get_wallet_balance', None)
    if callable(fn):
        return float(fn(addr) or 0.0), 'get_wallet_balance'
    # fail-closed: don't silently fallback unknown authoritative source
    raise MigrationError('missing_required_hook:get_wallet_balance')


def _token_balances(addr):
    fn = _require_hook('get_all_token_balances')
    return dict(fn(addr) or {})


def _collect_assets(addr):
    s = _server()
    thr, thr_source = _balance_source(addr)
    tokens = _token_balances(addr)
    pledge = getattr(s, 'get_pledge_record', lambda _a: None)(addr)
    whitelist = bool(getattr(s, 'is_wallet_whitelisted', lambda _a: False)(addr) or getattr(s, 'is_whitelisted_address', lambda _a: False)(addr))
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


def _verify_legacy_secret_once(old_address, legacy_secret):
    s = _server()
    verify = getattr(s, 'verify_legacy_secret_once', None)
    if callable(verify):
        return bool(verify(old_address, legacy_secret))

    # fallback only if storage has hash and no challenge verifier exists
    get_hash = getattr(s, 'get_send_seed_hash', None)
    if callable(get_hash):
        stored = get_hash(old_address)
        if not stored:
            return False
        submitted = hashlib.sha256((legacy_secret or '').encode()).hexdigest()
        return submitted == stored

    raise MigrationError('missing_required_hook:legacy_secret_verifier')


def migrate_legacy_address(old_address, legacy_secret, new_compressed_public_key):
    if not old_address or not legacy_secret or not new_compressed_public_key:
        raise ValueError('missing_migration_fields')

    new_v1_address = derive_thronos_address(new_compressed_public_key)

    mmap = _load_map()
    existing = mmap.get(old_address)
    if existing and existing.get('status') in ('completed', 'repaired'):
        raise ValueError('already_migrated')

    if not _verify_legacy_secret_once(old_address, legacy_secret):
        raise ValueError('invalid_legacy_proof')

    assets = _collect_assets(old_address)
    admission_only = not _has_transferable_state(assets)

    pending = {
        'version': MIGRATION_RECORD_VERSION,
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

    # preflight required operations (fail closed)
    transfer_balance = _require_hook('transfer_balance_atomic')
    transfer_tokens = _require_hook('transfer_all_tokens_atomic')
    preserve_admission = _require_hook('preserve_admission_to_new_address')
    mark_migrated = _require_hook('mark_legacy_migrated')

    moved_thr = 0.0
    moved_tokens = 0
    try:
        if assets['thr_balance'] > 0:
            transfer_balance(old_address, new_v1_address, assets['thr_balance'])
            moved_thr = float(assets['thr_balance'])

        moved_tokens = int(transfer_tokens(old_address, new_v1_address) or 0)

        preserve_admission(old_address, new_v1_address)

        tx = {
            'type': 'wallet_v1_migration',
            'old_address': old_address,
            'new_v1_address': new_v1_address,
            'old_balance_source': assets['thr_source'],
            'migrated_thr_amount': moved_thr,
            'migrated_token_count': moved_tokens,
            'pledge_status_preserved': pending['pledge_status_preserved'],
            'repair_of': None,
        }

        rec = dict(pending)
        rec.update({
            'status': 'completed',
            'completed_at': _now(),
            'migrated_thr_amount': moved_thr,
            'migrated_token_count': moved_tokens,
            'assets_migrated': (moved_thr > 0 or moved_tokens > 0),
            'migration_tx': tx,
        })

        mark_migrated(old_address, new_v1_address, tx)
        mmap[old_address] = rec
        _save_map_compat(mmap)
        return rec
    except Exception as e:
        rb = getattr(_server(), 'rollback_partial_migration', None)
        if callable(rb):
            try:
                rb(old_address, new_v1_address)
            except Exception:
                pass
        # ensure no persisted pending map entry
        mmap.pop(old_address, None)
        if MIGRATION_FILE.exists() and mmap:
            _save_map_compat(mmap)
        elif MIGRATION_FILE.exists() and not mmap:
            MIGRATION_FILE.unlink(missing_ok=True)
        raise MigrationError(f'migration_failed:{e}')


def repair_migration(old_address, new_v1_address):
    mmap = _load_map()
    rec = mmap.get(old_address)
    if not rec:
        raise ValueError('migration_record_not_found')

    rec_new = rec.get('new_v1_address')
    if rec_new and rec_new != new_v1_address:
        raise ValueError('migration_record_mismatch')

    s = _server()
    assets_old = _collect_assets(old_address)

    if _has_transferable_state(assets_old):
        transfer_balance = _require_hook('transfer_balance_atomic')
        transfer_tokens = _require_hook('transfer_all_tokens_atomic')
        if assets_old['thr_balance'] > 0:
            transfer_balance(old_address, new_v1_address, assets_old['thr_balance'])
        moved_tokens = int(transfer_tokens(old_address, new_v1_address) or 0)

        rec['status'] = 'repaired'
        rec['repaired_at'] = _now()
        rec['repair_of'] = rec.get('status')
        rec.setdefault('migration_tx', {})
        rec['migration_tx'].update({
            'repair_of': rec.get('status'),
            'migrated_thr_amount': rec.get('migrated_thr_amount', 0.0) + float(assets_old['thr_balance'] or 0.0),
            'migrated_token_count': rec.get('migrated_token_count', 0) + moved_tokens,
        })
        mmap[old_address] = rec
        _save_map_compat(mmap)
        return {'ok': True, 'action': 'moved_missing_assets', 'status': 'repaired'}

    unmark = _require_hook('unmark_legacy_migrated')
    unmark(old_address)
    rec['status'] = 'failed'
    rec['failed_at'] = _now()
    mmap[old_address] = rec
    _save_map_compat(mmap)
    return {'ok': True, 'action': 'rolled_back_marker', 'status': 'failed'}


def resolve_migration(address):
    mmap = _load_map()
    if address in mmap:
        rec = mmap[address]
        rec.setdefault('version', 1)
        return rec
    for rec in mmap.values():
        if rec.get('new_v1_address') == address:
            rec.setdefault('version', 1)
            return rec
    return None
