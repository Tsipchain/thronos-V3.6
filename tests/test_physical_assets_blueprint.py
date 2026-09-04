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

    _nft_counter = [0]

    def canonical_mint(name, description, category, price, royalties, creator,
                       image_url=None, for_sale=True, mint_fee=0,
                       extra_fields=None, nft_id=None, **kwargs):
        _nft_counter[0] += 1
        nft_id = nft_id or f'NFT_BP_{_nft_counter[0]}'
        nft = {
            'nft_id': nft_id,
            'name': name,
            'description': description,
            'category': category,
            'price': price,
            'royalties': royalties,
            'creator': creator,
            'for_sale': for_sale,
        }
        if extra_fields:
            nft.update(extra_fields)
        reg = load_nft()
        reg['nfts'].append(nft)
        save_nft(reg)
        return {'nft_id': nft_id, 'nft': nft, 'tx_id': f'TX_BP_{_nft_counter[0]}'}

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
        canonical_mint_fn=canonical_mint,
        creator_approval_authorizer=lambda a, t, c: True,
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
                          json=_signed_request('physical_asset_register', {
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
            }, from_thr=CREATOR2))
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

        job = pa_svc.get_job(job_id)
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
                    'gcode_hash': job.get('gcode_hash', ''),
                    'printer_id': job.get('printer_id', ''),
                    'completed_at': job.get('completed_at', ''),
                    'nonce': 'nonce-1',
                    'signature': 'fakesig',
                },
            }))
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertTrue(data.get('signed'))
        self.assertEqual(data['job']['status'], 'CREATOR_SIGNED')

        resp = self.client.post(f'/api/assets/jobs/{job_id}/certify',
            json=_signed_request('physical_asset_produce', {}))
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

    def test_certify_endpoint_requires_signing_first(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-CERT',
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
        self.client.post(f'/api/assets/jobs/{job_id}/complete',
            json=_signed_request('physical_asset_produce', {}))

        resp = self.client.post(f'/api/assets/jobs/{job_id}/certify',
            json=_signed_request('physical_asset_produce', {}))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json()['ok'])

    def test_certify_endpoint_success(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_produce', {
                'batch_id': 'BATCH-BP-CERT2',
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

        self.client.post(f'/api/assets/jobs/{job_id}/gcode',
            json=_signed_request('physical_asset_produce', {
                'gcode_hash': 'b' * 64}))
        self.client.post(f'/api/assets/jobs/{job_id}/start',
            json=_signed_request('physical_asset_produce', {
                'printer_id': 'BAMBU-X1C-001'}))
        self.client.post(f'/api/assets/jobs/{job_id}/complete',
            json=_signed_request('physical_asset_produce', {}))
        job = pa_svc.get_job(job_id)
        self.client.post(f'/api/assets/jobs/{job_id}/sign',
            json=_signed_request('physical_asset_produce', {
                'signature_data': {
                    'tenant_id': 'aisthetic',
                    'batch_id': 'BATCH-BP-CERT2',
                    'job_id': job_id,
                    'asset_id': asset_id,
                    'serial': 'TPC-S1-001',
                    'edition_number': 1,
                    'creator_address': CREATOR,
                    'design_hash': 'a' * 64,
                    'gcode_hash': job.get('gcode_hash', ''),
                    'printer_id': job.get('printer_id', ''),
                    'completed_at': job.get('completed_at', ''),
                    'nonce': 'nonce-1',
                    'signature': 'fakesig',
                },
            }))

        resp = self.client.post(f'/api/assets/jobs/{job_id}/certify',
            json=_signed_request('physical_asset_produce', {}))
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertTrue(data['certified'])
        self.assertIn('nft_id', data)


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


# ── Stage 2.7: Security gate tests ──────────────────────────────────────────

ADMIN = 'THRADMIN0000000000000000000000000000000001'


class TestGate1ActionEnforcement(unittest.TestCase):
    """Gate 1: Wrong wallet action is rejected with 403."""

    def setUp(self):
        self.app, self.tmpdir, self.nft_store = _init_test_env()
        self.client = self.app.test_client()

    def test_wrong_action_on_approve_rejected(self):
        resp = self.client.post('/api/assets/creators/approve',
            json=_signed_request('physical_asset_produce', {
                'tenant_id': 'aisthetic',
                'creator_address': CREATOR,
            }))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()['error'], 'wallet_action_not_allowed')

    def test_wrong_action_on_batch_rejected(self):
        resp = self.client.post('/api/assets/batches',
            json=_signed_request('physical_asset_register', {
                'batch_id': 'B1',
                'tenant_id': 'aisthetic',
            }))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()['error'], 'wallet_action_not_allowed')

    def test_correct_action_on_approve_accepted(self):
        resp = self.client.post('/api/assets/creators/approve',
            json=_signed_request('physical_asset_register', {
                'tenant_id': 'aisthetic',
                'creator_address': CREATOR,
            }, from_thr=CREATOR2))
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.get_json()['ok'])


class TestGate2SelfApprovalBlueprint(unittest.TestCase):
    """Gate 2: Self-approval rejected through blueprint."""

    def setUp(self):
        self.app, self.tmpdir, self.nft_store = _init_test_env()
        self.client = self.app.test_client()

    def test_self_approval_rejected(self):
        resp = self.client.post('/api/assets/creators/approve',
            json=_signed_request('physical_asset_register', {
                'tenant_id': 'aisthetic',
                'creator_address': CREATOR,
            }, from_thr=CREATOR))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['error'], 'self_approval_not_allowed')


class TestGate7PublicReadSanitizationBlueprint(unittest.TestCase):
    """Gate 7: Public read endpoints strip claim_secret_hash."""

    def setUp(self):
        self.app, self.tmpdir, self.nft_store = _init_test_env()
        self.client = self.app.test_client()
        ok, self.asset = pa_svc.register_asset(
            tenant_id='aisthetic', product_id='coin-v1', sku='TPC-S1',
            serial='TPC-S1-001', edition_number=1, edition_size=100,
            creator_address=CREATOR, design_hash='a' * 64,
            asset_type='THR_BACKED_COLLECTIBLE',
        )
        self.assertTrue(ok)
        pa_svc.set_claim_secret(self.asset['id'], 'my-secret-456-claim-long!')

    def test_get_asset_strips_secret_hash(self):
        resp = self.client.get(f"/api/assets/{self.asset['id']}")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('claim_secret_hash', data['asset'])

    def test_get_by_serial_strips_secret_hash(self):
        resp = self.client.get('/api/assets/serial/TPC-S1-001')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('claim_secret_hash', data['asset'])

    def test_list_assets_strips_secret_hash(self):
        resp = self.client.get('/api/assets/?tenant_id=aisthetic')
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['count'] >= 1)
        for asset in data['assets']:
            self.assertNotIn('claim_secret_hash', asset)


class TestGate8RecursiveSecretRejection(unittest.TestCase):
    """Gate 8: Nested secrets in payload recursively rejected."""

    def setUp(self):
        self.app, self.tmpdir, self.nft_store = _init_test_env()
        self.client = self.app.test_client()

    def test_nested_private_key_rejected(self):
        body = _signed_request('physical_asset_register', {
            'tenant_id': 'a', 'creator_address': CREATOR,
        })
        body['payload']['nested'] = {'private_key': 'deadbeef' * 8}
        resp = self.client.post('/api/assets/creators/approve', json=body)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['error'], 'raw_secret_in_request')

    def test_deeply_nested_mnemonic_rejected(self):
        body = _signed_request('physical_asset_register', {
            'tenant_id': 'a', 'creator_address': CREATOR,
        })
        body['payload']['level1'] = {'level2': {'mnemonic': 'word1 word2 word3'}}
        resp = self.client.post('/api/assets/creators/approve', json=body)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['error'], 'raw_secret_in_request')

    def test_secret_in_list_rejected(self):
        body = _signed_request('physical_asset_register', {
            'tenant_id': 'a', 'creator_address': CREATOR,
        })
        body['payload']['items'] = [{'seed_phrase': 'one two three'}]
        resp = self.client.post('/api/assets/creators/approve', json=body)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['error'], 'raw_secret_in_request')

    def test_empty_secret_value_passes(self):
        body = _signed_request('physical_asset_register', {
            'tenant_id': 'a', 'creator_address': CREATOR,
        }, from_thr=CREATOR2)
        body['payload']['private_key'] = ''
        resp = self.client.post('/api/assets/creators/approve', json=body)
        self.assertNotEqual(resp.get_json().get('error'), 'raw_secret_in_request')


if __name__ == '__main__':
    unittest.main()
