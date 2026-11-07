import json
import sqlite3
from unittest.mock import patch

import pytest
from flask import Flask

from services.earn_account import (
    EarnAccountStore, register_earn_account_routes,
    _LEADERBOARD_START as START, _LEADERBOARD_END as END,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr('services.earn_account.time.time', lambda: START + 3600)
    return EarnAccountStore(str(tmp_path / 'earn.db'), 'leaderboard-test-key')


def account(store, name):
    email = name + '@private-domain.test'
    store.register(email, 'password123')
    _, token = store.login(email, 'password123')
    return store.user_for_session(token), token


def receipt(store, user, ref, amount, *, provider='cpx', at=START + 100):
    with patch('services.earn_account.time.time', return_value=at):
        if provider == 'cpx':
            return store.record_cpx_receipt(trans_id=ref, cpx_ext_user_id=user['cpx_ext_user_id'],
                status=1, amount_local=amount, payload={})
        provider_id = store.provider_user_id(user['earn_user_id'], provider)
        if provider == 'timewall':
            with patch.dict('os.environ', {'TIMEWALL_THC_CONVERSION': '1', 'TIMEWALL_ALLOW_DECIMALS': '1'}):
                return store.record_timewall_receipt(event_id=ref, provider_user_id=provider_id,
                    revenue_raw=amount, payload={})
        method = store.record_bitcotasks_receipt if provider == 'bitcotasks' else store.record_pure_receipt
        return method(trans_id=ref, provider_user_id=provider_id, status=1, reward_thc=amount, payload={})


def test_cycle_is_exactly_30_days_and_survives_restart(store):
    before = store.leaderboard(at_time=START - 1)
    running = store.leaderboard(at_time=START)
    ended = store.leaderboard(at_time=END)
    assert END - START == 30 * 86400
    assert before['phase'] == 'upcoming'
    assert running['phase'] == 'running'
    assert running['seconds_remaining'] == 30 * 86400
    assert ended['phase'] == 'ended'
    assert ended['seconds_remaining'] == 0
    restarted = EarnAccountStore(store.db_path, 'leaderboard-test-key').leaderboard(at_time=START + 120)
    assert restarted['campaign_id'] == running['campaign_id']
    assert restarted['ends_at'] == END
    assert restarted['seconds_remaining'] == 30 * 86400 - 120
    assert restarted['prizes_enabled'] is False


@pytest.mark.parametrize('provider', ['cpx', 'bitcotasks', 'pure', 'timewall'])
def test_all_provider_receipts_count_as_provisional_without_wallet(store, provider):
    user, _ = account(store, provider)
    receipt(store, user, 'real-' + provider, '12.345678', provider=provider)
    result = store.leaderboard(caller_user_id=user['earn_user_id'])
    assert result['total_active'] == 1
    assert result['your_rank'] == 1
    assert result['provisional'] is True
    assert result['your_score'] == {'total_earned': '12.345678', 'pending_earned': '12.345678', 'cleared_earned': '0.000000', 'completions': 1}
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'


def test_pending_and_cleared_are_separate_and_clearance_does_not_double_count(store, monkeypatch):
    user, _ = account(store, 'splits')
    receipt(store, user, 'one', '0.100001')
    receipt(store, user, 'two', '0.200002', at=START + 200)
    store.record_verified_clearance(source='cpx_survey', source_ref='one', event_ref='verified-clearance',
        new_state='confirmed', provider_status='cleared', cleared_at=END + 100)
    monkeypatch.setattr('services.earn_account.time.time', lambda: START + 100 + 7 * 86400)
    with patch.dict('os.environ', {'NODE_ROLE': 'master', 'READ_ONLY': '0', 'SCHEDULER_ENABLED': '1'}):
        assert store.release_mature_earn_holds() == 1
    result = store.leaderboard(caller_user_id=user['earn_user_id'], at_time=END + 200)
    assert result['your_score'] == {'total_earned': '0.300003', 'pending_earned': '0.200002', 'cleared_earned': '0.100001', 'completions': 2}
    assert result['phase'] == 'ended'


def test_receipt_time_boundaries_are_start_inclusive_end_exclusive(store):
    user, _ = account(store, 'boundaries')
    for ref, at in [('before', START - 1), ('start', START), ('last', END - 1), ('end', END)]:
        receipt(store, user, ref, '1', at=at)
    assert store.leaderboard(at_time=START + 50)['entries'][0]['total_earned'] == '1.000000'
    assert store.leaderboard(at_time=END + 100)['entries'][0]['total_earned'] == '2.000000'


def test_duplicate_callbacks_do_not_inflate_score(store):
    user, _ = account(store, 'duplicate')
    for _ in range(3): receipt(store, user, 'same-ref', '5')
    score = store.leaderboard()['entries'][0]
    assert score['total_earned'] == '5.000000'
    assert score['completions'] == 1


def test_reversals_remove_score_even_after_cycle_end(store):
    user, _ = account(store, 'reversal')
    receipt(store, user, 'reversed-ref', '5')
    store.record_cpx_receipt(trans_id='reversed-ref', cpx_ext_user_id=user['cpx_ext_user_id'],
        status=2, amount_local='5', payload={'reason': 'provider_reversal'})
    result = store.leaderboard(caller_user_id=user['earn_user_id'], at_time=END + 100)
    assert result['entries'] == []
    assert result['your_rank'] is None
    assert result['your_score']['total_earned'] == '0.000000'


def test_non_provider_credits_and_wrong_owner_receipts_are_excluded(store):
    a, _ = account(store, 'actual')
    b, _ = account(store, 'unverified')
    receipt(store, a, 'actual-ref', '3')
    store.record_thc_credit(b['earn_user_id'], 'cpx', 'actual-ref', '999999')
    store.record_thc_credit(b['earn_user_id'], 'timewall', 'missing-provider-receipt', '999999')
    store.record_thc_credit(b['earn_user_id'], 'train_to_earn', 'workout', '999999')
    result = store.leaderboard(caller_user_id=b['earn_user_id'])
    assert result['total_active'] == 1
    assert result['your_rank'] is None
    assert result['entries'][0]['total_earned'] == '3.000000'


def test_equal_decimal_scores_share_rank_and_order_is_stable(store):
    users = [account(store, name)[0] for name in ['tie-a', 'tie-b', 'third']]
    for user, amount in zip(users, ['0.300003', '0.300003', '0.100001']):
        receipt(store, user, user['earn_user_id'], amount)
    first = store.leaderboard()
    second = store.leaderboard()
    assert [e['rank'] for e in first['entries']] == [1, 1, 3]
    assert first['entries'] == second['entries']


def test_callers_rank_and_score_are_returned_outside_visible_top(store):
    a, _ = account(store, 'leader')
    b, _ = account(store, 'outside')
    receipt(store, a, 'high', '20')
    receipt(store, b, 'low', '1')
    result = store.leaderboard(limit=1, caller_user_id=b['earn_user_id'])
    assert len(result['entries']) == 1
    assert result['your_rank'] == 2
    assert result['your_score']['total_earned'] == '1.000000'


def test_api_is_authenticated_personalized_and_does_not_leak_identity(store):
    user, token = account(store, 'secret-person')
    receipt(store, user, 'provider-reference-must-stay-private', '2')
    app = Flask(__name__)
    register_earn_account_routes(app, store)
    client = app.test_client()
    anon_resp = client.get('/api/earn/leaderboard')
    assert anon_resp.status_code == 200
    anon_data = anon_resp.get_json()
    assert anon_data['entries'][0]['is_caller'] is False
    response = client.get('/api/earn/leaderboard?month_start=0&at_time=0', headers={'Authorization': 'Bearer ' + token})
    data = response.get_json()
    assert response.headers['Cache-Control'] == 'no-store'
    assert data['starts_at'] == START
    assert data['server_now'] == START + 3600
    assert data['entries'][0]['is_caller'] is True
    assert data['entries'][0]['display_name'].startswith('Earner-')
    raw = json.dumps(data)
    for private in [user['email'], 'private-domain.test', user['earn_user_id'], user['cpx_ext_user_id'], 'provider-reference-must-stay-private']:
        assert private not in raw
    anonymous_caller = store.leaderboard()
    assert anonymous_caller['entries'][0]['is_caller'] is False


def test_ranking_reads_do_not_write_credits_or_audit_events(store):
    user, _ = account(store, 'read-only')
    receipt(store, user, 'read-only-ref', '2')
    with sqlite3.connect(store.db_path) as con:
        before = [con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in ['thc_ledger', 'thc_ledger_audit', 'cpx_receipts']]
    for _ in range(3): store.leaderboard(at_time=END + 100)
    with sqlite3.connect(store.db_path) as con:
        after = [con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in ['thc_ledger', 'thc_ledger_audit', 'cpx_receipts']]
    assert before == after
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'
