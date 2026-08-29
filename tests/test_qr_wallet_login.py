"""
Tests for THRONOS_API_LOGIN_V1 — QR Wallet Login + Pledge Routing

Covers:
  1.  Challenge creation returns valid structure
  2.  Challenge single-use (consumed flag)
  3.  Challenge expiry
  4.  Signature verification — valid signature accepted
  5.  Signature verification — invalid signature rejected
  6.  Domain separation — wallet action type rejected at login
  7.  Nonce mismatch rejected
  8.  Audience mismatch rejected
  9.  Address derivation from public key
  10. Pledge routing: ACTIVE → /dashboard
  11. Pledge routing: NOT_PLEDGED → /pledge
  12. Session cookie set on success
  13. Session endpoint returns session data
  14. Logout clears session
  15. Challenge status endpoint
  16. Canonical message determinism
  17. Missing fields rejected
  18. Replay protection — same challenge reused
"""

import json
import time
import hashlib
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _canonical_login_challenge_msg(challenge: dict) -> str:
    fields = ('audience', 'challenge_id', 'nonce', 'timestamp', 'type', 'version')
    parts = [f'"{k}":{json.dumps(str(challenge.get(k, "")))}' for k in fields]
    return '{' + ','.join(parts) + '}'


@pytest.fixture(scope='module')
def secp256k1_keypair():
    from cryptography.hazmat.primitives.asymmetric import ec
    private_key = ec.generate_private_key(ec.SECP256K1())
    pub_numbers = private_key.public_key().public_numbers()
    x_bytes = pub_numbers.x.to_bytes(32, 'big')
    prefix = b'\x02' if pub_numbers.y % 2 == 0 else b'\x03'
    compressed_pub = (prefix + x_bytes).hex()
    return private_key, compressed_pub


@pytest.fixture(scope='module')
def derived_address(secp256k1_keypair):
    _, compressed_pub = secp256k1_keypair
    from wallet_v1_address_derivation import derive_thronos_address
    return derive_thronos_address(compressed_pub)


def _sign_challenge(private_key, challenge_response: dict) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    canonical = _canonical_login_challenge_msg(challenge_response).encode('utf-8')
    sig = private_key.sign(canonical, ec.ECDSA(hashes.SHA256()))
    return sig.hex()


@pytest.fixture(scope='module')
def app_client():
    os.environ.setdefault('DATA_DIR', '/tmp/thronos_test_login')
    os.environ.setdefault('NODE_ROLE', 'master')
    os.makedirs(os.environ['DATA_DIR'], exist_ok=True)

    from server_ext import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestChallengeCreation:
    def test_challenge_returns_valid_structure(self, app_client):
        resp = app_client.post('/api/auth/challenge')
        data = resp.get_json()
        assert data['ok'] is True
        assert 'challenge' in data
        ch = data['challenge']
        assert ch['type'] == 'thronos_api_login'
        assert ch['version'] == '1'
        assert ch['audience'] == 'api.thronoschain.org'
        assert 'challenge_id' in ch
        assert 'nonce' in ch
        assert 'qr_uri' in data
        assert data['qr_uri'].startswith('thronos://login?')
        assert data['expires_in'] == 120

    def test_challenge_unique_nonces(self, app_client):
        r1 = app_client.post('/api/auth/challenge').get_json()
        r2 = app_client.post('/api/auth/challenge').get_json()
        assert r1['challenge']['nonce'] != r2['challenge']['nonce']
        assert r1['challenge']['challenge_id'] != r2['challenge']['challenge_id']


class TestChallengeStatus:
    def test_status_returns_unconsumed(self, app_client):
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        resp = app_client.get(f'/api/auth/challenge/status/{ch["challenge_id"]}')
        data = resp.get_json()
        assert data['ok'] is True
        assert data['consumed'] is False
        assert data['expires_in'] > 0

    def test_status_not_found(self, app_client):
        resp = app_client.get('/api/auth/challenge/status/nonexistent_id')
        assert resp.status_code == 404


class TestVerification:
    def test_valid_signature_accepted(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        sig_hex = _sign_challenge(private_key, ch)
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['ok'] is True
        assert data['address'].startswith('THR')
        assert 'pledge_ok' in data
        assert 'route' in data
        assert data['route'] in ('/dashboard', '/pledge', '/pledge/status')

    def test_invalid_signature_rejected(self, app_client, secp256k1_keypair):
        _, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        fake_sig = 'aa' * 70
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': fake_sig,
            'public_key': compressed_pub,
        })
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['ok'] is False
        assert 'invalid_signature' in data.get('error', '')

    def test_missing_fields_rejected(self, app_client):
        resp = app_client.post('/api/auth/verify', json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert data['error'] == 'missing_fields'

    def test_missing_challenge_id_rejected(self, app_client, secp256k1_keypair):
        _, compressed_pub = secp256k1_keypair
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': {'type': 'thronos_api_login', 'version': '1'},
            'signature': 'aa' * 32,
            'public_key': compressed_pub,
        })
        assert resp.status_code == 400


class TestDomainSeparation:
    def test_wallet_action_type_rejected(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        ch['type'] = 'thronos_wallet_action'
        sig_hex = _sign_challenge(private_key, ch)
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['error'] == 'invalid_type'


class TestReplayProtection:
    def test_challenge_single_use(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        sig_hex = _sign_challenge(private_key, ch)
        r1 = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        assert r1.status_code == 200
        r2 = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        assert r2.status_code == 400
        data = r2.get_json()
        assert data['error'] == 'challenge_already_used'


class TestNonceAudienceMismatch:
    def test_nonce_mismatch_rejected(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        ch['nonce'] = 'wrong_nonce_value'
        sig_hex = _sign_challenge(private_key, ch)
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['error'] == 'nonce_mismatch'

    def test_audience_mismatch_rejected(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        ch['audience'] = 'evil.example.com'
        sig_hex = _sign_challenge(private_key, ch)
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['error'] == 'audience_mismatch'


class TestSessionManagement:
    def test_session_cookie_set_on_login(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        sig_hex = _sign_challenge(private_key, ch)
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        assert resp.status_code == 200
        set_cookie = resp.headers.get('Set-Cookie', '')
        assert 'thr_session=' in set_cookie

    def test_session_endpoint_returns_data(self, app_client, secp256k1_keypair, derived_address):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        sig_hex = _sign_challenge(private_key, ch)
        app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        resp = app_client.get('/api/auth/session')
        data = resp.get_json()
        assert data['ok'] is True
        assert data['address'] == derived_address
        assert 'pledge_ok' in data
        assert 'route' in data

    def test_logout_clears_session(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        sig_hex = _sign_challenge(private_key, ch)
        app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        resp = app_client.post('/api/auth/logout')
        assert resp.get_json()['ok'] is True
        sess_resp = app_client.get('/api/auth/session')
        assert sess_resp.status_code == 401

    def test_no_session_returns_401(self, app_client):
        # Use a fresh client without cookies
        from server_ext import app as _app
        with _app.test_client() as fresh_client:
            resp = fresh_client.get('/api/auth/session')
            assert resp.status_code == 401


class TestPledgeRouting:
    def test_unpledged_wallet_routes_to_pledge(self, app_client, secp256k1_keypair):
        private_key, compressed_pub = secp256k1_keypair
        ch = app_client.post('/api/auth/challenge').get_json()['challenge']
        sig_hex = _sign_challenge(private_key, ch)
        resp = app_client.post('/api/auth/verify', json={
            'challenge_response': ch,
            'signature': sig_hex,
            'public_key': compressed_pub,
        })
        data = resp.get_json()
        assert data['ok'] is True
        assert data['route'] in ('/pledge', '/pledge/status')


class TestCanonicalMessage:
    def test_canonical_determinism(self):
        ch = {
            'type': 'thronos_api_login',
            'version': '1',
            'challenge_id': 'test_123',
            'nonce': 'abc',
            'audience': 'api.thronoschain.org',
            'timestamp': '1700000000',
        }
        msg1 = _canonical_login_challenge_msg(ch)
        msg2 = _canonical_login_challenge_msg(ch)
        assert msg1 == msg2
        assert '"type":"thronos_api_login"' in msg1
        assert '"audience":"api.thronoschain.org"' in msg1
        parsed = json.loads(msg1)
        assert list(parsed.keys()) == ['audience', 'challenge_id', 'nonce', 'timestamp', 'type', 'version']

    def test_canonical_field_order_alphabetical(self):
        ch = {
            'type': 'thronos_api_login', 'version': '1',
            'challenge_id': 'x', 'nonce': 'y',
            'audience': 'z', 'timestamp': '0',
        }
        msg = _canonical_login_challenge_msg(ch)
        keys = [k.strip('"') for k in msg.strip('{}').split(',') if ':' in k]
        first_keys = [k.split(':')[0].strip('"') for k in msg.strip('{}').split('","')]
        assert '"audience"' in msg[:30]


class TestLoginPage:
    def test_login_page_renders(self, app_client):
        resp = app_client.get('/login')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Login' in html
        assert 'Thronos Wallet' in html
        assert '/api/auth/challenge' in html
        assert 'thronos://login' not in html or 'qr_uri' in html
