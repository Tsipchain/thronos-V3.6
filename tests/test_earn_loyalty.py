import hashlib
import json
import sqlite3

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from flask import Flask

from services.earn_account import EarnAccountStore, register_earn_account_routes
from wallet_v1_address_derivation import derive_thronos_address


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr('services.earn_account._wallet_link_requires_mobile_approval', lambda _: False)
    store = EarnAccountStore(str(tmp_path / 'earn.db'), 'loyalty-test-key')
    app = Flask(__name__)
    register_earn_account_routes(app, store)
    clients = []
    for email in ['alice@example.com', 'bob@example.com']:
        client = app.test_client()
        client.post('/api/earn/register', json={'email': email, 'password': 'password123'})
        client.post('/api/earn/login', json={'email': email, 'password': 'password123'})
        clients.append(client)
    private = ec.generate_private_key(ec.SECP256K1())
    public = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex()
    wallet = derive_thronos_address(public)
    return store, clients[0], clients[1], private, public, wallet


def proof(client, private, public, wallet):
    challenge = client.post('/api/earn/wallet-link/challenge', json={'wallet_address': wallet}).get_json()
    keys = ['action', 'challenge_id', 'expires_at', 'nonce', 'wallet_address', 'approval']
    payload = {key: str(challenge[key]) for key in keys}
    message = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    signature = private.sign(hashlib.sha256(message).digest(), ec.ECDSA(utils.Prehashed(hashes.SHA256())))
    r, s = utils.decode_dss_signature(signature)
    return {'challenge_id': challenge['challenge_id'], 'wallet_address': wallet, 'public_key': public, 'signature': f'{r:064x}{s:064x}'}


def test_wallet_address_claim_does_not_grant_vip(setup):
    store, alice, bob, private, public, wallet = setup
    data = alice.get('/api/earn/leaderboard?wallet_address=' + wallet + '&vip=true').get_json()
    assert data['loyalty']['vip'] is False
    assert data['loyalty']['wallet_linked'] is False
    assert alice.get('/api/earn/me').get_json()['loyalty']['vip'] is False


def test_valid_signed_link_grants_membership_only_to_linked_account(setup):
    store, alice, bob, private, public, wallet = setup
    response = alice.post('/api/earn/wallet-link/complete', json=proof(alice, private, public, wallet))
    assert response.status_code == 200
    me = alice.get('/api/earn/me').get_json()
    assert me['loyalty'] == {'vip': True, 'wallet_linked': True, 'tier': 'wallet_loyalty_vip', 'basis': 'verified_wallet_link'}
    assert alice.get('/api/earn/leaderboard').get_json()['loyalty']['vip'] is True
    assert bob.get('/api/earn/leaderboard').get_json()['loyalty']['vip'] is False
    assert alice.get('/api/earn/balance').get_json()['available'] == '0.000000'
    assert alice.get('/api/earn/history').get_json()['entries'] == []


def test_invalid_signature_does_not_grant_vip(setup):
    store, alice, bob, private, public, wallet = setup
    data = proof(alice, private, public, wallet)
    data['signature'] = '00' * 64
    assert alice.post('/api/earn/wallet-link/complete', json=data).status_code == 403
    assert alice.get('/api/earn/leaderboard').get_json()['loyalty']['vip'] is False


def test_another_account_cannot_use_a_signed_link_challenge(setup):
    store, alice, bob, private, public, wallet = setup
    data = proof(alice, private, public, wallet)
    assert bob.post('/api/earn/wallet-link/complete', json=data).status_code == 400
    assert bob.get('/api/earn/me').get_json()['loyalty']['vip'] is False
    assert alice.post('/api/earn/wallet-link/complete', json=data).status_code == 200


def test_membership_tracks_authoritative_link_and_does_not_leak_wallet_in_ranking(setup):
    store, alice, bob, private, public, wallet = setup
    assert alice.post('/api/earn/wallet-link/complete', json=proof(alice, private, public, wallet)).status_code == 200
    ranking = alice.get('/api/earn/leaderboard').get_json()
    assert wallet not in json.dumps(ranking)
    with sqlite3.connect(store.db_path) as con:
        con.execute('DELETE FROM earn_wallet_links WHERE wallet_address=?', (wallet,))
    assert alice.get('/api/earn/me').get_json()['loyalty']['vip'] is False


def test_pwa_leaderboard_is_confined_to_earn():
    from pathlib import Path
    pwa = (Path(__file__).parent.parent / 'public/wallet-pwa/app.js').read_text()
    home = pwa.split('async function showWallet() {', 1)[1].split('async function showEarn(options = {}) {', 1)[0]
    earn = pwa.split('async function showEarn(options = {}) {', 1)[1]
    assert 'walletLeaderboardPanel' not in home
    assert 'loyaltyBtn' not in home
    assert 'id="earnPwaLeaderboard"' in earn
    assert "ThronosEarnLeaderboard.mount(document.getElementById('earnPwaLeaderboard')" in earn
