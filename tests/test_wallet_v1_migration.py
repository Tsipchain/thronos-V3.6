import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wallet_v1_migration as m
import wallet_v1_activation as a


class S:
    def __init__(self):
        self.bal = {'OLD': 10.0, 'NEW': 0.0}
        self.tokens = {'ABC': {'OLD': 5, 'NEW': 0}}
        self.marks = {}
        self.pledged = {'PLEDGED', 'OLD'}
        self.whitelisted = {'WHITE'}
        self._json = {}
        self.MUSIC_ARTISTS_FILE = 'artists.json'
        self.MUSIC_TRACKS_FILE = 'tracks.json'
        self.MUSIC_REWARDS_FILE = 'rewards.json'
        self.MUSIC_ENTITLEMENTS_FILE = 'entitlements.json'
        self.MUSIC_PLAYLISTS_FILE = 'playlists.json'
        self.MUSIC_ARTIST_PROFILES_FILE = 'artist_profiles.json'
        self.MUSIC_OFFLINE_ITEMS_FILE = 'offline_items.json'
        self.MUSIC_ROYALTIES_FILE = 'royalties.json'
        self.mining_whitelist = {}
        self.mining_payouts = {}
        self.pool_rewards = {}
        self.agent_bindings = {}

    def load_json(self, path, default=None): return self._json.get(path, default)
    def save_json(self, path, data): self._json[path] = data

    def load_token_balances(self): return self.tokens
    def save_token_balances(self, balances): self.tokens = balances
    def get_wallet_balances_cached(self, addr):
        toks = {'THR': float(self.bal.get(addr, 0.0) or 0.0)}
        for sym, holders in (self.tokens or {}).items():
            if isinstance(holders, dict):
                toks[str(sym).upper()] = float(holders.get(addr, 0.0) or 0.0)
        return {'tokens': [{'symbol': k, 'balance': v} for k, v in toks.items()]}
    def get_wallet_balance(self, addr): return self.bal.get(addr, 0)
    def get_all_token_balances(self, addr): return self.tokens.get(addr, {})
    def verify_legacy_secret_once(self, old, sec): return sec == 'ok'
    def transfer_balance_atomic(self, old, new, amt): self.bal[old] -= amt; self.bal[new] = self.bal.get(new, 0)+amt
    def set_token_balances_for_address(self, addr, balances):
        # balances is symbol->amount for one address
        for sym, amt in (balances or {}).items():
            self.tokens.setdefault(sym, {})
            self.tokens[sym][addr] = float(amt or 0)
    def transfer_all_tokens_atomic(self, old, new):
        moved=0
        for sym, holders in list((self.tokens or {}).items()):
            v = float((holders or {}).get(old, 0) or 0)
            if v>0:
                holders[new]=float(holders.get(new,0) or 0)+v
                holders[old]=0
                moved += 1
        return moved
    def preserve_admission_to_new_address(self, old, new):
        if old in self.pledged: self.pledged.add(new)
        if old in self.whitelisted: self.whitelisted.add(new)
    def mark_legacy_migrated(self, old, new, tx): self.marks[old] = {'new': new, 'tx': tx}
    def unmark_legacy_migrated(self, old): self.marks.pop(old, None)
    def rollback_partial_migration(self, old, new): pass

    def resolve_wallet_pledge_state(self, addr): return {'active': addr in self.pledged}
    def has_pledge_access(self, addr): return addr in self.pledged
    def is_wallet_whitelisted(self, addr): return addr in self.whitelisted
    def is_whitelisted_address(self, addr): return addr in self.whitelisted
    def get_mining_whitelist_entry(self, addr):
        if addr in self.mining_whitelist:
            return self.mining_whitelist.get(addr)
        if addr == 'MINER':
            return {'active': True, 'banned': False, 'pledge_ok': False, 'whitelist_legacy': True}
        return None
    def get_mining_payout_state(self, addr):
        return self.mining_payouts.get(addr)
    def get_pool_rewards_state(self, addr):
        return self.pool_rewards.get(addr)
    def get_agent_wallet_binding_state(self, addr):
        return self.agent_bindings.get(addr)
    def move_mining_whitelist_entry(self, old, new):
        if old not in self.mining_whitelist:
            return 0
        self.mining_whitelist[new] = dict(self.mining_whitelist[old])
        self.mining_whitelist.pop(old, None)
        return 1
    def move_mining_payout_state(self, old, new):
        st = self.mining_payouts.get(old)
        if not st:
            return 0
        self.mining_payouts[new] = self.mining_payouts.get(new, 0) + st
        self.mining_payouts[old] = 0
        return 1
    def move_pool_rewards_state(self, old, new):
        st = self.pool_rewards.get(old)
        if not st:
            return 0
        self.pool_rewards[new] = self.pool_rewards.get(new, 0) + st
        self.pool_rewards[old] = 0
        return 1
    def move_agent_wallet_binding_state(self, old, new):
        st = self.agent_bindings.get(old)
        if not st:
            return 0
        self.agent_bindings[new] = st
        self.agent_bindings.pop(old, None)
        return 1
    def _whitelist_allows_no_pledge(self, entry): return bool(entry.get('whitelist_legacy'))


def _setup(monkeypatch, tmp_path, s):
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(a, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')


def test_legacy_secret_verifier_works_and_wrong_rejected(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    assert m.verify_legacy_secret_once('OLD', 'ok') is True
    assert m.verify_legacy_secret_once('OLD', 'wrong') is False


def test_missing_legacy_verifier_fail_closed(monkeypatch, tmp_path):
    class SBare:
        def get_wallet_balance(self, *_): return 0
        def get_all_token_balances(self, *_): return {}
    sb = SBare()
    monkeypatch.setattr(m, '_server', lambda: sb)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    try:
        m.verify_legacy_secret_once('OLD', 'x')
        assert False
    except Exception as e:
        assert 'missing_legacy_seed_hash' in str(e)


def test_admission_hooks_still_work(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    assert a.require_active_thr_address('WHITE') is True
    assert a.require_active_thr_address('PLEDGED') is True
    assert a.require_active_thr_address('MINER') is True


def test_old_and_new_status_gates(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"pending"}},"index_new":{}}')
    assert a.require_active_thr_address('OLD') is True
    try:
        a.require_active_thr_address('NEW'); assert False
    except a.AdmissionError:
        pass
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}},"index_new":{}}')
    try:
        a.require_active_thr_address('OLD'); assert False
    except a.AdmissionError:
        pass
    assert a.require_active_thr_address('NEW') is True


def test_balance_and_tokens_migrate(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    rec = m.migrate_legacy_address('OLD', 'ok', '02' + '11'*32)
    assert rec['migrated_thr_amount'] == 10.0
    assert rec['migrated_token_count'] >= 1


def test_bad_migration_repair_moves_missing(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['status'] in ('repaired', 'failed')


def test_old_map_format_resolves(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    rec = m.resolve_migration('NEW')
    assert rec['old_address'] == 'OLD'


def test_token_transfer_failure_restores_thr(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.tokens = {'OLD': {'ABC': 5}, 'NEW': {}}
    def boom_tokens(old, new):
        raise RuntimeError('token_fail')
    s.transfer_all_tokens_atomic = boom_tokens
    try:
        m.migrate_legacy_address('OLD', 'ok', '02' + '22'*32)
        assert False
    except Exception:
        pass
    assert s.bal['OLD'] == 10.0
    assert s.bal['NEW'] == 0.0
    assert not (tmp_path/'m.json').exists()


def test_preserve_admission_failure_restores_assets_and_no_admission(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    def boom_preserve(old, new):
        raise RuntimeError('preserve_fail')
    s.preserve_admission_to_new_address = boom_preserve
    try:
        m.migrate_legacy_address('OLD', 'ok', '02' + '33'*32)
        assert False
    except Exception:
        pass
    assert s.bal['OLD'] == 10.0
    assert s.bal['NEW'] == 0.0
    assert s.bal['OLD'] == 10.0
    assert s.bal['NEW'] == 0.0
    assert 'NEW' not in s.pledged
    assert 'OLD' not in s.marks
    assert not (tmp_path/'m.json').exists()
    # failed migration does not grant new admission and old is not read-only
    try:
        a.require_active_thr_address('NEW')
        assert False
    except a.AdmissionError:
        pass
    assert a.require_active_thr_address('OLD') is True


def test_repair_token_failure_after_thr_move_restores_thr(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    def boom_tokens(old, new):
        raise RuntimeError('repair_token_fail')
    s.transfer_all_tokens_atomic = boom_tokens
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception as e:
        assert 'repair_failed' in str(e)
    assert s.bal['OLD'] == 10.0
    assert s.bal['NEW'] == 0.0


def test_repair_admission_failure_restores_thr_and_tokens(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    def boom_preserve(old, new):
        raise RuntimeError('repair_preserve_fail')
    s.preserve_admission_to_new_address = boom_preserve
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception as e:
        assert 'repair_failed' in str(e)
    assert s.bal['OLD'] == 10.0
    assert s.bal['NEW'] == 0.0
    assert s.bal['OLD'] == 10.0
    assert s.bal['NEW'] == 0.0


def test_failed_repair_does_not_mark_repaired_or_grant_new_admission(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    s.transfer_all_tokens_atomic = lambda *_: (_ for _ in ()).throw(RuntimeError('repair_fail'))
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception:
        pass
    rec = m.resolve_migration('OLD')
    assert rec['status'] == 'failed'
    try:
        a.require_active_thr_address('NEW')
        assert False
    except a.AdmissionError:
        pass
    assert rec['status'] != 'repaired'


def test_repaired_thr_only_can_move_remaining_tokens_without_thr_remove(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 0.0001}
    s.tokens = {'WBTC': {'OLD': 2, 'NEW': 0}, 'L2E': {'OLD': 3, 'NEW': 0}}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"repaired","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['moved_thr_amount'] == 0.0
    assert out['moved_token_count'] == 2
    assert s.bal['NEW'] == 0.0001
    assert s.tokens['WBTC']['OLD'] == 0
    assert s.tokens['WBTC']['NEW'] == 2


def test_token_repair_idempotent_no_duplication(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 0.0001}
    s.tokens = {'WBTC': {'OLD': 0, 'NEW': 2}, 'L2E': {'OLD': 0, 'NEW': 3}}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"repaired","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['moved_token_count'] == 0
    assert s.tokens['WBTC']['NEW'] == 2


def test_token_repair_rollback_restores_tokens(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 0.0001}
    s.tokens = {'WBTC': {'OLD': 2, 'NEW': 0}}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    def boom(_o,_n):
        raise RuntimeError('boom')
    s.preserve_admission_to_new_address = boom
    try:
        m.repair_migration('OLD','NEW')
        assert False
    except Exception:
        pass
    assert s.bal['OLD'] == 0.0
    assert s.bal['NEW'] == 0.0001


def test_assets_migrated_flag_tracks_remaining_tokens(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 0.1}
    s.tokens = {'WBTC': {'OLD': 1, 'NEW': 0}}
    s._json[s.MUSIC_ARTISTS_FILE] = [{'wallet_address': 'OLD'}]
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD','NEW')
    assert out['assets_migrated'] is True
    rec = m.resolve_migration('OLD')
    assert rec['assets_migrated'] is True


def test_music_bindings_repaired_and_assets_flag(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {'WBTC': {'OLD': 2, 'NEW': 0}}
    s._json[s.MUSIC_ARTISTS_FILE] = [{'wallet_address': 'OLD', 'name': 'artist'}]
    s._json[s.MUSIC_TRACKS_FILE] = [{'owner_address': 'OLD', 'creator_address': 'OLD'}]
    s._json[s.MUSIC_REWARDS_FILE] = [{'reward_address': 'OLD'}]
    s._json[s.MUSIC_ENTITLEMENTS_FILE] = [{'owner_address': 'OLD'}]
    s._json[s.MUSIC_PLAYLISTS_FILE] = [{'wallet_address': 'OLD'}]
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['music_bindings_repaired'] is True
    assert out['ecosystem_bindings_repaired'] is True
    assert out['assets_migrated'] is True
    assert s._json[s.MUSIC_ARTISTS_FILE][0]['wallet_address'] == 'NEW'
    assert s._json[s.MUSIC_TRACKS_FILE][0]['owner_address'] == 'NEW'
    assert s._json[s.MUSIC_TRACKS_FILE][0]['creator_address'] == 'OLD'  # provenance kept historical


def test_assets_migrated_false_when_music_not_repaired(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {'WBTC': {'OLD': 0, 'NEW': 1}}
    # disable music repair hooks and json I/O
    s.load_json = None
    s.save_json = None
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['assets_migrated'] is False


class AuthS(S):
    def __init__(self):
        super().__init__()
        self.bal = {'OLD': 0.0, 'NEW': 0.0001}
        self.auth = {
            'OLD': {'THR': 0.0, 'WBTC': 2.0, 'L2E': 3.0, 'JAM': 4.0},
            'NEW': {'THR': 0.0001, 'WBTC': 0.0, 'L2E': 0.0, 'JAM': 0.0},
        }
        self.tokens = {'JAM': {'OLD': 0, 'NEW': 0}}  # stale source intentionally empty

    def load_token_balances(self): return self.tokens
    def save_token_balances(self, balances): self.tokens = balances
    def get_wallet_balances_cached(self, addr):
        toks = self.auth.get(addr, {})
        return {'tokens': [{'symbol': k, 'balance': v} for k, v in toks.items()]}

    def transfer_all_tokens_atomic(self, old, new):
        moved = 0
        for sym, bal in list(self.auth.get(old, {}).items()):
            if sym == 'THR':
                continue
            if float(bal or 0) > 0:
                self.auth.setdefault(new, {}).setdefault(sym, 0.0)
                self.auth[new][sym] += float(bal)
                self.auth[old][sym] = 0.0
                moved += 1
        return moved


class HookZeroCustomS(S):
    """Simulates production hook that does nothing for custom tokens."""
    def __init__(self):
        super().__init__()
        self.bal = {'OLD': 0.0, 'NEW': 1.0}
        self.tokens = {
            '7CEB': {'OLD': 118.55, 'NEW': 0.0},
            'CVT': {'OLD': 10000000, 'NEW': 0.0},
            'HPENNIS': {'OLD': 18929319.95, 'NEW': 0.0},
            'JAM': {'OLD': 100903, 'NEW': 0.0},
            'LOUMIDIS': {'OLD': 7756027, 'NEW': 0.0},
            'MAR': {'OLD': 973635, 'NEW': 0.0},
        }

    def transfer_all_tokens_atomic(self, old, new):
        return 0


class LiveCustomLedgerS(S):
    """Simulates production /api/balances custom-token source (custom registry + ledgers)."""
    def __init__(self):
        super().__init__()
        self.bal = {'OLD': 0.0, 'NEW': 1.0}
        self.custom_tokens = {
            '7CEB': {'id': 'tok-7ceb', 'decimals': 2},
            'CVT': {'id': 'tok-cvt', 'decimals': 6},
            'HPENNIS': {'id': 'tok-hpennis', 'decimals': 2},
            'JAM': {'id': 'tok-jam', 'decimals': 3},
            'LOUMIDIS': {'id': 'tok-loumidis', 'decimals': 3},
            'MAR': {'id': 'tok-mar', 'decimals': 3},
        }
        self.custom_ledgers = {
            'tok-7ceb': {'OLD': 118.55, 'NEW': 0.0},
            'tok-cvt': {'OLD': 10000000, 'NEW': 0.0},
            'tok-hpennis': {'OLD': 18929319.95, 'NEW': 0.0},
            'tok-jam': {'OLD': 100903, 'NEW': 0.0},
            'tok-loumidis': {'OLD': 7756027, 'NEW': 0.0},
            'tok-mar': {'OLD': 973635, 'NEW': 0.0},
        }

    def load_custom_tokens(self, include_legacy=True):
        return self.custom_tokens

    def load_custom_token_ledger(self, token_id):
        return dict(self.custom_ledgers.get(token_id, {}))

    def save_custom_token_ledger(self, token_id, ledger):
        self.custom_ledgers[token_id] = dict(ledger or {})

    def get_wallet_balances_cached(self, addr):
        toks = {
            'THR': float(self.bal.get(addr, 0.0) or 0.0),
            'WBTC': 0.0,
            'L2E': 0.0,
        }
        for sym, meta in self.custom_tokens.items():
            led = self.custom_ledgers.get(meta['id'], {})
            toks[sym] = float(led.get(addr, 0.0) or 0.0)
        return {'tokens': [{'symbol': k, 'balance': v} for k, v in toks.items()]}

    def transfer_all_tokens_atomic(self, old, new):
        # Simulate production hook existing but skipping custom ledgers.
        return 0


def test_authoritative_balances_source_drives_token_repair(monkeypatch, tmp_path):
    s = AuthS(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['moved_thr_amount'] == 0.0
    assert out['moved_token_count'] >= 3
    assert s.auth['OLD']['WBTC'] == 0.0
    assert s.auth['NEW']['WBTC'] == 2.0


def test_repeat_repair_idempotent_with_authoritative_source(monkeypatch, tmp_path):
    s = AuthS(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    _ = m.repair_migration('OLD', 'NEW')
    out2 = m.repair_migration('OLD', 'NEW')
    assert out2['action'] in ('no_missing_assets', 'moved_missing_assets')
    assert out2['moved_thr_amount'] == 0.0
    assert m._remaining_old_token_count('OLD') == 0


def test_wbtc_nonzero_missing_writable_source_fails_closed(monkeypatch, tmp_path):
    class NoWrite:
        def __init__(self):
            self.bal={'OLD':0.0,'NEW':0.0}
        def get_wallet_balance(self,a): return self.bal.get(a,0.0)
        def get_wallet_balances_cached(self,a):
            return {'tokens':[{'symbol':'THR','balance':self.bal.get(a,0.0)},{'symbol':'WBTC','balance':1.0 if a=='OLD' else 0.0}]}
        def verify_legacy_secret_once(self,*_): return True
        def preserve_admission_to_new_address(self,*_): return None
        def mark_legacy_migrated(self,*_): return None
        def rollback_partial_migration(self,*_): return None
    s=NoWrite(); _setup(monkeypatch,tmp_path,s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD','NEW')
        assert False
    except Exception as e:
        assert 'missing_authoritative_token_write_source:WBTC' in str(e)


def test_l2e_nonzero_missing_writable_source_fails_closed(monkeypatch, tmp_path):
    class NoWrite2:
        def __init__(self): self.bal={'OLD':0.0,'NEW':0.0}
        def get_wallet_balance(self,a): return self.bal.get(a,0.0)
        def get_wallet_balances_cached(self,a):
            return {'tokens':[{'symbol':'THR','balance':self.bal.get(a,0.0)},{'symbol':'L2E','balance':2.0 if a=='OLD' else 0.0}]}
        def verify_legacy_secret_once(self,*_): return True
        def preserve_admission_to_new_address(self,*_): return None
        def mark_legacy_migrated(self,*_): return None
        def rollback_partial_migration(self,*_): return None
    s=NoWrite2(); _setup(monkeypatch,tmp_path,s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD','NEW')
        assert False
    except Exception as e:
        assert 'missing_authoritative_token_write_source:L2E' in str(e)


def test_live_shape_custom_tokens_move_and_counts(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {
        '7CEB': {'OLD': 1, 'NEW': 0},
        'CVT': {'OLD': 2, 'NEW': 0},
        'HPENNIS': {'OLD': 3, 'NEW': 0},
        'JAM': {'OLD': 4, 'NEW': 0},
        'LOUMIDIS': {'OLD': 5, 'NEW': 0},
        'MAR': {'OLD': 6, 'NEW': 0},
    }
    assert m._remaining_old_token_count('OLD') == 6
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['moved_thr_amount'] == 0.0
    assert out['moved_token_count'] == 6
    assert out['remaining_old_token_count'] == 0
    for sym in ('7CEB','CVT','HPENNIS','JAM','LOUMIDIS','MAR'):
        assert s.tokens[sym]['OLD'] == 0
        assert s.tokens[sym]['NEW'] > 0
    assert m._remaining_old_token_count('OLD') == 0


def test_custom_source_missing_fails_closed(monkeypatch, tmp_path):
    class MissingCustom(S):
        load_token_balances = None
        save_token_balances = None
        transfer_all_tokens_atomic = None
    s = MissingCustom(); _setup(monkeypatch, tmp_path, s)
    s.bal={'OLD':0.0,'NEW':0.1}
    s.tokens={'JAM':{'OLD':2,'NEW':0}}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD','NEW')
        assert False
    except Exception as e:
        assert 'missing_authoritative_custom_token_write_source' in str(e)


def test_mining_continuity_repair_moves_whitelist_and_payout(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {'JAM': {'OLD': 0, 'NEW': 1}}
    s.mining_whitelist = {'OLD': {'active': True, 'banned': False, 'pledge_ok': False, 'whitelist_legacy': True}}
    s.mining_payouts = {'OLD': 5}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['mining_bindings_repaired'] is True
    assert s.mining_whitelist.get('NEW', {}).get('active') is True
    assert s.mining_payouts.get('NEW') == 5
    assert s.mining_payouts.get('OLD') == 0


def test_repeat_repair_no_duplicate_mining_or_pool(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {'JAM': {'OLD': 0, 'NEW': 1}}
    s.mining_whitelist = {'OLD': {'active': True, 'banned': False, 'pledge_ok': True}}
    s.mining_payouts = {'OLD': 7}
    s.pool_rewards = {'OLD': 9}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    _ = m.repair_migration('OLD', 'NEW')
    out2 = m.repair_migration('OLD', 'NEW')
    assert s.mining_payouts.get('NEW') == 7
    assert s.pool_rewards.get('NEW') == 9
    assert out2['moved_thr_amount'] == 0.0


def test_missing_mining_write_source_fails_closed(monkeypatch, tmp_path):
    class NoMiningWrite(S):
        move_mining_whitelist_entry = None
        move_mining_payout_state = None
    s = NoMiningWrite(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {'JAM': {'OLD': 0, 'NEW': 1}}
    s.mining_whitelist = {'OLD': {'active': True, 'banned': False, 'pledge_ok': True}}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception as e:
        assert 'missing_mining_binding_write_source' in str(e)


def test_missing_pool_write_source_fails_closed(monkeypatch, tmp_path):
    class NoPoolWrite(S):
        move_pool_rewards_state = None
    s = NoPoolWrite(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {'JAM': {'OLD': 0, 'NEW': 1}}
    s.pool_rewards = {'OLD': 10}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception as e:
        assert 'missing_pool_rewards_write_source' in str(e)


def test_missing_agent_write_source_fails_closed(monkeypatch, tmp_path):
    class NoAgentWrite(S):
        move_agent_wallet_binding_state = None
    s = NoAgentWrite(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 1.0}
    s.tokens = {'JAM': {'OLD': 0, 'NEW': 1}}
    s.agent_bindings = {'OLD': {'service': 'pytheia'}}
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception as e:
        assert 'missing_agent_wallet_binding_write_source' in str(e)


def test_hook_zero_custom_tokens_fallback_still_moves(monkeypatch, tmp_path):
    s = HookZeroCustomS(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['moved_token_count'] == 6
    assert out['remaining_old_token_count'] == 0
    for sym in ('7CEB', 'CVT', 'HPENNIS', 'JAM', 'LOUMIDIS', 'MAR'):
        assert s.tokens[sym]['OLD'] == 0.0
        assert s.tokens[sym]['NEW'] > 0


def test_remaining_tokens_cannot_report_no_missing_assets(monkeypatch, tmp_path):
    s = HookZeroCustomS(); _setup(monkeypatch, tmp_path, s)
    # disable custom writable source to force fail-closed/incomplete condition
    s.save_token_balances = None
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception as e:
        assert 'missing_authoritative_custom_token_write_source' in str(e)


def test_remaining_tokens_implies_assets_not_migrated(monkeypatch, tmp_path):
    s = HookZeroCustomS(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['remaining_old_token_count'] == 0
    assert out['assets_migrated'] is True


def test_repeat_repair_no_duplicate_custom_token_credit(monkeypatch, tmp_path):
    s = HookZeroCustomS(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    _ = m.repair_migration('OLD', 'NEW')
    out2 = m.repair_migration('OLD', 'NEW')
    assert out2['moved_token_count'] == 0
    assert out2['action'] != 'incomplete_repair'
    assert s.tokens['7CEB']['NEW'] == 118.55


def test_live_custom_ledger_source_migrates_exact_amounts(monkeypatch, tmp_path):
    s = LiveCustomLedgerS(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['moved_token_count'] == 6
    assert out['remaining_old_token_count'] == 0
    assert out['assets_migrated'] is True
    assert s.custom_ledgers['tok-7ceb']['OLD'] == 0.0
    assert s.custom_ledgers['tok-cvt']['OLD'] == 0.0
    assert s.custom_ledgers['tok-hpennis']['OLD'] == 0.0
    assert s.custom_ledgers['tok-jam']['OLD'] == 0.0
    assert s.custom_ledgers['tok-loumidis']['OLD'] == 0.0
    assert s.custom_ledgers['tok-mar']['OLD'] == 0.0
    assert s.custom_ledgers['tok-7ceb']['NEW'] == 118.55
    assert s.custom_ledgers['tok-cvt']['NEW'] == 10000000
    assert s.custom_ledgers['tok-hpennis']['NEW'] == 18929319.95
    assert s.custom_ledgers['tok-jam']['NEW'] == 100903
    assert s.custom_ledgers['tok-loumidis']['NEW'] == 7756027
    assert s.custom_ledgers['tok-mar']['NEW'] == 973635


def test_live_custom_ledger_repeat_repair_idempotent(monkeypatch, tmp_path):
    s = LiveCustomLedgerS(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    _ = m.repair_migration('OLD', 'NEW')
    out2 = m.repair_migration('OLD', 'NEW')
    assert out2['moved_token_count'] == 0
    assert out2['remaining_old_token_count'] == 0
    assert s.custom_ledgers['tok-7ceb']['NEW'] == 118.55


def test_music_artist_playlist_offline_and_royalty_bindings_repaired(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 0.1}
    s.tokens = {'WBTC': {'OLD': 0, 'NEW': 1}}
    s._json[s.MUSIC_ARTISTS_FILE] = [{'wallet_address': 'OLD', 'name': 'artist'}]
    s._json[s.MUSIC_ARTIST_PROFILES_FILE] = [{'artist_wallet': 'OLD', 'artist': 'OLD'}]
    s._json[s.MUSIC_PLAYLISTS_FILE] = [{'wallet_address': 'OLD'}, {'owner_address': 'OLD'}]
    s._json[s.MUSIC_OFFLINE_ITEMS_FILE] = [{'user_address': 'OLD'}]
    s._json[s.MUSIC_ENTITLEMENTS_FILE] = [{'owner_address': 'OLD'}]
    s._json[s.MUSIC_REWARDS_FILE] = [{'payout_address': 'OLD'}]
    s._json[s.MUSIC_ROYALTIES_FILE] = [{'royalty_address': 'OLD'}]
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['music_bindings_repaired'] is True
    assert out['ecosystem_bindings_repaired'] is True
    assert out['assets_migrated'] is True
    assert out['status'] == 'repaired'
    assert s._json[s.MUSIC_ARTISTS_FILE][0]['wallet_address'] == 'NEW'
    assert s._json[s.MUSIC_ARTIST_PROFILES_FILE][0]['artist_wallet'] == 'NEW'
    assert s._json[s.MUSIC_PLAYLISTS_FILE][0]['wallet_address'] == 'NEW'
    assert s._json[s.MUSIC_PLAYLISTS_FILE][1]['owner_address'] == 'NEW'
    assert s._json[s.MUSIC_OFFLINE_ITEMS_FILE][0]['user_address'] == 'NEW'
    assert s._json[s.MUSIC_REWARDS_FILE][0]['payout_address'] == 'NEW'
    assert s._json[s.MUSIC_ROYALTIES_FILE][0]['royalty_address'] == 'NEW'


def test_music_repeat_repair_idempotent_no_duplicates(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 0.1}
    s.tokens = {'WBTC': {'OLD': 0, 'NEW': 1}}
    s._json[s.MUSIC_PLAYLISTS_FILE] = [{'wallet_address': 'OLD'}, {'wallet_address': 'OLD'}]
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed","assets_migrated":false}},"index_new":{"NEW":"OLD"}}')
    _ = m.repair_migration('OLD', 'NEW')
    playlists_after_first = list(s._json[s.MUSIC_PLAYLISTS_FILE])
    out2 = m.repair_migration('OLD', 'NEW')
    assert out2['moved_token_count'] == 0
    assert s._json[s.MUSIC_PLAYLISTS_FILE] == playlists_after_first


def test_missing_music_write_source_fails_closed(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    s.bal = {'OLD': 0.0, 'NEW': 0.1}
    s.tokens = {'WBTC': {'OLD': 0, 'NEW': 1}}
    s._json[s.MUSIC_PLAYLISTS_FILE] = [{'wallet_address': 'OLD'}]
    s.save_json = None
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{"NEW":"OLD"}}')
    try:
        m.repair_migration('OLD', 'NEW')
        assert False
    except Exception as e:
        assert 'missing_music_binding_write_source' in str(e)
