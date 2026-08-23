"""
Tests for V1 Withdraw Funds-Safety Gate (PR #761)

Covers 12 security cases:
  1.  Sufficient balance — withdrawal allowed
  2.  Insufficient balance — rejected
  3.  Zero balance wallet — rejected
  4.  Exact balance withdrawal — succeeds, remainder is zero
  5.  Double-spend via two different nonces — second rejected
  6.  Replay — same nonce reused — rejected
  7.  Tampered payload — payload_hash_mismatch
  8.  USDT withdrawal uses THR/USDT pool
  9.  USDC withdrawal uses THR/USDC pool (not THR/USDT)
 10.  Pool-save failure — wallet balance rolled back
 11.  Queue-save failure — wallet + pool rolled back
 12.  Queue entry records intent_nonce for payout idempotency audit
"""

import json
import hashlib
import time
import os
import sys
import shutil
import secrets

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_wallet_action_intent(intent: dict) -> str:
    fields = ('action', 'amount', 'asset', 'chain', 'created_at', 'from_thr',
              'nonce', 'payload_hash', 'recipient', 'type', 'version', 'wallet_id')
    parts = [f'"{k}":{json.dumps(str(intent.get(k, "")))}' for k in fields]
    return '{' + ','.join(parts) + '}'


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


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


@pytest.fixture(scope='module')
def data_dir():
    d = '/tmp/thronos_test_withdraw_gate'
    os.makedirs(d, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def app_client(data_dir, derived_address, secp256k1_keypair):
    os.environ['DATA_DIR'] = data_dir
    os.environ['NODE_ROLE'] = 'master'
    os.environ.setdefault('BSC_RPC_URL', 'https://bsc-testnet.example.com')
    os.environ.setdefault('BSC_PAYOUT_ADDRESS', '0x' + 'aa' * 20)
    os.environ.setdefault('BASE_RPC_URL', 'https://base-testnet.example.com')
    os.environ.setdefault('BASE_PAYOUT_ADDRESS', '0x' + 'bb' * 20)

    _init_data(data_dir, derived_address, balance=50.0, usdt_pool=1000.0, usdc_pool=500.0)

    from server_ext import app
    app.config['TESTING'] = True

    import server as _srv
    _srv.WITHDRAW_CHAIN_CONFIG['bsc']['rpc_url'] = 'https://bsc-testnet.example.com'
    _srv.WITHDRAW_CHAIN_CONFIG['bsc']['payout_wallet'] = '0x' + 'aa' * 20
    _srv.WITHDRAW_CHAIN_CONFIG['base']['rpc_url'] = 'https://base-testnet.example.com'
    _srv.WITHDRAW_CHAIN_CONFIG['base']['payout_wallet'] = '0x' + 'bb' * 20

    with app.test_client() as client:
        yield client

    _cleanup_nonces(data_dir)


def _init_data(data_dir, thr_address, balance=50.0, usdt_pool=1000.0, usdc_pool=500.0):
    balances = {}
    if balance > 0:
        balances[thr_address] = {'USDT_bsc': balance, 'USDC_base': balance}
    _write_json(os.path.join(data_dir, 'internal_asset_balances.json'), balances)

    pools = [
        {'token_a': 'THR', 'token_b': 'USDT', 'reserves_a': 10000.0, 'reserves_b': usdt_pool},
        {'token_a': 'THR', 'token_b': 'USDC', 'reserves_a': 10000.0, 'reserves_b': usdc_pool},
    ]
    _write_json(os.path.join(data_dir, 'pools.json'), pools)

    _write_json(os.path.join(data_dir, 'withdraw_queue.json'), [])
    _write_json(os.path.join(data_dir, 'wallet_history.json'), [])
    _write_json(os.path.join(data_dir, 'chain.json'), [])

    os.makedirs(os.path.join(data_dir, 'custom_ledgers'), exist_ok=True)


def _cleanup_nonces(data_dir):
    nonces_file = os.path.join(data_dir, 'wallet_action_nonces.json')
    if os.path.exists(nonces_file):
        os.remove(nonces_file)


def _write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)


def _read_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def _build_withdraw_request(private_key, compressed_pub, thr_address,
                            amount=10.0, token='USDT', dest_chain='bsc',
                            dest_address='0x' + 'ab' * 20, nonce=None):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    if nonce is None:
        nonce = secrets.token_hex(16)

    payload = {
        'amount': amount,
        'token': token,
        'dest_chain': dest_chain,
        'dest_address': dest_address,
    }
    ph = _payload_hash(payload)

    intent = {
        'type': 'thronos_wallet_action',
        'version': '1',
        'action': 'crosschain_withdraw',
        'wallet_id': thr_address,
        'from_thr': thr_address,
        'nonce': nonce,
        'created_at': str(int(time.time())),
        'payload_hash': ph,
        'amount': str(amount),
        'asset': token,
        'chain': dest_chain,
        'recipient': dest_address,
    }

    canonical = _canonical_wallet_action_intent(intent).encode('utf-8')
    sig = private_key.sign(canonical, ec.ECDSA(hashes.SHA256()))

    return {
        'intent': intent,
        'signature': sig.hex(),
        'public_key': compressed_pub,
        'payload': payload,
    }, nonce


class TestBalanceOwnership:
    """Tests 1-4: Balance sufficiency checks."""

    def test_sufficient_balance_allowed(self, app_client, secp256k1_keypair, derived_address, data_dir):
        private_key, compressed_pub = secp256k1_keypair
        req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=10.0)
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        data = resp.get_json()
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
        assert data['ok'] is True
        assert data['amount'] == 10.0
        assert data['amount_net'] == 9.8
        bals = _read_json(os.path.join(data_dir, 'internal_asset_balances.json'))
        assert bals[derived_address]['USDT_bsc'] == 40.0

    def test_insufficient_balance_rejected(self, app_client, secp256k1_keypair, derived_address):
        private_key, compressed_pub = secp256k1_keypair
        req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=100.0)
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['ok'] is False
        assert data['error'] == 'insufficient_balance'
        assert data['balance'] == 50.0
        assert data['required'] == 100.0

    def test_zero_balance_rejected(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=0.0)
        private_key, compressed_pub = secp256k1_keypair
        req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=5.0)
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['error'] == 'insufficient_balance'
        assert data['balance'] == 0.0

    def test_exact_balance_withdrawal(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=10.0)
        private_key, compressed_pub = secp256k1_keypair
        req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=10.0)
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['ok'] is True
        bals = _read_json(os.path.join(data_dir, 'internal_asset_balances.json'))
        assert bals[derived_address]['USDT_bsc'] == 0.0


class TestDoubleSpend:
    """Test 5: Two different nonces against depleted balance."""

    def test_second_nonce_rejected_after_balance_depleted(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=30.0)
        private_key, compressed_pub = secp256k1_keypair
        req1, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=25.0)
        r1 = app_client.post('/api/wallet/v1/withdraw', json=req1)
        assert r1.status_code == 200
        assert r1.get_json()['ok'] is True

        req2, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=25.0)
        r2 = app_client.post('/api/wallet/v1/withdraw', json=req2)
        data2 = r2.get_json()
        assert r2.status_code == 400
        assert data2['error'] == 'insufficient_balance'
        assert data2['balance'] == 5.0


class TestReplay:
    """Test 6: Same nonce replayed — rejected by intent verification."""

    def test_same_nonce_rejected(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=100.0)
        private_key, compressed_pub = secp256k1_keypair
        fixed_nonce = secrets.token_hex(16)
        req1, _ = _build_withdraw_request(private_key, compressed_pub, derived_address,
                                          amount=5.0, nonce=fixed_nonce)
        r1 = app_client.post('/api/wallet/v1/withdraw', json=req1)
        assert r1.status_code == 200

        req2, _ = _build_withdraw_request(private_key, compressed_pub, derived_address,
                                          amount=5.0, nonce=fixed_nonce)
        r2 = app_client.post('/api/wallet/v1/withdraw', json=req2)
        data2 = r2.get_json()
        assert r2.status_code == 400
        assert data2['error'] == 'nonce_reused'


class TestTamper:
    """Test 7: Tampered payload hash mismatch."""

    def test_tampered_amount_rejected(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=100.0)
        private_key, compressed_pub = secp256k1_keypair
        req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=5.0)
        req['payload']['amount'] = 50.0
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['error'] == 'payload_hash_mismatch'


class TestPoolIsolation:
    """Tests 8-9: Token-specific pool accounting."""

    def test_usdt_withdrawal_uses_usdt_pool(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=50.0, usdt_pool=1000.0, usdc_pool=500.0)
        private_key, compressed_pub = secp256k1_keypair
        req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address,
                                         amount=10.0, token='USDT', dest_chain='bsc')
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        assert resp.status_code == 200

        pools = _read_json(os.path.join(data_dir, 'pools.json'))
        usdt_pool = next(p for p in pools
                         if {(p.get('token_a') or '').upper(),
                             (p.get('token_b') or '').upper()} == {'THR', 'USDT'})
        usdc_pool = next(p for p in pools
                         if {(p.get('token_a') or '').upper(),
                             (p.get('token_b') or '').upper()} == {'THR', 'USDC'})
        assert usdt_pool['reserves_b'] == 1000.0 - 9.8
        assert usdc_pool['reserves_b'] == 500.0

    def test_usdc_withdrawal_uses_usdc_pool(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=50.0, usdt_pool=1000.0, usdc_pool=500.0)
        private_key, compressed_pub = secp256k1_keypair
        req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address,
                                         amount=10.0, token='USDC', dest_chain='base')
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        assert resp.status_code == 200

        pools = _read_json(os.path.join(data_dir, 'pools.json'))
        usdt_pool = next(p for p in pools
                         if {(p.get('token_a') or '').upper(),
                             (p.get('token_b') or '').upper()} == {'THR', 'USDT'})
        usdc_pool = next(p for p in pools
                         if {(p.get('token_a') or '').upper(),
                             (p.get('token_b') or '').upper()} == {'THR', 'USDC'})
        assert usdt_pool['reserves_b'] == 1000.0
        assert usdc_pool['reserves_b'] == 500.0 - 9.8


class TestRollback:
    """Tests 10-11: Failure safety — rollback on pool/queue save errors."""

    def test_pool_save_failure_restores_balance(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=50.0)
        private_key, compressed_pub = secp256k1_keypair

        import server as _srv
        original_save = _srv.save_pools

        def _failing_save(pools):
            raise IOError("disk full")

        _srv.save_pools = _failing_save
        try:
            req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=10.0)
            resp = app_client.post('/api/wallet/v1/withdraw', json=req)
            assert resp.status_code == 500
        finally:
            _srv.save_pools = original_save

        bals = _read_json(os.path.join(data_dir, 'internal_asset_balances.json'))
        assert bals[derived_address]['USDT_bsc'] == 50.0

    def test_queue_save_failure_restores_balance_and_pool(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=50.0, usdt_pool=1000.0)
        private_key, compressed_pub = secp256k1_keypair

        import server as _srv
        original_save_json = _srv.save_json

        call_count = [0]

        def _selective_fail(path, data):
            if 'withdraw_queue' in str(path):
                raise IOError("queue write failed")
            return original_save_json(path, data)

        _srv.save_json = _selective_fail
        try:
            req, _ = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=10.0)
            resp = app_client.post('/api/wallet/v1/withdraw', json=req)
            assert resp.status_code == 500
        finally:
            _srv.save_json = original_save_json

        bals = _read_json(os.path.join(data_dir, 'internal_asset_balances.json'))
        assert bals[derived_address]['USDT_bsc'] == 50.0
        pools = _read_json(os.path.join(data_dir, 'pools.json'))
        usdt_pool = next(p for p in pools
                         if {(p.get('token_a') or '').upper(),
                             (p.get('token_b') or '').upper()} == {'THR', 'USDT'})
        assert usdt_pool['reserves_b'] == 1000.0


class TestPayoutIdempotency:
    """Test 12: Queue entry records intent_nonce for dedup audit."""

    def test_queue_entry_has_intent_nonce(self, app_client, secp256k1_keypair, derived_address, data_dir):
        _init_data(data_dir, derived_address, balance=50.0)
        private_key, compressed_pub = secp256k1_keypair
        req, nonce_used = _build_withdraw_request(private_key, compressed_pub, derived_address, amount=5.0)
        resp = app_client.post('/api/wallet/v1/withdraw', json=req)
        assert resp.status_code == 200

        queue = _read_json(os.path.join(data_dir, 'withdraw_queue.json'))
        assert len(queue) >= 1
        entry = queue[-1]
        assert entry['intent_nonce'] == nonce_used
        assert entry['balance_before'] == 50.0
        assert entry['balance_after'] == 45.0
        assert entry['thr_address'] == derived_address
