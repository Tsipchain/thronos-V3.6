import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from flask import Flask

from services.earn_account import EarnAccountStore, EarnError, register_earn_account_routes

T0 = 1793900000
WEEK = 7 * 86400
MASTER = {'NODE_ROLE': 'master', 'READ_ONLY': '0', 'SCHEDULER_ENABLED': '1'}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0)
    monkeypatch.setenv('TIMEWALL_THC_CONVERSION', '1')
    monkeypatch.setenv('TIMEWALL_ALLOW_DECIMALS', '1')
    store = EarnAccountStore(str(tmp_path / 'earn.db'), 'internal-hold-test')
    store.register('hold@example.com', 'password123')
    _, token = store.login('hold@example.com', 'password123')
    user = store.user_for_session(token)
    return store, user, token


def credit(store, user, ref='one', *, provider='cpx'):
    if provider == 'cpx':
        store.record_cpx_receipt(trans_id=ref, cpx_ext_user_id=user['cpx_ext_user_id'], status=1, amount_local='10.000001', payload={})
    elif provider == 'timewall':
        store.record_timewall_receipt(event_id=ref, provider_user_id=store.provider_user_id(user['earn_user_id'], provider), revenue_raw='10.000001', payload={})
    else:
        method = store.record_bitcotasks_receipt if provider == 'bitcotasks' else store.record_pure_receipt
        method(trans_id=ref, provider_user_id=store.provider_user_id(user['earn_user_id'], provider), status=1, reward_thc='10.000001', payload={})
    return next(e for e in store.thc_history(user['earn_user_id']) if e['source_ref'] == ref)


@pytest.mark.parametrize('provider', ['cpx', 'timewall', 'bitcotasks', 'pure'])
def test_each_verified_provider_starts_its_own_seven_day_hold(setup, provider):
    store, user, _ = setup
    entry = credit(store, user, provider=provider)
    assert entry['earn_hold_started_at'] == T0
    assert entry['earn_hold_until'] == T0 + WEEK
    assert entry['earn_hold_phase'] == 'waiting'
    assert entry['earn_hold_days_remaining'] == 7
    assert entry['estimated_clearance_at'] is None
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'


def test_duplicate_callback_and_restart_do_not_restart_the_hold(setup, monkeypatch):
    store, user, _ = setup
    first = credit(store, user)
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + 100)
    again = credit(store, user)
    restarted = EarnAccountStore(store.db_path, 'internal-hold-test')
    row = restarted.thc_history(user['earn_user_id'])[0]
    assert first['entry_id'] == again['entry_id'] == row['entry_id']
    assert row['earn_hold_until'] == T0 + WEEK
    events = restarted.thc_receipt_details(user['earn_user_id'], row['entry_id'])['events']
    assert sum(e['event_type'] == 'earn_hold_started' for e in events) == 1


def test_master_releases_exactly_at_deadline_once_without_claiming_provider_payment(setup, monkeypatch):
    store, user, _ = setup
    original = credit(store, user)
    with patch.dict(os.environ, MASTER):
        monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK - 1)
        assert store.release_mature_earn_holds() == 0
        monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK)
        assert store.release_mature_earn_holds() == 1
        assert store.release_mature_earn_holds() == 0
    row = store.thc_history(user['earn_user_id'])[0]
    assert row['entry_id'] == original['entry_id']
    assert row['state'] == 'confirmed'
    assert row['earn_hold_released_at'] == T0 + WEEK
    assert row['cleared_at'] is None
    assert row['settlement_ref'] is None
    assert row['provider_status'] == original['provider_status']
    assert store.thc_balance(user['earn_user_id'])['available'] == '10.000001'
    assert len(store.thc_history(user['earn_user_id'])) == 1


@pytest.mark.parametrize('flags', [
    {'NODE_ROLE': 'replica'}, {'READ_ONLY': '1'}, {'SCHEDULER_ENABLED': '0'},
])
def test_replica_read_only_or_disabled_scheduler_cannot_release(setup, monkeypatch, flags):
    store, user, _ = setup
    credit(store, user)
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK)
    with patch.dict(os.environ, {**MASTER, **flags}):
        assert store.release_mature_earn_holds() == 0
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'


def test_api_reads_and_provider_clearance_cannot_bypass_internal_hold(setup):
    store, user, token = setup
    entry = credit(store, user)
    with pytest.raises(EarnError, match='earn_hold_requires_server_release'):
        store.transition_thc(entry['entry_id'], 'confirmed')
    row, changed = store.record_verified_clearance(source='cpx_survey', source_ref='one',
        event_ref='real-provider-clearance', new_state='confirmed', provider_status='provider_confirmed', cleared_at=T0)
    assert changed is True and row['state'] == 'pending'
    assert row['cleared_at'] == T0
    app = Flask(__name__)
    register_earn_account_routes(app, store)
    client = app.test_client()
    auth = {'Authorization': 'Bearer ' + token}
    response = client.get('/api/earn/history/' + entry['entry_id'], headers=auth)
    assert response.get_json()['entry']['state'] == 'pending'
    assert response.get_json()['entry']['earn_pending_reason'] == 'earn_hold_active'
    assert not any('release' in rule.rule for rule in app.url_map.iter_rules())
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'


def test_expired_hold_reads_remain_pending_until_master_runs(setup, monkeypatch):
    store, user, _ = setup
    credit(store, user)
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK + 1)
    for _ in range(2):
        row = store.thc_history(user['earn_user_id'])[0]
        assert row['state'] == 'pending'
        assert row['earn_hold_phase'] == 'due'
        assert row['earn_hold_seconds_remaining'] == 0
        assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'


def test_different_receipts_release_at_their_own_deadlines(setup, monkeypatch):
    store, user, _ = setup
    a = credit(store, user, 'a')
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + 3600)
    b = credit(store, user, 'b')
    assert b['earn_hold_until'] == a['earn_hold_until'] + 3600
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK)
    with patch.dict(os.environ, MASTER): assert store.release_mature_earn_holds() == 1
    assert store.thc_balance(user['earn_user_id'])['available'] == '10.000001'
    assert store.thc_balance(user['earn_user_id'])['pending'] == '10.000001'


def test_reversal_before_or_after_release_removes_availability(setup, monkeypatch):
    store, user, _ = setup
    credit(store, user, 'before')
    credit(store, user, 'after')
    store.record_cpx_receipt(trans_id='before', cpx_ext_user_id=user['cpx_ext_user_id'], status=2, amount_local='10.000001', payload={'reason': 'invalid_answers'})
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK)
    with patch.dict(os.environ, MASTER): assert store.release_mature_earn_holds() == 1
    store.record_cpx_receipt(trans_id='after', cpx_ext_user_id=user['cpx_ext_user_id'], status=2, amount_local='10.000001', payload={'reason': 'provider_reversal'})
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'
    assert all(e['state'] == 'reversed' for e in store.thc_history(user['earn_user_id']))


def test_unverified_credit_cannot_release_even_with_forged_hold_fields(setup, monkeypatch):
    store, user, _ = setup
    row, _ = store.record_thc_credit(user['earn_user_id'], 'timewall', 'no-provider-receipt', '999')
    with sqlite3.connect(store.db_path) as con:
        con.execute("UPDATE thc_ledger SET earn_hold_policy='earn-seven-day-v1',earn_hold_until=? WHERE entry_id=?", (T0, row['entry_id']))
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK)
    with patch.dict(os.environ, MASTER): assert store.release_mature_earn_holds() == 0


def test_migration_backfills_only_pending_verified_receipts_from_original_time(setup):
    store, user, _ = setup
    entry = credit(store, user)
    with sqlite3.connect(store.db_path) as con:
        con.execute('UPDATE thc_ledger SET earn_hold_started_at=NULL,earn_hold_until=NULL,earn_hold_policy=NULL WHERE entry_id=?', (entry['entry_id'],))
        con.execute("DELETE FROM thc_ledger_audit WHERE event_type='earn_hold_started'")
    store.record_thc_credit(user['earn_user_id'], 'manual', 'unverified', '1')
    restarted = EarnAccountStore(store.db_path, 'internal-hold-test')
    rows = {r['source_ref']: r for r in restarted.thc_history(user['earn_user_id'])}
    assert rows['one']['earn_hold_until'] == T0 + WEEK
    assert rows['unverified']['earn_hold_until'] is None


def test_concurrent_master_runs_release_one_entry_once(setup, monkeypatch):
    store, user, _ = setup
    entry = credit(store, user)
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + WEEK)
    with patch.dict(os.environ, MASTER), ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: store.release_mature_earn_holds(), range(2)))
    assert sum(counts) == 1
    events = store.thc_receipt_details(user['earn_user_id'], entry['entry_id'])['events']
    assert sum(e['event_type'] == 'earn_hold_released' for e in events) == 1


def test_existing_available_balance_is_not_relocked_on_migration(setup):
    store, user, _ = setup
    entry = credit(store, user)
    with sqlite3.connect(store.db_path) as con:
        con.execute("UPDATE thc_ledger SET state='confirmed',earn_hold_started_at=NULL,earn_hold_until=NULL,earn_hold_policy=NULL WHERE entry_id=?", (entry['entry_id'],))
    restarted = EarnAccountStore(store.db_path, 'internal-hold-test')
    row = restarted.thc_history(user['earn_user_id'])[0]
    assert row['state'] == 'confirmed'
    assert row['earn_hold_until'] is None
    assert restarted.thc_balance(user['earn_user_id'])['available'] == '10.000001'


def test_shortened_stored_deadline_cannot_release_early(setup, monkeypatch):
    store, user, _ = setup
    entry = credit(store, user)
    with sqlite3.connect(store.db_path) as con:
        con.execute('UPDATE thc_ledger SET earn_hold_until=? WHERE entry_id=?', (T0 + 1, entry['entry_id']))
    monkeypatch.setattr('services.earn_account.time.time', lambda: T0 + 2)
    with patch.dict(os.environ, MASTER):
        assert store.release_mature_earn_holds() == 0
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'
