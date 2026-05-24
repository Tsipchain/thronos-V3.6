import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wallet_v1_migration as m
import wallet_v1_activation as a


class S:
    def __init__(self):
        self.bal = {'OLD': 10.0, 'NEW': 0.0}
        self.tokens = {'OLD': {'ABC': 5}, 'NEW': {}}
        self.marked = {}

    def get_wallet_balance(self, addr):
        return self.bal.get(addr, 0)

    def get_all_token_balances(self, addr):
        return self.tokens.get(addr, {})

    def verify_legacy_secret_once(self, old, sec):
        return sec == 'ok'

    def transfer_balance_atomic(self, old, new, amt):
        if self.bal.get(old, 0) < amt:
            raise RuntimeError('insufficient')
        self.bal[old] -= amt
        self.bal[new] = self.bal.get(new, 0) + amt

    def transfer_all_tokens_atomic(self, old, new):
        moved = 0
        for k, v in list(self.tokens.get(old, {}).items()):
            if v > 0:
                self.tokens.setdefault(new, {})[k] = self.tokens.setdefault(new, {}).get(k, 0) + v
                self.tokens[old][k] = 0
                moved += 1
        return moved

    def mark_legacy_migrated(self, old, new, tx):
        self.marked[old] = {'new': new, 'tx': tx}

    def rollback_partial_migration(self, old, new):
        pass


def test_balance_migrates_exact(monkeypatch, tmp_path):
    s = S()
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    rec = m.migrate_legacy_address('OLD', 'ok', '02'+'11'*32, 'NEW')
    assert rec['status'] == 'completed'
    assert s.bal['OLD'] == 0
    assert s.bal['NEW'] == 10.0


def test_token_balances_migrated(monkeypatch, tmp_path):
    s = S()
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    rec = m.migrate_legacy_address('OLD', 'ok', '02'+'11'*32, 'NEW')
    assert rec['migrated_token_count'] >= 1
    assert s.tokens['OLD']['ABC'] == 0
    assert s.tokens['NEW']['ABC'] == 5


def test_zero_balance_admission_only(monkeypatch, tmp_path):
    s = S(); s.bal['OLD']=0; s.tokens['OLD']={}
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    rec = m.migrate_legacy_address('OLD', 'ok', '02'+'11'*32, 'NEW')
    assert rec['admission_only'] is True
    assert rec['migrated_thr_amount'] == 0
    assert rec['assets_migrated'] is False


def test_failed_migration_not_marked(monkeypatch, tmp_path):
    s = S()
    def bad_transfer(*args, **kwargs): raise RuntimeError('boom')
    s.transfer_balance_atomic = bad_transfer
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    try:
        m.migrate_legacy_address('OLD', 'ok', '02'+'11'*32, 'NEW')
        assert False
    except RuntimeError:
        pass
    assert 'OLD' not in s.marked
    assert not (tmp_path / 'm.json').exists()


def test_repair_moves_missing_or_rolls_back(monkeypatch, tmp_path):
    s = S()
    monkeypatch.setattr(m, '_server', lambda: s)
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    (tmp_path / 'm.json').write_text('{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}}')
    out = m.repair_migration('OLD','NEW')
    assert out['ok'] is True


def test_old_address_read_only_only_after_completed(monkeypatch, tmp_path):
    monkeypatch.setattr(m, 'MIGRATION_FILE', tmp_path / 'm.json')
    (tmp_path / 'm.json').write_text('{"OLD":{"old_address":"OLD","new_v1_address":"NEW","status":"completed"}}')
    try:
        a.require_active_thr_address('OLD')
        assert False
    except a.AdmissionError:
        pass
