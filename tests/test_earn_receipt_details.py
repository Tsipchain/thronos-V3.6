import hashlib
import logging
import sqlite3

import pytest
from flask import Flask

from services.earn_account import EarnAccountStore, register_earn_account_routes, timewall_postback_hash


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('TIMEWALL_POSTBACK_LIVE', '0')
    monkeypatch.setenv('TIMEWALL_SECRET_KEY', 'test-only-secret')
    monkeypatch.setenv('TIMEWALL_POSTBACK_IPS', '127.0.0.1')
    monkeypatch.setenv('TIMEWALL_THC_CONVERSION', '670')
    store = EarnAccountStore(str(tmp_path / 'earn.db'), 'test-identity-key')
    user = store.register('receipt@example.com', 'password123')
    app = Flask(__name__)
    register_earn_account_routes(app, store)
    client = app.test_client()
    token = client.post('/api/earn/login', json={
        'email': 'receipt@example.com', 'password': 'password123',
    }).get_json()['access_token']
    provider_id = store.provider_user_id(user['earn_user_id'], 'timewall')
    return store, user, client, {'Authorization': 'Bearer ' + token}, provider_id


def payload(provider_id):
    return {'user_ID': provider_id, 'revenue': '0.10', 'withdrawid': 'provider-real-reference',
            'hash': timewall_postback_hash(provider_id, '0.10', 'test-only-secret')}


def credit(store, provider_id):
    store.record_timewall_receipt(event_id='receipt-001', provider_user_id=provider_id,
        revenue_raw='0.10', event_type='survey', offer_name='Completed survey',
        payload={'hash': 'private-signature', 'ip': 'private-ip', 'extra': 'private-payload'})


def test_details_require_authentication_and_ownership(setup):
    store, user, client, auth, provider_id = setup
    credit(store, provider_id)
    entry = store.thc_history(user['earn_user_id'])[0]
    url = '/api/earn/history/' + entry['entry_id']
    assert client.get(url).status_code == 200  # restored same-origin cookie
    anonymous = client.application.test_client()
    assert anonymous.get(url).status_code == 401
    other = client.application.test_client()
    other.post('/api/earn/register', json={'email': 'other@example.com', 'password': 'password123'})
    other.post('/api/earn/login', json={'email': 'other@example.com', 'password': 'password123'})
    assert other.get(url).status_code == 404
    assert other.get('/api/earn/history/missing').status_code == 404


def test_details_expose_real_receipt_and_audit_without_raw_payload(setup):
    store, user, client, auth, provider_id = setup
    credit(store, provider_id)
    entry = store.thc_history(user['earn_user_id'])[0]
    response = client.get('/api/earn/history/' + entry['entry_id'], headers=auth)
    data = response.get_json()
    assert data['entry']['source_ref'] == 'receipt-001'
    assert data['entry']['amount'] == '67.000000'
    assert data['entry']['state'] == 'pending'
    assert data['entry']['note'] == 'survey:Completed survey'
    assert data['entry']['estimated_clearance_at'] is None
    assert len(data['events']) == 2
    assert data['events'][0]['event_type'] == 'provider_receipt'
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'private-' not in response.get_data(as_text=True)
    assert 'earn_user_id' not in data['entry']
    assert store.thc_balance(user['earn_user_id'])['available'] == '0.000000'


def test_expired_estimate_never_clears_a_receipt_on_read(setup):
    store, user, client, auth, provider_id = setup
    credit(store, provider_id)
    entry = store.thc_history(user['earn_user_id'])[0]
    with sqlite3.connect(store.db_path) as con:
        con.execute('UPDATE thc_ledger SET estimated_clearance_at=1 WHERE entry_id=?', (entry['entry_id'],))
    for _ in range(2):
        data = client.get('/api/earn/history/' + entry['entry_id'], headers=auth).get_json()
        assert data['entry']['state'] == 'pending'
        assert data['entry']['cleared_at'] is None
        assert len(data['events']) == 2


def test_verified_clearance_is_visible_on_original_receipt(setup):
    store, user, client, auth, provider_id = setup
    credit(store, provider_id)
    store.record_verified_clearance(source='timewall', source_ref='receipt-001',
        event_ref='verified-provider-clearance', new_state='confirmed', provider_status='cleared', cleared_at=1700000000)
    entry = store.thc_history(user['earn_user_id'])[0]
    data = client.get('/api/earn/history/' + entry['entry_id'], headers=auth).get_json()
    assert data['entry']['state'] == 'pending'
    assert data['entry']['earn_hold_phase'] == 'waiting'
    assert data['entry']['cleared_at'] == 1700000000
    assert len(data['events']) == 3
    assert len(store.thc_history(user['earn_user_id'])) == 1


def test_disabled_preflight_verifies_without_credit_and_can_be_retried_live(setup, monkeypatch, caplog):
    store, user, client, auth, provider_id = setup
    request = payload(provider_id)
    with caplog.at_level(logging.INFO, logger='services.earn_account'):
        assert client.get('/api/earn/timewall/postback', query_string=request).status_code == 503
        assert client.get('/api/earn/timewall/postback', query_string=request).status_code == 503
    assert 'verified_callback' in caplog.text
    assert hashlib.sha256(request['withdrawid'].encode()).hexdigest()[:16] in caplog.text
    assert request['hash'] not in caplog.text
    assert provider_id not in caplog.text
    assert store.thc_history(user['earn_user_id']) == []
    with sqlite3.connect(store.db_path) as con:
        assert con.execute('SELECT COUNT(*) FROM timewall_receipts').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM thc_ledger_audit').fetchone()[0] == 0
    monkeypatch.setenv('TIMEWALL_POSTBACK_LIVE', '1')
    for _ in range(2):
        assert client.get('/api/earn/timewall/postback', query_string=request).status_code == 200
    entries = store.thc_history(user['earn_user_id'])
    assert len(entries) == 1
    assert entries[0]['state'] == 'pending'
    assert entries[0]['amount'] == '67.000000'
    assert len(store.thc_receipt_details(user['earn_user_id'], entries[0]['entry_id'])['events']) == 2


@pytest.mark.parametrize('invalid', ['hash', 'ip', 'unknown_user', 'revenue'])
def test_preflight_does_not_verify_invalid_callbacks(setup, caplog, invalid):
    store, user, client, auth, provider_id = setup
    request = payload(provider_id)
    environment = {}
    if invalid == 'hash': request['hash'] = 'invalid'
    if invalid == 'ip': environment['REMOTE_ADDR'] = '203.0.113.1'
    if invalid == 'unknown_user':
        request['user_ID'] = 'tw_unknown'
        request['hash'] = timewall_postback_hash('tw_unknown', '0.10', 'test-only-secret')
    if invalid == 'revenue':
        request['revenue'] = 'NaN'
        request['hash'] = timewall_postback_hash(provider_id, 'NaN', 'test-only-secret')
    with caplog.at_level(logging.INFO, logger='services.earn_account'):
        assert client.get('/api/earn/timewall/postback', query_string=request, environ_overrides=environment).status_code == 503
    assert 'verified_callback' not in caplog.text
    assert store.thc_history(user['earn_user_id']) == []
