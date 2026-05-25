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
    def set_token_balances_for_address(self, addr, balances): self.tokens[addr] = dict(balances or {})
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

    def resolve_wallet_pledge_state(self, addr): return {'active': addr in self.pledged}
    def has_pledge_access(self, addr): return addr in self.pledged
    def is_wallet_whitelisted(self, addr): return addr in self.whitelisted
    def is_whitelisted_address(self, addr): return addr in self.whitelisted
    def get_mining_whitelist_entry(self, addr):
        if addr == 'MINER': return {'active': True, 'banned': False, 'pledge_ok': False, 'whitelist_legacy': True}
        return None
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
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}},"index_new":{"NEW":"OLD"}}')
    out = m.repair_migration('OLD', 'NEW')
    assert out['status'] in ('repaired', 'failed')


def test_old_map_format_resolves(monkeypatch, tmp_path):
    s = S(); _setup(monkeypatch, tmp_path, s)
    (tmp_path/'m.json').write_text('{"migrations":{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}},"index_new":{"NEW":"OLD"}}')
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
    assert s.tokens['OLD'].get('ABC') == 5
    assert s.tokens['NEW'].get('ABC', 0) == 0
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
