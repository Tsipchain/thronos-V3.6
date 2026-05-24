import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wallet_v1_migration as m
import wallet_v1_activation as a


class S:
    def __init__(self):
        self.bal = {'OLD': 10.0, 'NEW': 0.0}
        self.tokens = {'OLD': {'ABC': 5}, 'NEW': {}}
        self.marks = {}
        self.pledged = {'PLEDGED', 'OLD'}
        self.whitelisted = {'WHITE'}

    def get_wallet_balance(self, addr): return self.bal.get(addr, 0)
    def get_all_token_balances(self, addr): return self.tokens.get(addr, {})
    def verify_legacy_secret_once(self, old, sec): return sec == 'ok'
    def transfer_balance_atomic(self, old, new, amt): self.bal[old] -= amt; self.bal[new] = self.bal.get(new, 0)+amt
    def transfer_all_tokens_atomic(self, old, new):
        moved=0
        for k,v in list(self.tokens.get(old, {}).items()):
            if v>0:
                self.tokens.setdefault(new,{})[k]=self.tokens.setdefault(new,{}).get(k,0)+v
                self.tokens[old][k]=0; moved += 1
        return moved
    def preserve_admission_to_new_address(self, old, new):
        if old in self.pledged: self.pledged.add(new)
        if old in self.whitelisted: self.whitelisted.add(new)
    def mark_legacy_migrated(self, old, new, tx): self.marks[old] = {'new': new, 'tx': tx}
    def unmark_legacy_migrated(self, old): self.marks.pop(old, None)
    def rollback_partial_migration(self, old, new): pass

    # admission hooks
    def resolve_wallet_pledge_state(self, addr): return {'active': addr in self.pledged}
    def has_pledge_access(self, addr): return addr in self.pledged
    def is_wallet_whitelisted(self, addr): return addr in self.whitelisted
    def is_whitelisted_address(self, addr): return addr in self.whitelisted
    def get_mining_whitelist_entry(self, addr):
        if addr == 'MINER':
            return {'active': True, 'banned': False, 'pledge_ok': False, 'whitelist_legacy': True}
        return None
    def _whitelist_allows_no_pledge(self, entry): return bool(entry.get('whitelist_legacy'))


def _setup(monkeypatch, tmp_path, s):
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(a, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')


def test_inactive_non_pledged_rejected(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    try:
        a.require_active_thr_address('NOPE'); assert False
    except a.AdmissionError as e:
        assert str(e) == 'inactive_thr_address'


def test_whitelisted_address_admitted(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    assert a.require_active_thr_address('WHITE') is True


def test_pledged_address_admitted(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    assert a.require_active_thr_address('PLEDGED') is True


def test_mining_whitelist_policy_admitted(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    assert a.require_active_thr_address('MINER') is True


def test_migrated_old_blocked_only_after_completed(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"pending"}},"index_new":{}}')
    assert a.require_active_thr_address('OLD') is True
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}},"index_new":{}}')
    try:
        a.require_active_thr_address('OLD'); assert False
    except a.AdmissionError as e:
        assert str(e) == 'legacy_address_migrated_read_only'


def test_migrated_new_admitted_only_after_completed_or_repaired(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"failed"}},"index_new":{}}')
    try:
        a.require_active_thr_address('NEW'); assert False
    except a.AdmissionError:
        pass
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"repaired"}},"index_new":{}}')
    assert a.require_active_thr_address('NEW') is True


def test_old_balance_migrates_exact_and_derives_new_address(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    pub = '02' + '11' * 32
    rec = m.migrate_legacy_address('OLD', 'ok', pub)
    assert rec['status'] == 'completed'
    assert rec['new_v1_address'] == m.derive_thronos_address(pub)
    assert rec['migrated_thr_amount'] == 10.0


def test_token_balances_migrate_or_preserve(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    rec = m.migrate_legacy_address('OLD', 'ok', '02' + '11' * 32)
    assert rec['migrated_token_count'] >= 1


def test_missing_required_hooks_fail_closed(monkeypatch, tmp_path):
    class SBare:
        def verify_legacy_secret_once(self, *_): return True
        def get_wallet_balance(self, *_): return 10
        def get_all_token_balances(self, *_): return {}
    s = SBare()
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    try:
        m.migrate_legacy_address('OLD', 'ok', '02' + '11' * 32)
        assert False
    except Exception as e:
        assert 'missing_required_hook' in str(e)


def test_failed_migration_not_marked_legacy(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    def bad(*a, **k): raise RuntimeError('boom')
    s.transfer_balance_atomic = bad
    try:
        m.migrate_legacy_address('OLD', 'ok', '02' + '11' * 32)
        assert False
    except Exception:
        pass
    assert 'OLD' not in s.marks


def test_repair_moves_missing_assets_or_rolls_back(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}},"index_new":{}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['ok'] is True


def test_old_format_migration_map_resolves(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}},"index_new":{"NEW":"OLD"}}')
    rec = m.resolve_migration('NEW')
    assert rec['old_address'] == 'OLD'
