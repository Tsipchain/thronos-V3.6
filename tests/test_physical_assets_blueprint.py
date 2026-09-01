"""
Tests for Physical Assets Blueprint — isolated Flask endpoint testing.

Uses Flask test client with injected mock signature verification.
Does NOT import server.py or server_ext.py.
"""

import copy
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

import physical_assets_service as pa_svc
from physical_assets_blueprint import physical_assets_bp, init_physical_assets_blueprint


CREATOR = 'THR0000000000000000000000000000000000000001'
CREATOR2 = 'THR0000000000000000000000000000000000000002'


def _init_test_env(
    verify_ok=True,
    payload_hash_ok=True,
    verify_error=('invalid_signature', 'signature verification failed'),
    read_only=False,
    node_role='master',
):
    tmpdir = tempfile.mkdtemp()

    def load_json(path, default):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def save_json(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f)

    nft_store = {'nfts': [], 'collections': {}}

    def load_nft():
        return copy.deepcopy(nft_store)

    def save_nft(reg):
        nft_store.clear()
        nft_store.update(reg)

    pa_svc.init_physical_assets(
        data_dir=tmpdir,
        load_json_fn=load_json,
        save_json_fn=save_json,
        node_role=node_role,
        read_only=read_only,
        feature_enabled=True,
        load_nft_registry_fn=load_nft,
        save_nft_registry_fn=save_nft,
        nft_mint_fee=1.0,
    )

    def verify_intent(intent, signature, public_key):
        if verify_ok:
            return True, None, None
        return False, verify_error[0], verify_error[1]

    def verify_payload_hash(payload_hash, payload):
        return payload_hash_ok

    init_physical_assets_blueprint(
        verify_intent_fn=verify_intent,
        verify_payload_hash_fn=verify_payload_hash,
        pa_service_module=pa_svc,
        node_role=node_role,
        read_only=read_only,
    )

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(physical_assets_bp)

    return app, tmpdir, nft_store


def _signed_request(action='physical_asset_produce', payload=None, from_thr=CREATOR):
    payload = payload or {}
    return {
        'intent': {
            'type': 'thronos_wallet_action',
            'version': '1',
            'action': action,
            'from_thr': from_thr,
            'nonce': f'nonce-{int(time.time() * 1000)}',
            'created_at': str(int(time.time())),
            'payload_hash': 'mock_hash',
        },
        'signature': 'mock_signature_hex',
        'public_key': '02' + 'ab' * 32,
        'payload': payload,
    }


# ── Write guard ──────────────────────────────────────────────────────────────

class TestBlueprintWriteGuard(unittest.TestCase):
    def test_read_only_rejects_post(self):
        app, _, _ = _init_test_env(read_only=True)
        with app.test_client() as c:
            resp = c.post('/api/assets/creators/approve',
                          json=_signed_request(payload={
                              'tenant_id': 'a', 'creator_address': CREATOR}))
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(resp.get_json()['error'], 'read_only_replica')

    def test_replica_node_rejects_post(self):
        app, _, _ = _init_test_env(node_role='replica')
        with app.test_client() as c:
            resp = c.post('/api/assets/batches',
                          json=_signed_request(payload={'batch_id': 'B1'}))
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(resp.get_json()['error'], 'read_only_replica')

    def test_read_only_allows_get(self):
        app, _, _ = _init_test_env(read_only=True)
        with app.test_client() as c:
            resp = c.get('/api/assets/')
            self.assertEqual(resp.status_code, 200)


# ── Signature validation ─────────────────────────────────────────────────────

class TestBlueprintSignatureValidation(unittest.TestCase):
    def test_missing_intent_rejects_401(self):
        app, _, _ = _init_test_env()
        with app.test_client() as c:
            resp = c.post('/api/assets/creators/approve',
                          json={'payload': {'tenant_id': 'a'}})
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.get_json()['error'], 'signed_wallet_action_required')

    def test_missing_signature_rejects_401(self):
        app, _, _ = _init_test_env()
        with app.test_client() as c:
            body = _signed_request(payload={
                'tenant_id': 'a', 'creator_address': CREATOR})
            del body['signature']
            resp = c.post('/api/assets/creators/approve', json=body)
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.get_json()['error'], 'signed_wallet_action_required')

    def test_missing_public_key_rejects_401(self):
        app, _, _ = _init_test_env()
        with app.test_client() as c:
            body = _signed_request(payload={
                'tenant_id': 'a', 'creator_address': CREATOR})
            del body['public_key']
            resp = c.post('/api/assets/creators/approve', json=body)
            self.assertEqual(resp.status_code, 401)

    def test_invalid_signature_rejects_400(self):
        app, _, _ = _init_test_env(verify_ok=False)
        with app.test_client() as c:
            resp = c.post('/api/assets/creators/approve',
                          json=_signed_request(payload={
                              'tenant_id': 'a', 'creator_address': CREATOR}))
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()['error'], 'invalid_signature')

    def test_payload_hash_mismatch_rejects_400(self):
        app, _, _ = _init_test_env(payload_hash_ok=False)
        with app.test_client() as c:
            resp = c.post('/api/assets/creators/approve',
                          json=_signed_request(payload={
                              'tenant_id': 'a', 'creator_address': CREATOR}))
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()['error'], 'payload_hash_mismatch')

    def test_expired_timestamp_rejects(self):
        app, _, _ = _init_test_env(
            verify_ok=False,
            verify_error=('timestamp_expired', 'intent timestamp too old'))
        with app.test_client() as c:
            resp = c.post('/api/assets/creators/approve',
                          json=_signed_request(payload={
                              'tenant_id': 'a', 'creator_address': CREATOR}))
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()['error'], 'timestamp_expired')

    def test_reused_nonce_rejects(self):
        app, _, _ = _init_test_env(
            verify_ok=False,
            verify_error=('nonce_reused', 'intent nonce already consumed'))
        with app.test_client() as c:
            resp = c.post('/api/assets/creators/approve',
                          json=_signed_request(payload={
                              'tenant_id': 'a', 'creator_address': CREATOR}))
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()['error'], 'nonce_reused')

    def test_raw_private_key_in_request_rejects(self):
        app, _, _ = _init_test_env()
        with app.test_client() as c:
            body = _signed_request(payload={
                'tenant_id': 'a', 'creator_address': CREATOR})
            body['private_key'] = 'deadbeef' * 8
            resp = c.post('/api/assets/creators/approve', json=body)
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()['error'], 'raw_secret_in_request')

    def test_raw_secret_key_in_request_rejects(self):
        app, _, _ = _init_test_env()
        with app.test_client() as c:
            body = _signed_request(payload={
                'tenant_id': 'a', 'creator_address': CREATOR})
            body['secret_key'] = 'deadbeef' * 8
            resp = c.post('/api/assets/batches', json=body)
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()['error'], 'raw_secret_in_request')


# ── Production endpoint happy paths ──────────────────────────────────────────

class TestBlueprintProductionEndpoints(unittest.TestCase):
    def setUp(self):
        self.app, self.tmpdir, self.nft_store = _init_test_env()
        self.client = self.app.test_client()
        resp = self.client.post('/api/assets/creators/approve',
            json=_signed_request('physical_asset_register', {
                'tenant_id': 'aisthetic',
                'creator_address': CREATOR,
            }))
        self.assertTrue(resp.get_json()['ok'])

    def test_create_batch_endpoint(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-1',
                'tenant_id': 'aisthetic',
                'product_id': 'coin-v1',
                'sku': 'TPC-S1',
                'quantity': 2,
                'edition_start': 1,
                'edition_size': 100,
                'design_hash': 'a' * 64,
                'creation_fee': 25.0,
            }))
        data = resp.get_json()
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(data['ok'])
        self.assertEqual(len(data['jobs']), 2)

    def test_get_batch_endpoint(self):
        self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-GET',
                'tenant_id': 'aisthetic',
                'product_id': 'coin-v1',
                'sku': 'TPC-S1',
                'quantity': 1,
                'edition_start': 1,
                'edition_size': 100,
                'design_hash': 'a' * 64,
            }))
        resp = self.client.get('/api/assets/batches/BATCH-BP-GET')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(data['batch']['batch_id'], 'BATCH-BP-GET')

    def test_get_nonexistent_batch_404(self):
        resp = self.client.get('/api/assets/batches/NONEXISTENT')
        self.assertEqual(resp.status_code, 404)

    def test_list_jobs_endpoint(self):
        self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-LIST',
                'tenant_id': 'aisthetic',
                'product_id': 'coin-v1',
                'sku': 'TPC-S1',
                'quantity': 3,
                'edition_start': 1,
                'edition_size': 100,
                'design_hash': 'a' * 64,
            }))
        resp = self.client.get('/api/assets/jobs?batch_id=BATCH-BP-LIST')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['count'], 3)

    def test_get_job_endpoint(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-JOB',
                'tenant_id': 'aisthetic',
                'product_id': 'coin-v1',
                'sku': 'TPC-S1',
                'quantity': 1,
                'edition_start': 1,
                'edition_size': 100,
                'design_hash': 'a' * 64,
            }))
        job_id = resp.get_json()['jobs'][0]['job_id']
        resp = self.client.get(f'/api/assets/jobs/{job_id}')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(data['job']['job_id'], job_id)

    def test_get_nonexistent_job_404(self):
        resp = self.client.get('/api/assets/jobs/NONEXISTENT')
        self.assertEqual(resp.status_code, 404)

    def test_job_status_endpoint(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-STAT',
                'tenant_id': 'aisthetic',
                'product_id': 'coin-v1',
                'sku': 'TPC-S1',
                'quantity': 1,
                'edition_start': 1,
                'edition_size': 100,
                'design_hash': 'a' * 64,
            }))
        job_id = resp.get_json()['jobs'][0]['job_id']
        resp = self.client.get(f'/api/assets/jobs/{job_id}/status')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertIn('job', data)
        self.assertIn('asset', data)

    def test_full_job_lifecycle_via_endpoints(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-LIFE',
                'tenant_id': 'aisthetic',
                'product_id': 'coin-v1',
                'sku': 'TPC-S1',
                'quantity': 1,
                'edition_start': 1,
                'edition_size': 100,
                'design_hash': 'a' * 64,
            }))
        data = resp.get_json()
        job_id = data['jobs'][0]['job_id']
        asset_id = data['jobs'][0]['asset_id']

        resp = self.client.post(f'/api/assets/jobs/{job_id}/gcode',
            json=_signed_request('physical_asset_produce', {
                'gcode_hash': 'b' * 64,
            }))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])

        resp = self.client.post(f'/api/assets/jobs/{job_id}/start',
            json=_signed_request('physical_asset_produce', {
                'printer_id': 'BAMBU-X1C-001',
            }))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])

        resp = self.client.post(f'/api/assets/jobs/{job_id}/complete',
            json=_signed_request('physical_asset_produce', {}))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])

        resp = self.client.post(f'/api/assets/jobs/{job_id}/sign',
            json=_signed_request('physical_asset_produce', {
                'signature_data': {
                    'tenant_id': 'aisthetic',
                    'batch_id': 'BATCH-BP-LIFE',
                    'job_id': job_id,
                    'asset_id': asset_id,
                    'serial': 'TPC-S1-001',
                    'edition_number': 1,
                    'creator_address': CREATOR,
                    'design_hash': 'a' * 64,
                    'nonce': 'nonce-1',
                    'signature': 'fakesig',
                },
            }))
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertTrue(data.get('certified'))
        self.assertIn('nft_id', data)

    def test_fail_print_endpoint(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-FAIL',
                'tenant_id': 'aisthetic',
                'product_id': 'coin-v1',
                'sku': 'TPC-S1',
                'quantity': 1,
                'edition_start': 1,
                'edition_size': 100,
                'design_hash': 'a' * 64,
            }))
        job_id = resp.get_json()['jobs'][0]['job_id']

        self.client.post(f'/api/assets/jobs/{job_id}/gcode',
            json=_signed_request('physical_asset_produce', {
                'gcode_hash': 'b' * 64}))
        self.client.post(f'/api/assets/jobs/{job_id}/start',
            json=_signed_request('physical_asset_produce', {
                'printer_id': 'BAMBU-X1C-001'}))

        resp = self.client.post(f'/api/assets/jobs/{job_id}/fail',
            json=_signed_request('physical_asset_produce', {
                'reason': 'nozzle clog'}))
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(data['job']['status'], 'PRINT_FAILED')


# ── Stage 1 read endpoints via blueprint ─────────────────────────────────────

class TestBlueprintReadEndpoints(unittest.TestCase):
    def setUp(self):
        self.app, self.tmpdir, self.nft_store = _init_test_env()
        self.client = self.app.test_client()

    def test_list_assets_empty(self):
        resp = self.client.get('/api/assets/')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(data['count'], 0)

    def test_get_nonexistent_asset_404(self):
        resp = self.client.get('/api/assets/nonexistent')
        self.assertEqual(resp.status_code, 404)

    def test_get_serial_nonexistent_404(self):
        resp = self.client.get('/api/assets/serial/NOEXIST')
        self.assertEqual(resp.status_code, 404)

    def test_proof_nonexistent_404(self):
        resp = self.client.get('/api/assets/nonexistent/proof')
        self.assertEqual(resp.status_code, 404)


if __name__ == '__main__':
    unittest.main()
