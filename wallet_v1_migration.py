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
    raw = _load_map_raw()
    if isinstance(raw.get('migrations'), dict):
        return raw['migrations']
    return raw


def _save_map_compat(migrations):
    index_new = {}
    for old, rec in migrations.items():
        new = rec.get('new_v1_address')
        if new:
            index_new[new] = old
    MIGRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    MIGRATION_FILE.write_text(json.dumps({'migrations': migrations, 'index_new': index_new}, indent=2, sort_keys=True))


def _require_callable(name):
    fn = getattr(_server(), name, None)
    if not callable(fn):
        raise MigrationError(f'missing_required_hook:{name}')
    return fn


def get_send_seed_hash(old_address):
    s = _server()
    load_json = getattr(s, 'load_json', None)
    pledge_chain = getattr(s, 'PLEDGE_CHAIN', None)
    if not callable(load_json) or not pledge_chain:
        raise MigrationError('missing_legacy_seed_hash')
    pledges = load_json(pledge_chain, []) or []
    row = next((p for p in pledges if p.get('thr_address') == old_address), None)
    return row.get('send_seed_hash') if row else None


def verify_legacy_secret_once(old_address, legacy_secret):
    s = _server()
    verifier = getattr(s, 'verify_legacy_secret_once', None)
    if callable(verifier):
        return bool(verifier(old_address, legacy_secret))
    stored = get_send_seed_hash(old_address)
    if not stored:
        raise MigrationError('missing_legacy_seed_hash')
    return hashlib.sha256((legacy_secret or '').encode()).hexdigest() == stored


def get_wallet_balance(address):
    """Authoritative THR source: same primitives /api/balances uses in server.py (get_wallet_balance or LEDGER_FILE)."""
    s = _server()
    if callable(getattr(s, 'get_wallet_balance', None)):
        return float(s.get_wallet_balance(address) or 0.0), 'get_wallet_balance'
    if callable(getattr(s, 'load_json', None)) and getattr(s, 'LEDGER_FILE', None):
        ledger = s.load_json(s.LEDGER_FILE, {}) or {}
        return float(ledger.get(address, 0.0) or 0.0), 'LEDGER_FILE'
    raise MigrationError('missing_authoritative_balance_source')


def get_all_token_balances(address):
    s = _server()
    if callable(getattr(s, 'get_all_token_balances', None)):
        return dict(s.get_all_token_balances(address) or {})
    if callable(getattr(s, 'load_token_balances', None)):
        balances = s.load_token_balances() or {}
        return dict(balances.get(address, {}) or {})
    if callable(getattr(s, 'load_json', None)) and getattr(s, 'TOKEN_BALANCES_FILE', None):
        balances = s.load_json(s.TOKEN_BALANCES_FILE, {}) or {}
        return dict(balances.get(address, {}) or {})
    raise MigrationError('missing_authoritative_token_source')


def transfer_balance_atomic(old, new, amount):
    s = _server()
    if callable(getattr(s, 'transfer_balance_atomic', None)):
        return s.transfer_balance_atomic(old, new, amount)
    load_json = getattr(s, 'load_json', None)
    save_json = getattr(s, 'save_json', None)
    ledger_file = getattr(s, 'LEDGER_FILE', None)
    if not callable(load_json) or not callable(save_json) or not ledger_file:
        raise MigrationError('missing_required_hook:transfer_balance_atomic')
    ledger = load_json(ledger_file, {}) or {}
    old_bal = float(ledger.get(old, 0.0) or 0.0)
    if old_bal < float(amount):
        raise MigrationError('insufficient_old_balance_for_migration')
    ledger[old] = old_bal - float(amount)
    ledger[new] = float(ledger.get(new, 0.0) or 0.0) + float(amount)
    save_json(ledger_file, ledger)


def transfer_all_tokens_atomic(old, new):
    s = _server()
    if callable(getattr(s, 'transfer_all_tokens_atomic', None)):
        return int(s.transfer_all_tokens_atomic(old, new) or 0)
    if callable(getattr(s, 'load_token_balances', None)) and callable(getattr(s, 'save_token_balances', None)):
        balances = s.load_token_balances() or {}
        old_b = balances.get(old, {}) or {}
        new_b = balances.get(new, {}) or {}
        moved = 0
        for sym, amt in list(old_b.items()):
            v = float(amt or 0)
            if v > 0:
                new_b[sym] = float(new_b.get(sym, 0) or 0) + v
                old_b[sym] = 0
                moved += 1
        balances[old] = old_b
        balances[new] = new_b
        s.save_token_balances(balances)
        return moved
    raise MigrationError('missing_required_hook:transfer_all_tokens_atomic')


def preserve_admission_to_new_address(old, new):
    s = _server()
    if callable(getattr(s, 'preserve_admission_to_new_address', None)):
        return s.preserve_admission_to_new_address(old, new)
    load_json = getattr(s, 'load_json', None)
    save_json = getattr(s, 'save_json', None)
    pledge_chain = getattr(s, 'PLEDGE_CHAIN', None)
    if not callable(load_json) or not callable(save_json) or not pledge_chain:
        raise MigrationError('missing_required_hook:preserve_admission_to_new_address')
    pledges = load_json(pledge_chain, []) or []
    old_row = next((p for p in pledges if p.get('thr_address') == old), None)
    if old_row and not any(p.get('thr_address') == new for p in pledges):
        cp = dict(old_row)
        cp['thr_address'] = new
        cp.pop('send_seed_hash', None)
        cp.pop('send_auth_hash', None)
        pledges.append(cp)
        save_json(pledge_chain, pledges)


def mark_legacy_migrated(old, new, tx):
    s = _server()
    if callable(getattr(s, 'mark_legacy_migrated', None)):
        return s.mark_legacy_migrated(old, new, tx)
    load_json = getattr(s, 'load_json', None)
    save_json = getattr(s, 'save_json', None)
    pledge_chain = getattr(s, 'PLEDGE_CHAIN', None)
    if not callable(load_json) or not callable(save_json) or not pledge_chain:
        raise MigrationError('missing_required_hook:mark_legacy_migrated')
    pledges = load_json(pledge_chain, []) or []
    changed = False
    for p in pledges:
        if p.get('thr_address') == old:
            p['status'] = 'legacy_migrated'
            p['migrated_to'] = new
            p['migrated_at'] = _now()
            changed = True
    if changed:
        save_json(pledge_chain, pledges)


def unmark_legacy_migrated(old):
    s = _server()
    if callable(getattr(s, 'unmark_legacy_migrated', None)):
        return s.unmark_legacy_migrated(old)
    load_json = getattr(s, 'load_json', None)
    save_json = getattr(s, 'save_json', None)
    pledge_chain = getattr(s, 'PLEDGE_CHAIN', None)
    if not callable(load_json) or not callable(save_json) or not pledge_chain:
        raise MigrationError('missing_required_hook:unmark_legacy_migrated')
    pledges = load_json(pledge_chain, []) or []
    for p in pledges:
        if p.get('thr_address') == old:
            p.pop('status', None)
            p.pop('migrated_to', None)
            p.pop('migrated_at', None)
    save_json(pledge_chain, pledges)


def rollback_partial_migration(old, new):
    s = _server()
    rb = getattr(s, 'rollback_partial_migration', None)
    if callable(rb):
        try:
            return rb(old, new)
        except Exception:
            pass
    try:
        unmark_legacy_migrated(old)
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
    return {
        'thr_balance': thr,
        'thr_source': src,
        'token_balances': tokens,
        'pledge_record': pledge,
        'whitelist': whitelist,
        'pool_rewards': pools,
        'nft_ownership': nfts,
        'mining_state': mining,
    }


def _has_assets(a):
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
    admission_only = not _has_assets(assets)

    moved_thr = 0.0
    moved_tokens = 0
    try:
        if assets['thr_balance'] > 0:
            transfer_balance_atomic(old_address, new_v1_address, assets['thr_balance'])
            moved_thr = assets['thr_balance']
        moved_tokens = transfer_all_tokens_atomic(old_address, new_v1_address)
        preserve_admission_to_new_address(old_address, new_v1_address)

        tx = {
            'type': 'wallet_v1_migration',
            'old_address': old_address,
            'new_v1_address': new_v1_address,
            'old_balance_source': assets['thr_source'],
            'migrated_thr_amount': moved_thr,
            'migrated_token_count': moved_tokens,
            'pledge_status_preserved': bool(assets['pledge_record'] or assets['whitelist']),
            'repair_of': None,
        }

        mark_legacy_migrated(old_address, new_v1_address, tx)

        rec = {
            'version': MIGRATION_RECORD_VERSION,
            'old_address': old_address,
            'new_v1_address': new_v1_address,
            'status': 'completed',
            'created_at': _now(),
            'completed_at': _now(),
            'old_balance_source': assets['thr_source'],
            'migrated_thr_amount': moved_thr,
            'migrated_token_count': moved_tokens,
            'pledge_status_preserved': bool(assets['pledge_record'] or assets['whitelist']),
            'admission_only': admission_only,
            'assets_migrated': (moved_thr > 0 or moved_tokens > 0),
            'migration_tx': tx,
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

    if _has_assets(assets_old):
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
            'ok': True,
            'old_address': old_address,
            'new_v1_address': new_v1_address,
            'action': 'moved_missing_assets',
            'moved_thr_amount': moved_thr,
            'moved_token_count': moved_tokens,
            'status': 'repaired',
            'repair_tx_id': f'repair:{old_address}:{_now()}',
        }

    unmark_legacy_migrated(old_address)
    rec['status'] = 'failed'
    rec['failed_at'] = _now()
    mmap[old_address] = rec
    _save_map_compat(mmap)
    return {
        'ok': True,
        'old_address': old_address,
        'new_v1_address': new_v1_address,
        'action': 'rolled_back_marker',
        'moved_thr_amount': 0.0,
        'moved_token_count': 0,
        'status': 'failed',
        'repair_tx_id': '',
    }


def resolve_migration(address):
    mmap = _load_map()
    if address in mmap:
        return mmap[address]
    for rec in mmap.values():
        if rec.get('new_v1_address') == address:
            return rec
    return None
