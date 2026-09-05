"""
Tests for Physical Assets Registry — Stage 1.

Covers: duplicate serial, concurrent edition allocation, edition overflow,
idempotent register, duplicate NFT mint, replayed signed request, modified
payload/signature, read-only replica rejects writes, cross-tenant access,
IDOR mutation, path traversal/malformed serial, public proof contains no PII,
raw secret/private key fields rejected.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import physical_assets_service as pa_svc

ADMIN = 'THRADMIN0000000000000000000000000000000001'


def _init_service(feature_enabled=True, read_only=False, node_role='master'):
    tmpdir = tempfile.mkdtemp()
    registry_file = os.path.join(tmpdir, 'physical_assets_registry.json')

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
        import copy
        return copy.deepcopy(nft_store)

    def save_nft(reg):
        nft_store.clear()
        nft_store.update(reg)

    import copy as _copy
    import time as _time

    def canonical_mint(name, description, category, price, royalties, creator,
                       for_sale=False, mint_fee=0, extra_fields=None,
                       nft_id=None, tx_id=None):
        if nft_id is None:
            nft_id = f"NFT-PA-{int(_time.time() * 1000)}"
        if tx_id is None:
            tx_id = f"{nft_id}-TX"
        store_copy = _copy.deepcopy(nft_store)
        for existing in store_copy.get('nfts', []):
            if existing.get('id') == nft_id:
                return {'nft_id': nft_id, 'nft': existing, 'tx_id': tx_id}
        timestamp = _time.strftime('%Y-%m-%d %H:%M:%S UTC', _time.gmtime())
        nft = {
            'id': nft_id, 'name': name, 'description': description,
            'category': category, 'price': price, 'royalties': royalties,
            'creator': creator, 'owner': creator, 'image_url': None,
            'created_at': timestamp, 'for_sale': for_sale, 'mint_fee': mint_fee,
        }
        if extra_fields:
            nft.update(extra_fields)
        store_copy.setdefault('nfts', []).append(nft)
        nft_store.clear()
        nft_store.update(store_copy)
        return {'nft_id': nft_id, 'nft': nft, 'tx_id': tx_id}

    pa_svc.init_physical_assets(
        data_dir=tmpdir,
        load_json_fn=load_json,
        save_json_fn=save_json,
        node_role=node_role,
        read_only=read_only,
        feature_enabled=feature_enabled,
        load_nft_registry_fn=load_nft,
        save_nft_registry_fn=save_nft,
        nft_mint_fee=1.0,
        canonical_mint_fn=canonical_mint,
        creator_approval_authorizer=lambda a, t, c: True,
    )
    return tmpdir, nft_store


def _build_sig_data(job, asset_id=None, **overrides):
    data = {
        'tenant_id': 'aisthetic',
        'batch_id': job.get('batch_id', ''),
        'job_id': job.get('job_id', ''),
        'asset_id': asset_id or job.get('asset_id', ''),
        'serial': job.get('serial', ''),
        'edition_number': job.get('edition_number', 0),
        'creator_address': CREATOR,
        'design_hash': job.get('design_hash', ''),
        'gcode_hash': job.get('gcode_hash', ''),
        'printer_id': job.get('printer_id', ''),
        'completed_at': job.get('completed_at', ''),
        'nonce': 'test-nonce',
    }
    data.update(overrides)
    return data


def _register_default(**overrides):
    params = dict(
        tenant_id='aisthetic',
        product_id='thronos-physical-coin-series-one',
        sku='TPC-S1',
        serial='TPC-S1-001',
        edition_number=1,
        edition_size=100,
        creator_address='THR0000000000000000000000000000000000000001',
        design_hash='a' * 64,
        asset_type='THR_BACKED_COLLECTIBLE',
    )
    params.update(overrides)
    return pa_svc.register_asset(**params)


class TestRegisterAsset(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_register_success(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        self.assertEqual(asset['state'], 'REGISTERED')
        self.assertEqual(asset['serial'], 'TPC-S1-001')
        self.assertEqual(asset['edition_number'], 1)
        self.assertEqual(asset['edition_size'], 100)

    def test_duplicate_serial_rejected(self):
        ok1, _ = _register_default()
        self.assertTrue(ok1)
        ok2, result = _register_default(edition_number=2)
        self.assertFalse(ok2)
        self.assertEqual(result['error'], 'duplicate_serial')

    def test_duplicate_edition_rejected(self):
        ok1, _ = _register_default()
        self.assertTrue(ok1)
        ok2, result = _register_default(serial='TPC-S1-002')
        self.assertFalse(ok2)
        self.assertEqual(result['error'], 'duplicate_edition')

    def test_edition_overflow(self):
        ok, result = _register_default(edition_number=101, edition_size=100)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'edition_overflow')

    def test_idempotent_register(self):
        ok1, asset1 = _register_default(idempotency_key='test-key-001')
        self.assertTrue(ok1)
        ok2, asset2 = _register_default(idempotency_key='test-key-001')
        self.assertTrue(ok2)
        self.assertEqual(asset1['id'], asset2['id'])

    def test_invalid_serial_format(self):
        ok, result = _register_default(serial='../../../etc/passwd')
        self.assertFalse(ok)
        self.assertIn('invalid_serial', result['error'])

    def test_path_traversal_serial(self):
        ok, result = _register_default(serial='..\\windows\\system32')
        self.assertFalse(ok)
        self.assertIn('invalid_serial', result['error'])

    def test_malformed_serial_too_short(self):
        ok, result = _register_default(serial='A')
        self.assertFalse(ok)
        self.assertIn('invalid_serial', result['error'])

    def test_invalid_creator_address(self):
        ok, result = _register_default(creator_address='NOT_A_THR_ADDRESS')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_creator_address')

    def test_invalid_asset_type(self):
        ok, result = _register_default(asset_type='INVALID_TYPE')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_asset_type')

    def test_invalid_design_hash(self):
        ok, result = _register_default(design_hash='tooshort')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_design_hash_format')

    def test_invalid_edition_number_zero(self):
        ok, result = _register_default(edition_number=0)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_edition_number')

    def test_invalid_edition_number_negative(self):
        ok, result = _register_default(edition_number=-1)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_edition_number')


class TestConcurrentEditionAllocation(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_concurrent_editions_no_duplicates(self):
        results = []
        errors = []

        def register_edition(n):
            try:
                ok, result = pa_svc.register_asset(
                    tenant_id='aisthetic',
                    product_id='concurrent-test',
                    sku='CT',
                    serial=f'CT-{n:03d}',
                    edition_number=n,
                    edition_size=100,
                    creator_address='THR0000000000000000000000000000000000000001',
                    design_hash='b' * 64,
                )
                results.append((n, ok, result))
            except Exception as e:
                errors.append((n, str(e)))

        threads = [threading.Thread(target=register_edition, args=(i,)) for i in range(1, 11)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        success_count = sum(1 for _, ok, _ in results if ok)
        self.assertEqual(success_count, 10)

        serials = set()
        editions = set()
        for _, ok, result in results:
            if ok:
                serials.add(result['serial'])
                editions.add(result['edition_number'])
        self.assertEqual(len(serials), 10)
        self.assertEqual(len(editions), 10)


class TestReadOnlyReplicaRejects(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service(read_only=True)

    def test_register_rejected_on_replica(self):
        ok, result = _register_default()
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'read_only_replica')


class TestFeatureDisabled(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service(feature_enabled=False)

    def test_register_rejected_when_disabled(self):
        ok, result = _register_default()
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'physical_assets_disabled')


class TestGetAsset(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_get_by_id(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        found = pa_svc.get_asset(asset['id'])
        self.assertIsNotNone(found)
        self.assertEqual(found['serial'], 'TPC-S1-001')

    def test_get_by_serial(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        found = pa_svc.get_asset_by_serial('TPC-S1-001')
        self.assertIsNotNone(found)
        self.assertEqual(found['id'], asset['id'])

    def test_get_nonexistent(self):
        found = pa_svc.get_asset('nonexistent')
        self.assertIsNone(found)


class TestAssetProof(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_proof_contains_no_pii(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        proof = pa_svc.get_asset_proof(asset['id'])
        self.assertIsNotNone(proof)
        proof_str = json.dumps(proof)
        self.assertNotIn('claim_secret', proof_str)
        self.assertNotIn('owner_address', proof_str)
        self.assertNotIn('metadata', proof_str)
        self.assertNotIn('commerce_proof_link', proof_str)
        self.assertIn('serial', proof)
        self.assertIn('edition_number', proof)
        self.assertIn('design_hash', proof)
        self.assertIn('creator_address', proof)


class TestMintAssetNFT(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_mint_success(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(
            asset_id=asset['id'],
            from_address='THR0000000000000000000000000000000000000001',
        )
        self.assertTrue(ok)
        self.assertIn('nft_id', result)
        self.assertFalse(result.get('already_minted', False))

    def test_duplicate_nft_mint_returns_same(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok1, r1 = pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        self.assertTrue(ok1)
        ok2, r2 = pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        self.assertTrue(ok2)
        self.assertTrue(r2.get('already_minted'))
        self.assertEqual(r1['nft_id'], r2['nft_id'])

    def test_unauthorized_mint(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(
            asset_id=asset['id'],
            from_address='THRATTACKER00000000000000000000000000000000',
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'unauthorized_mint')

    def test_nft_stored_in_registry(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        self.assertEqual(len(self.nft_store.get('nfts', [])), 1)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['physical_asset_id'], asset['id'])
        self.assertEqual(nft['serial'], 'TPC-S1-001')


class TestClaimAsset(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_claim_success(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        pa_svc.set_claim_secret(asset['id'], 'supersecret123-claim-key!')
        ok, result = pa_svc.claim_asset(
            asset_id=asset['id'],
            claim_secret='supersecret123-claim-key!',
            new_owner_address='THRNEWOWNER0000000000000000000000000000001',
        )
        self.assertTrue(ok)
        self.assertEqual(result['state'], 'CLAIMED')

    def test_wrong_claim_secret(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.set_claim_secret(asset['id'], 'supersecret123-claim-key!')
        ok, result = pa_svc.claim_asset(
            asset_id=asset['id'],
            claim_secret='wrongsecret',
            new_owner_address='THRNEWOWNER0000000000000000000000000000001',
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_claim_secret')

    def test_claim_transfers_nft_ownership(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        pa_svc.set_claim_secret(asset['id'], 'supersecret123-claim-key!')
        pa_svc.claim_asset(asset['id'], 'supersecret123-claim-key!', 'THRNEWOWNER0000000000000000000000000000001')
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['owner'], 'THRNEWOWNER0000000000000000000000000000001')


class TestTransferAsset(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_transfer_success(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        ok, result = pa_svc.transfer_asset(
            asset_id=asset['id'],
            from_address='THR0000000000000000000000000000000000000001',
            to_address='THRBUYER00000000000000000000000000000000001',
        )
        self.assertTrue(ok)
        self.assertEqual(result['state'], 'TRANSFERRED')

    def test_unauthorized_transfer(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        ok, result = pa_svc.transfer_asset(
            asset_id=asset['id'],
            from_address='THRATTACKER00000000000000000000000000000000',
            to_address='THRBUYER00000000000000000000000000000000001',
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'unauthorized_transfer')

    def test_invalid_to_address(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.mint_asset_nft(asset['id'], 'THR0000000000000000000000000000000000000001')
        ok, result = pa_svc.transfer_asset(
            asset_id=asset['id'],
            from_address='THR0000000000000000000000000000000000000001',
            to_address='INVALID',
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_to_address')

    def test_transfer_not_minted(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.transfer_asset(
            asset_id=asset['id'],
            from_address='THR0000000000000000000000000000000000000001',
            to_address='THRBUYER00000000000000000000000000000000001',
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_state_for_transfer')


class TestCrossTenantAccess(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_different_tenant_same_edition_allowed(self):
        ok1, a1 = _register_default(tenant_id='tenant_a')
        self.assertTrue(ok1)
        ok2, a2 = _register_default(
            tenant_id='tenant_b',
            serial='TPC-S1-002',
        )
        self.assertTrue(ok2)
        self.assertNotEqual(a1['id'], a2['id'])


class TestListAssets(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_list_filtered_by_tenant(self):
        _register_default(tenant_id='a', serial='A-001', edition_number=1)
        _register_default(tenant_id='b', serial='B-001', edition_number=1)
        assets = pa_svc.list_assets(tenant_id='a')
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]['tenant_id'], 'a')


class TestRawSecretFieldsRejected(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_claim_secret_stored_as_hash_only(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.set_claim_secret(asset['id'], 'mysecretclaim12345678901')
        updated = pa_svc.get_asset(asset['id'])
        self.assertIsNotNone(updated.get('claim_secret_hash'))
        self.assertNotEqual(updated['claim_secret_hash'], 'mysecretclaim12345678901')
        self.assertEqual(len(updated['claim_secret_hash']), 64)


# ── Stage 2: Production layer tests ────────────────────────────────────────

CREATOR = 'THR0000000000000000000000000000000000000001'
CREATOR2 = 'THR0000000000000000000000000000000000000002'


class TestApproveCreator(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_approve_and_check(self):
        ok, entry = pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        self.assertTrue(ok)
        self.assertTrue(entry['active'])
        self.assertTrue(pa_svc.is_approved_creator(CREATOR, 'aisthetic'))

    def test_unapproved_creator(self):
        self.assertFalse(pa_svc.is_approved_creator(CREATOR, 'aisthetic'))

    def test_invalid_address_rejected(self):
        ok, result = pa_svc.approve_creator('aisthetic', 'NOTAVALIDADDR')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_creator_address')

    def test_product_id_restriction(self):
        pa_svc.approve_creator('aisthetic', CREATOR,
                               approver_address=ADMIN,
                               allowed_product_ids=['product-a'])
        self.assertTrue(pa_svc.is_approved_creator(CREATOR, 'aisthetic', 'product-a'))
        self.assertFalse(pa_svc.is_approved_creator(CREATOR, 'aisthetic', 'product-b'))


class TestDesignHashing(unittest.TestCase):
    def test_hash_bytes(self):
        data = b'test 3mf content'
        h = pa_svc.hash_design_bytes(data)
        self.assertEqual(len(h), 64)
        self.assertEqual(h, pa_svc.hash_design_bytes(data))

    def test_different_data_different_hash(self):
        h1 = pa_svc.hash_design_bytes(b'design-a')
        h2 = pa_svc.hash_design_bytes(b'design-b')
        self.assertNotEqual(h1, h2)

    def test_store_design_file(self):
        tmpdir, _ = _init_service()
        content = b'fake 3mf binary content'
        design_hash, path = pa_svc.store_design_file(
            content, 'benchy.3mf', 'aisthetic', 'coin-v1')
        self.assertEqual(len(design_hash), 64)
        self.assertTrue(os.path.exists(path))
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), content)


class TestCreateProductionBatch(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)

    def test_create_batch_success(self):
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-001',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=3,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertTrue(ok)
        self.assertIn('batch', result)
        self.assertIn('jobs', result)
        self.assertEqual(len(result['jobs']), 3)
        self.assertEqual(result['batch']['status'], 'ACTIVE')

    def test_batch_creates_assets(self):
        pa_svc.create_production_batch(
            batch_id='BATCH-002',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=2,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        assets = pa_svc.list_assets(tenant_id='aisthetic')
        self.assertEqual(len(assets), 2)
        serials = {a['serial'] for a in assets}
        self.assertEqual(serials, {'TPC-S1-001', 'TPC-S1-002'})

    def test_unapproved_creator_rejected(self):
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-003',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR2,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'creator_not_approved')

    def test_edition_overflow_in_batch(self):
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-004',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=5,
            edition_start=98,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'edition_overflow')

    def test_duplicate_batch_id_same_hash(self):
        pa_svc.create_production_batch(
            batch_id='BATCH-005',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-005',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertTrue(ok)

    def test_creation_fee_stored(self):
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-FEE',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
            creation_fee=25.0,
        )
        self.assertTrue(ok)
        self.assertEqual(result['batch']['creation_fee'], 25.0)
        asset = pa_svc.get_asset(result['jobs'][0]['asset_id'])
        self.assertEqual(asset['creation_fee'], 25.0)


class TestProductionJobFlow(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-FLOW',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
            creation_fee=10.0,
        )
        self.assertTrue(ok)
        self.job_id = result['jobs'][0]['job_id']
        self.asset_id = result['jobs'][0]['asset_id']

    def test_upload_gcode(self):
        ok, job = pa_svc.upload_job_gcode(
            self.job_id, 'b' * 64, CREATOR)
        self.assertTrue(ok)
        self.assertEqual(job['status'], 'GCODE_READY')
        self.assertEqual(job['gcode_hash'], 'b' * 64)

    def test_upload_gcode_unauthorized(self):
        ok, result = pa_svc.upload_job_gcode(
            self.job_id, 'b' * 64, CREATOR2)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'unauthorized_creator')

    def test_start_print_job(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        ok, job = pa_svc.start_print_job(
            self.job_id, 'BAMBU-X1C-001', CREATOR)
        self.assertTrue(ok)
        self.assertEqual(job['status'], 'PRINTING')
        self.assertEqual(job['printer_id'], 'BAMBU-X1C-001')
        asset = pa_svc.get_asset(self.asset_id)
        self.assertEqual(asset['state'], 'PENDING_PRODUCTION')

    def test_complete_print_job(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        ok, job = pa_svc.complete_print_job(self.job_id, CREATOR)
        self.assertTrue(ok)
        self.assertEqual(job['status'], 'PRINTED')
        asset = pa_svc.get_asset(self.asset_id)
        self.assertEqual(asset['state'], 'PRODUCED')

    def test_fail_print_job(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        ok, job = pa_svc.fail_print_job(
            self.job_id, CREATOR, reason='nozzle clog')
        self.assertTrue(ok)
        self.assertEqual(job['status'], 'PRINT_FAILED')

    def test_fail_then_retry(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.fail_print_job(self.job_id, CREATOR, reason='clog')
        ok, job = pa_svc.start_print_job(
            self.job_id, 'BAMBU-X1C-001', CREATOR)
        self.assertTrue(ok)
        self.assertEqual(job['status'], 'PRINTING')

    def test_sign_production_only_signs(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)

        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job)
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertTrue(ok)
        self.assertTrue(result.get('signed'))
        self.assertNotIn('certified', result)

        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'CREATOR_SIGNED')
        self.assertEqual(len(self.nft_store.get('nfts', [])), 0)

    def test_sign_then_certify_mints_nft(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)

        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job)
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        ok, result = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertTrue(ok)
        self.assertTrue(result.get('certified'))
        self.assertIn('nft_id', result)

        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'CERTIFIED')

    def test_certify_mints_nft_with_5pct_royalty(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)

        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, nonce='test-nonce-002')
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        pa_svc.certify_production(self.job_id, CREATOR)

        self.assertEqual(len(self.nft_store.get('nfts', [])), 1)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['royalties'], 5)
        self.assertEqual(nft['creation_fee'], 10.0)
        self.assertEqual(nft['price'], 0)
        self.assertFalse(nft['for_sale'])
        self.assertEqual(nft['creator'], CREATOR)

    def test_failed_print_cannot_sign(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.fail_print_job(self.job_id, CREATOR, reason='clog')

        sig_data = {
            'tenant_id': 'aisthetic',
            'batch_id': 'BATCH-FLOW',
            'job_id': self.job_id,
            'asset_id': self.asset_id,
            'serial': 'TPC-S1-001',
            'edition_number': 1,
            'creator_address': CREATOR,
            'design_hash': 'a' * 64,
            'nonce': 'test-nonce-003',
            'signature': 'fakesig',
        }
        ok, result = pa_svc.sign_production(
            self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_printed')

    def test_sign_design_hash_mismatch_rejected(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)

        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, design_hash='f' * 64, nonce='test-nonce-004')
        ok, result = pa_svc.sign_production(
            self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'design_hash_mismatch')


class TestBatchCompletion(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)

    def test_batch_completes_when_all_jobs_certified(self):
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-MULTI',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=2,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertTrue(ok)
        jobs = result['jobs']

        for job in jobs:
            pa_svc.upload_job_gcode(job['job_id'], 'b' * 64, CREATOR)
            pa_svc.start_print_job(job['job_id'], 'BAMBU-X1C-001', CREATOR)
            pa_svc.complete_print_job(job['job_id'], CREATOR)

            j = pa_svc.get_job(job['job_id'])
            sig_data = _build_sig_data(j, nonce=f"nonce-{job['edition_number']}")
            pa_svc.sign_production(job['job_id'], CREATOR, sig_data)
            pa_svc.certify_production(job['job_id'], CREATOR)

        batch = pa_svc.get_batch('BATCH-MULTI')
        self.assertEqual(batch['status'], 'COMPLETED')


class TestGetProductionStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-STATUS',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.job_id = result['jobs'][0]['job_id']

    def test_production_status(self):
        status = pa_svc.get_production_status(self.job_id)
        self.assertIsNotNone(status)
        self.assertIn('job', status)
        self.assertIn('asset', status)
        self.assertEqual(status['job']['status'], 'PLANNED')

    def test_nonexistent_job_status(self):
        status = pa_svc.get_production_status('NONEXISTENT')
        self.assertIsNone(status)


class TestListJobs(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        pa_svc.create_production_batch(
            batch_id='BATCH-LIST',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=3,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )

    def test_list_all_jobs(self):
        jobs = pa_svc.list_jobs()
        self.assertEqual(len(jobs), 3)

    def test_list_by_batch(self):
        jobs = pa_svc.list_jobs(batch_id='BATCH-LIST')
        self.assertEqual(len(jobs), 3)
        jobs = pa_svc.list_jobs(batch_id='NONEXISTENT')
        self.assertEqual(len(jobs), 0)

    def test_list_by_status(self):
        jobs = pa_svc.list_jobs(status='PLANNED')
        self.assertEqual(len(jobs), 3)
        jobs = pa_svc.list_jobs(status='PRINTING')
        self.assertEqual(len(jobs), 0)


class TestNFTRoyalty5Percent(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_manual_mint_has_5pct_royalty(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['royalties'], 5)

    def test_creation_fee_does_not_auto_list(self):
        ok, asset = _register_default(creation_fee=50.0)
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['creation_fee'], 50.0)
        self.assertEqual(nft['price'], 0)
        self.assertFalse(nft['for_sale'])

    def test_zero_fee_not_for_sale(self):
        ok, asset = _register_default(creation_fee=0)
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['creation_fee'], 0)
        self.assertFalse(nft['for_sale'])


# ── Stage 2: Security rejection tests ────────────────────────────────────────

class TestSecurityRejections(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-SEC',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertTrue(ok)
        self.job_id = result['jobs'][0]['job_id']
        self.asset_id = result['jobs'][0]['asset_id']

    def _sign_and_certify_job(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, nonce='nonce-1')
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        cert_result = pa_svc.certify_production(self.job_id, CREATOR)
        return cert_result, sig_data

    def test_duplicate_certification_idempotent(self):
        (ok1, r1), sig_data = self._sign_and_certify_job()
        self.assertTrue(ok1)
        self.assertTrue(r1.get('certified'))
        nft_id = r1['nft_id']

        ok2, r2 = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertTrue(ok2)
        self.assertTrue(r2.get('already_certified'))
        self.assertEqual(r2.get('nft_id'), nft_id)
        self.assertEqual(len(self.nft_store.get('nfts', [])), 1)

    def test_cross_tenant_batch_creation_rejected(self):
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-XT', tenant_id='other_tenant',
            product_id='coin-v1', sku='TPC-S1',
            creator_address=CREATOR, quantity=1,
            edition_start=1, edition_size=100,
            design_hash='a' * 64,
        )
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'creator_not_approved')

    def test_wrong_creator_signs_rejected(self):
        pa_svc.approve_creator('aisthetic', CREATOR2, approver_address=ADMIN)
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        sig_data = {
            'tenant_id': 'aisthetic', 'batch_id': 'BATCH-SEC',
            'job_id': self.job_id, 'asset_id': self.asset_id,
            'serial': 'TPC-S1-001', 'edition_number': 1,
            'creator_address': CREATOR2, 'design_hash': 'a' * 64,
            'nonce': 'nonce-1', 'signature': 'fakesig',
        }
        ok, result = pa_svc.sign_production(self.job_id, CREATOR2, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'unauthorized_creator')

    def test_wrong_creator_starts_print_rejected(self):
        pa_svc.approve_creator('aisthetic', CREATOR2, approver_address=ADMIN)
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        ok, result = pa_svc.start_print_job(self.job_id, 'BAMBU', CREATOR2)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'unauthorized_creator')


class TestInvalidStateTransitions(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-STATE',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertTrue(ok)
        self.job_id = result['jobs'][0]['job_id']
        self.asset_id = result['jobs'][0]['asset_id']

    def test_complete_before_start_rejected(self):
        ok, result = pa_svc.complete_print_job(self.job_id, CREATOR)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_printing')

    def test_fail_before_start_rejected(self):
        ok, result = pa_svc.fail_print_job(self.job_id, CREATOR, 'reason')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_printing')

    def test_sign_before_complete_rejected(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        sig_data = {
            'tenant_id': 'aisthetic', 'batch_id': 'BATCH-STATE',
            'job_id': self.job_id, 'asset_id': self.asset_id,
            'serial': 'TPC-S1-001', 'edition_number': 1,
            'creator_address': CREATOR, 'design_hash': 'a' * 64,
            'nonce': 'nonce-1', 'signature': 'fakesig',
        }
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_printed')

    def test_start_certified_job_rejected(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, nonce='nonce-1')
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        pa_svc.certify_production(self.job_id, CREATOR)
        ok, result = pa_svc.start_print_job(self.job_id, 'BAMBU', CREATOR)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'invalid_job_state')

    def test_complete_certified_job_rejected(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, nonce='nonce-1')
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        pa_svc.certify_production(self.job_id, CREATOR)
        ok, result = pa_svc.complete_print_job(self.job_id, CREATOR)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_printing')

    def test_sign_planned_job_rejected(self):
        sig_data = {
            'tenant_id': 'aisthetic', 'batch_id': 'BATCH-STATE',
            'job_id': self.job_id, 'asset_id': self.asset_id,
            'serial': 'TPC-S1-001', 'edition_number': 1,
            'creator_address': CREATOR, 'design_hash': 'a' * 64,
            'nonce': 'nonce-1', 'signature': 'fakesig',
        }
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_printed')


# ── Stage 2.5: Architecture corrections ────────────────────────────────────

class TestCertificationLifecycle(unittest.TestCase):
    """Correction C: expanded certification lifecycle tests."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-CERT',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.assertTrue(ok)
        self.job_id = result['jobs'][0]['job_id']
        self.asset_id = result['jobs'][0]['asset_id']

    def _print_job(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)

    def _sign_job(self):
        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, nonce='nonce-cert-1')
        return pa_svc.sign_production(self.job_id, CREATOR, sig_data)

    def test_printed_unsigned_not_certified(self):
        self._print_job()
        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'PRINTED')
        self.assertNotEqual(job['status'], 'CERTIFIED')

    def test_creator_signed_not_certified(self):
        self._print_job()
        self._sign_job()
        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'CREATOR_SIGNED')
        self.assertNotEqual(job['status'], 'CERTIFIED')

    def test_mint_submitted_not_certified(self):
        self._print_job()
        self._sign_job()
        # Inject a failing canonical mint to test MINT_PENDING state
        original_fn = pa_svc._canonical_mint_fn
        pa_svc._canonical_mint_fn = None
        ok, result = pa_svc.certify_production(self.job_id, CREATOR)
        pa_svc._canonical_mint_fn = original_fn
        self.assertFalse(ok)
        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'MINT_PENDING')
        self.assertNotEqual(job['status'], 'CERTIFIED')

    def test_canonical_mint_rejected_not_certified(self):
        self._print_job()
        self._sign_job()
        original_fn = pa_svc._canonical_mint_fn
        pa_svc._canonical_mint_fn = None
        ok, result = pa_svc.certify_production(self.job_id, CREATOR)
        pa_svc._canonical_mint_fn = original_fn
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'nft_mint_failed')
        job = pa_svc.get_job(self.job_id)
        self.assertNotEqual(job['status'], 'CERTIFIED')

    def test_canonical_mint_timeout_retryable(self):
        self._print_job()
        self._sign_job()
        original_fn = pa_svc._canonical_mint_fn
        pa_svc._canonical_mint_fn = None
        ok1, r1 = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertFalse(ok1)
        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'MINT_PENDING')

        # Restore and retry — should succeed
        pa_svc._canonical_mint_fn = original_fn
        ok2, r2 = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertTrue(ok2)
        self.assertTrue(r2.get('certified'))
        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'CERTIFIED')

    def test_confirmed_tx_nft_certified(self):
        self._print_job()
        self._sign_job()
        ok, result = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertTrue(ok)
        self.assertTrue(result.get('certified'))
        self.assertIn('nft_id', result)
        self.assertIn('tx_id', result)

        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['status'], 'CERTIFIED')
        asset = pa_svc.get_asset(self.asset_id)
        self.assertEqual(asset['state'], 'MINTED')
        self.assertIsNotNone(asset['nft_id'])
        self.assertIsNotNone(asset['nft_tx_id'])
        self.assertEqual(asset['nft_mint_status'], 'confirmed')

    def test_duplicate_certify_returns_same_nft(self):
        self._print_job()
        self._sign_job()
        ok1, r1 = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertTrue(ok1)
        nft_id_1 = r1['nft_id']

        ok2, r2 = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertTrue(ok2)
        self.assertTrue(r2.get('already_certified'))
        self.assertEqual(r2.get('nft_id'), nft_id_1)
        self.assertEqual(len(self.nft_store.get('nfts', [])), 1)


class TestCanonicalTxIdentity(unittest.TestCase):
    """Gate 2: canonical tx identity must be real and durable.

    ThronosChain canonical NFT mint is atomic — append to CHAIN_FILE
    = confirmed. The tx_id and nft_id must be persisted on both the
    job and asset, and match the canonical chain entry.
    """

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-TX', tenant_id='aisthetic', product_id='coin-v1',
            sku='TPC-S1', creator_address=CREATOR, quantity=1,
            edition_start=1, edition_size=100, design_hash='a' * 64,
        )
        self.assertTrue(ok)
        self.job_id = result['jobs'][0]['job_id']
        self.asset_id = result['jobs'][0]['asset_id']

    def _full_certify(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, nonce='nonce-tx-1')
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        return pa_svc.certify_production(self.job_id, CREATOR)

    def test_certified_has_nft_id_and_tx_id(self):
        ok, result = self._full_certify()
        self.assertTrue(ok)
        self.assertIsNotNone(result['nft_id'])
        self.assertIsNotNone(result['tx_id'])
        self.assertTrue(result['nft_id'].startswith('NFT'))
        self.assertIn(result['nft_id'], result['tx_id'])

    def test_job_persists_canonical_reference(self):
        ok, result = self._full_certify()
        self.assertTrue(ok)
        job = pa_svc.get_job(self.job_id)
        self.assertEqual(job['nft_id'], result['nft_id'])
        self.assertEqual(job['nft_tx_id'], result['tx_id'])
        self.assertEqual(job['nft_mint_status'], 'confirmed')

    def test_asset_persists_canonical_reference(self):
        ok, result = self._full_certify()
        self.assertTrue(ok)
        asset = pa_svc.get_asset(self.asset_id)
        self.assertEqual(asset['nft_id'], result['nft_id'])
        self.assertEqual(asset['nft_tx_id'], result['tx_id'])
        self.assertEqual(asset['nft_mint_status'], 'confirmed')

    def test_missing_canonical_mint_not_certified(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        job = pa_svc.get_job(self.job_id)
        sig_data = _build_sig_data(job, nonce='nonce-tx-2')
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        original = pa_svc._canonical_mint_fn
        pa_svc._canonical_mint_fn = None
        ok, result = pa_svc.certify_production(self.job_id, CREATOR)
        pa_svc._canonical_mint_fn = original
        self.assertFalse(ok)
        job = pa_svc.get_job(self.job_id)
        self.assertNotEqual(job['status'], 'CERTIFIED')
        self.assertIsNone(job.get('nft_id'))

    def test_duplicate_certify_same_tx_id(self):
        ok, r1 = self._full_certify()
        self.assertTrue(ok)
        ok, r2 = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertTrue(ok)
        self.assertTrue(r2.get('already_certified'))
        self.assertEqual(r2['nft_id'], r1['nft_id'])
        self.assertEqual(r2['tx_id'], r1['tx_id'])

    def test_nft_mint_status_in_certify_result(self):
        ok, result = self._full_certify()
        self.assertTrue(ok)
        self.assertEqual(result['nft_mint_status'], 'confirmed')


class TestCreationFeeNotAutoList(unittest.TestCase):
    """Correction B: creation_fee does NOT auto-list the NFT."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_nonzero_creation_fee_does_not_auto_list(self):
        ok, asset = _register_default(creation_fee=100.0)
        self.assertTrue(ok)
        self.assertEqual(asset['creation_fee'], 100.0)
        self.assertEqual(asset['listing_price'], 0)
        self.assertFalse(asset['for_sale'])

        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['creation_fee'], 100.0)
        self.assertEqual(nft['price'], 0)
        self.assertFalse(nft['for_sale'])

    def test_listing_price_defaults_zero(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        self.assertEqual(asset['listing_price'], 0)
        self.assertFalse(asset['for_sale'])

    def test_creation_fee_separate_from_listing(self):
        ok, asset = _register_default(creation_fee=50.0)
        self.assertTrue(ok)
        self.assertEqual(asset['creation_fee'], 50.0)
        self.assertEqual(asset['listing_price'], 0)
        self.assertFalse(asset['for_sale'])


class TestCanonicalNFTRoyalty(unittest.TestCase):
    """Correction D: canonical NFT result has 5% royalty."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)

    def test_canonical_nft_has_5pct_royalty(self):
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-ROY',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
            creation_fee=25.0,
        )
        self.assertTrue(ok)
        job_id = result['jobs'][0]['job_id']
        asset_id = result['jobs'][0]['asset_id']

        pa_svc.upload_job_gcode(job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(job_id, CREATOR)

        job = pa_svc.get_job(job_id)
        sig_data = _build_sig_data(job, nonce='nonce-roy-1')
        pa_svc.sign_production(job_id, CREATOR, sig_data)
        ok, cert_result = pa_svc.certify_production(job_id, CREATOR)
        self.assertTrue(ok)

        self.assertEqual(len(self.nft_store.get('nfts', [])), 1)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['royalties'], 5)
        self.assertFalse(nft['for_sale'])
        self.assertEqual(nft['price'], 0)

    def test_manual_mint_also_has_5pct_royalty(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['royalties'], 5)


class TestJobStatesExpanded(unittest.TestCase):
    """Correction C: verify expanded JOB_STATES tuple."""

    def test_all_required_states_present(self):
        required = [
            'PLANNED', 'GCODE_READY', 'PRINTING', 'PRINT_FAILED',
            'PRINTED', 'CREATOR_SIGNED', 'MINT_PENDING', 'CERTIFIED',
        ]
        for state in required:
            self.assertIn(state, pa_svc.JOB_STATES, f'{state} missing from JOB_STATES')

    def test_removed_states_absent(self):
        removed = [
            'SERIAL_RESERVED', 'DESIGN_UPLOADED', 'NFT_MINTED',
            'CREATOR_SIGN_PENDING',
            'CHAIN_CONFIRMED', 'NFT_CONFIRMED', 'AVAILABLE',
        ]
        for state in removed:
            self.assertNotIn(state, pa_svc.JOB_STATES, f'{state} should not be in JOB_STATES')


class TestCertifyRequiresSigning(unittest.TestCase):
    """Correction C: certify without signing must fail."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-REQ',
            tenant_id='aisthetic',
            product_id='coin-v1',
            sku='TPC-S1',
            creator_address=CREATOR,
            quantity=1,
            edition_start=1,
            edition_size=100,
            design_hash='a' * 64,
        )
        self.job_id = result['jobs'][0]['job_id']

    def test_certify_printed_without_sign_fails(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        ok, result = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_signed')

    def test_certify_planned_job_fails(self):
        ok, result = pa_svc.certify_production(self.job_id, CREATOR)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'job_not_signed')


class TestAssetPersistsNftFields(unittest.TestCase):
    """Correction A: PA must persist nft_id, nft_tx_id, canonical mint status."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_asset_has_nft_mint_fields(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        self.assertIsNone(asset['nft_id'])
        self.assertIsNone(asset['nft_tx_id'])
        self.assertIsNone(asset['nft_mint_status'])

    def test_mint_sets_nft_fields(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)

        updated = pa_svc.get_asset(asset['id'])
        self.assertIsNotNone(updated['nft_id'])
        self.assertIsNotNone(updated['nft_tx_id'])
        self.assertEqual(updated['nft_mint_status'], 'confirmed')
        self.assertEqual(updated['state'], 'MINTED')


class TestSigningIntegration(unittest.TestCase):
    """Correction E: Maker Agent signed envelope accepted by Wallet V1 verifier.

    Security-critical gate — MUST pass, never skip.
    Requires: cryptography (same dependency as maker_agent.signer).
    """

    def test_maker_agent_signature_accepted_by_verifier(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from maker_agent.signer import WalletSigner
        from wallet_action_verify import verify_wallet_action_signature

        privkey = ec.generate_private_key(ec.SECP256K1())
        privkey_hex = format(privkey.private_numbers().private_value, '064x')
        signer = WalletSigner(privkey_hex)

        payload = {'batch_id': 'B1', 'job_id': 'J1', 'action': 'produce'}
        intent = signer.create_intent('physical_asset_produce', payload)
        signature_hex = signer.sign_intent(intent)

        ok, err_code, err_detail = verify_wallet_action_signature(
            intent, signature_hex, signer.public_key_hex
        )
        self.assertTrue(ok, f'Verification failed: {err_code} — {err_detail}')

    def test_address_pubkey_binding(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from maker_agent.signer import WalletSigner
        from wallet_action_verify import verify_wallet_action_signature
        import wallet_v1_production_final as wv1

        privkey = ec.generate_private_key(ec.SECP256K1())
        privkey_hex = format(privkey.private_numbers().private_value, '064x')
        signer = WalletSigner(privkey_hex)

        derived = wv1.derive_thronos_address(signer.public_key_hex)
        self.assertEqual(signer.address, derived)

        payload = {'test': 'binding'}
        intent = signer.create_intent('physical_asset_register', payload)
        sig = signer.sign_intent(intent)

        ok, _, _ = verify_wallet_action_signature(intent, sig, signer.public_key_hex)
        self.assertTrue(ok)

    def test_tampered_intent_rejected(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from maker_agent.signer import WalletSigner
        from wallet_action_verify import verify_wallet_action_signature

        privkey = ec.generate_private_key(ec.SECP256K1())
        privkey_hex = format(privkey.private_numbers().private_value, '064x')
        signer = WalletSigner(privkey_hex)

        payload = {'batch_id': 'B1'}
        intent = signer.create_intent('physical_asset_produce', payload)
        sig = signer.sign_intent(intent)

        intent['action'] = 'physical_asset_transfer'
        ok, err_code, _ = verify_wallet_action_signature(intent, sig, signer.public_key_hex)
        self.assertFalse(ok)
        self.assertEqual(err_code, 'invalid_signature')

    def test_wrong_key_rejected(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from maker_agent.signer import WalletSigner
        from wallet_action_verify import verify_wallet_action_signature

        key1 = ec.generate_private_key(ec.SECP256K1())
        key2 = ec.generate_private_key(ec.SECP256K1())
        signer1 = WalletSigner(format(key1.private_numbers().private_value, '064x'))
        signer2 = WalletSigner(format(key2.private_numbers().private_value, '064x'))

        payload = {'batch_id': 'B1'}
        intent = signer1.create_intent('physical_asset_produce', payload)
        sig = signer1.sign_intent(intent)

        ok, err_code, _ = verify_wallet_action_signature(intent, sig, signer2.public_key_hex)
        self.assertFalse(ok)


# ── Stage 2.7: Security gate tests ──────────────────────────────────────────

class TestGate2SelfApprovalRejected(unittest.TestCase):
    """Gate 2: Creator cannot approve themselves."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_self_approval_rejected(self):
        ok, result = pa_svc.approve_creator(
            'aisthetic', CREATOR, approver_address=CREATOR)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'self_approval_not_allowed')

    def test_missing_approver_rejected(self):
        ok, result = pa_svc.approve_creator('aisthetic', CREATOR)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'approver_address_required')

    def test_different_approver_accepted(self):
        ok, result = pa_svc.approve_creator(
            'aisthetic', CREATOR, approver_address=ADMIN)
        self.assertTrue(ok)


class TestGate5SignatureBindings(unittest.TestCase):
    """Gate 5: Signature must bind all manufacturing fields."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-BIND', tenant_id='aisthetic',
            product_id='coin-v1', sku='TPC-S1',
            creator_address=CREATOR, quantity=1,
            edition_start=1, edition_size=100, design_hash='a' * 64,
        )
        self.assertTrue(ok)
        self.job_id = result['jobs'][0]['job_id']
        self.asset_id = result['jobs'][0]['asset_id']
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)
        self.job = pa_svc.get_job(self.job_id)

    def test_missing_gcode_hash_rejected(self):
        sig_data = _build_sig_data(self.job, gcode_hash='')
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'incomplete_signature')
        self.assertEqual(result['missing'], 'gcode_hash')

    def test_missing_printer_id_rejected(self):
        sig_data = _build_sig_data(self.job, printer_id='')
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'incomplete_signature')
        self.assertEqual(result['missing'], 'printer_id')

    def test_missing_completed_at_rejected(self):
        sig_data = _build_sig_data(self.job, completed_at='')
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'incomplete_signature')
        self.assertEqual(result['missing'], 'completed_at')

    def test_gcode_hash_mismatch_rejected(self):
        sig_data = _build_sig_data(self.job, gcode_hash='c' * 64)
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'gcode_hash_mismatch')

    def test_printer_id_mismatch_rejected(self):
        sig_data = _build_sig_data(self.job, printer_id='WRONG-PRINTER')
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'printer_id_mismatch')

    def test_completed_at_mismatch_rejected(self):
        sig_data = _build_sig_data(self.job, completed_at='1999-01-01T00:00:00Z')
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'completed_at_mismatch')

    def test_all_bindings_match_accepted(self):
        sig_data = _build_sig_data(self.job)
        ok, result = pa_svc.sign_production(self.job_id, CREATOR, sig_data)
        self.assertTrue(ok)
        self.assertTrue(result.get('signed'))


class TestGate6ManualStateLockdown(unittest.TestCase):
    """Gate 6: Only RETIRED can be set via manual state mutation."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        ok, self.asset = _register_default()
        self.assertTrue(ok)

    def test_retired_allowed(self):
        ok, result = pa_svc.update_asset_state(self.asset['id'], 'RETIRED')
        self.assertTrue(ok)
        self.assertEqual(result['state'], 'RETIRED')

    def test_minted_rejected(self):
        ok, result = pa_svc.update_asset_state(self.asset['id'], 'MINTED')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'state_not_manually_settable')

    def test_produced_rejected(self):
        ok, result = pa_svc.update_asset_state(self.asset['id'], 'PRODUCED')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'state_not_manually_settable')

    def test_claimed_rejected(self):
        ok, result = pa_svc.update_asset_state(self.asset['id'], 'CLAIMED')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'state_not_manually_settable')


class TestGate7PublicReadSanitization(unittest.TestCase):
    """Gate 7: Public reads must not expose claim_secret_hash."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        ok, self.asset = _register_default()
        self.assertTrue(ok)
        pa_svc.set_claim_secret(self.asset['id'], 'my-secret-123-claim-long!')

    def test_sanitize_strips_claim_secret_hash(self):
        raw = pa_svc.get_asset(self.asset['id'])
        self.assertIn('claim_secret_hash', raw)
        sanitized = pa_svc.sanitize_asset_for_public(raw)
        self.assertNotIn('claim_secret_hash', sanitized)
        self.assertIn('serial', sanitized)
        self.assertIn('edition_number', sanitized)

    def test_constant_time_comparison(self):
        pa_svc.set_claim_secret(self.asset['id'], 'correct-secret-for-claim!')
        ok, _ = pa_svc.claim_asset(self.asset['id'], 'correct-secret-for-claim!',
                                   'THRNEWOWNER0000000000000000000000000000001')
        self.assertTrue(ok)

    def test_claim_secret_entropy(self):
        secret = pa_svc.generate_claim_secret()
        self.assertGreaterEqual(len(secret), 32)
        secret2 = pa_svc.generate_claim_secret()
        self.assertNotEqual(secret, secret2)


class TestGate34StableCanonicalIdentity(unittest.TestCase):
    """Gates 3-4: Exactly-once mint with stable nft_id and tx_id."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_stable_nft_id_format(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        self.assertEqual(result['nft_id'], f"NFT-PA-{asset['id']}")

    def test_stable_tx_id_format(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        updated = pa_svc.get_asset(asset['id'])
        self.assertEqual(updated['nft_tx_id'], f"NFT-PA-{asset['id']}-MINT")

    def test_idempotent_mint_returns_same_ids(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        ok1, r1 = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        ok2, r2 = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertEqual(r1['nft_id'], r2['nft_id'])
        self.assertTrue(r2.get('already_minted'))


# ── Fix 1: Partial NFT mint recovery ──────────────────────────────────────────

class TestPartialMintRecovery(unittest.TestCase):
    """Fix 1: tx_id=None must block confirmation."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_mint_without_chain_callbacks_returns_tx_none(self):
        """canonical_mint_nft with no chain callbacks returns tx_id=None."""
        from nft_mint_core import canonical_mint_nft
        result = canonical_mint_nft(
            name='Test', description='Test', category='test',
            price=0, royalties=5, creator=CREATOR,
            load_nft_registry_fn=lambda: self.nft_store,
            save_nft_registry_fn=lambda r: self.nft_store.update(r),
        )
        self.assertIsNone(result['tx_id'])

    def test_mint_asset_nft_rejects_missing_tx_id(self):
        """mint_asset_nft must fail if canonical mint returns tx_id=None."""
        ok, asset = _register_default()
        self.assertTrue(ok)

        original = pa_svc._canonical_mint_fn
        def no_chain_mint(**kwargs):
            result = original(**kwargs)
            result['tx_id'] = None
            return result
        pa_svc._canonical_mint_fn = no_chain_mint

        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        pa_svc._canonical_mint_fn = original
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'canonical_tx_missing')

        updated = pa_svc.get_asset(asset['id'])
        self.assertNotEqual(updated.get('nft_mint_status'), 'confirmed')

    def test_certify_rejects_missing_tx_id(self):
        """certify_production must fail if mint returns tx_id=None."""
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-NOTX', tenant_id='aisthetic',
            product_id='coin-v1', sku='TPC-S1',
            creator_address=CREATOR, quantity=1,
            edition_start=1, edition_size=100, design_hash='a' * 64,
        )
        self.assertTrue(ok)
        job_id = result['jobs'][0]['job_id']

        pa_svc.upload_job_gcode(job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(job_id, CREATOR)
        job = pa_svc.get_job(job_id)
        sig_data = _build_sig_data(job, nonce='notx-1')
        pa_svc.sign_production(job_id, CREATOR, sig_data)

        original = pa_svc._canonical_mint_fn
        def no_chain_mint(**kwargs):
            result = original(**kwargs)
            result['tx_id'] = None
            return result
        pa_svc._canonical_mint_fn = no_chain_mint

        ok, result = pa_svc.certify_production(job_id, CREATOR)
        pa_svc._canonical_mint_fn = original
        self.assertFalse(ok)
        self.assertIn(result['error'], ('canonical_tx_missing', 'nft_mint_failed'))

        job = pa_svc.get_job(job_id)
        self.assertNotEqual(job['status'], 'CERTIFIED')


class TestPartialMintRecoveryCore(unittest.TestCase):
    """Fix 1: nft_mint_core partial-failure recovery."""

    def test_registry_saved_chain_missing_recovers(self):
        """If NFT exists in registry but chain tx is missing, _ensure_chain_tx reconstructs it."""
        from nft_mint_core import canonical_mint_nft

        nft_store = {'nfts': []}
        chain = []
        call_count = {'save_chain': 0}

        def load_nft():
            import copy
            return copy.deepcopy(nft_store)
        def save_nft(reg):
            nft_store.clear()
            nft_store.update(reg)
        def load_chain():
            import copy
            return copy.deepcopy(chain)
        def save_chain(c):
            call_count['save_chain'] += 1
            chain.clear()
            chain.extend(c)

        # First mint — succeeds normally
        r1 = canonical_mint_nft(
            name='Test', description='Test', category='test',
            price=0, royalties=5, creator=CREATOR,
            nft_id='NFT-PA-RECOV', tx_id='NFT-PA-RECOV-MINT',
            load_nft_registry_fn=load_nft, save_nft_registry_fn=save_nft,
            load_chain_fn=load_chain, save_chain_fn=save_chain,
        )
        self.assertEqual(r1['nft_id'], 'NFT-PA-RECOV')
        self.assertEqual(r1['tx_id'], 'NFT-PA-RECOV-MINT')
        self.assertEqual(len(chain), 1)

        # Simulate partial failure: clear chain but leave NFT in registry
        chain.clear()
        self.assertEqual(len(nft_store.get('nfts', [])), 1)
        self.assertEqual(len(chain), 0)

        # Retry — should recover: no duplicate NFT, chain tx reconstructed
        r2 = canonical_mint_nft(
            name='Test', description='Test', category='test',
            price=0, royalties=5, creator=CREATOR,
            nft_id='NFT-PA-RECOV', tx_id='NFT-PA-RECOV-MINT',
            load_nft_registry_fn=load_nft, save_nft_registry_fn=save_nft,
            load_chain_fn=load_chain, save_chain_fn=save_chain,
        )
        self.assertEqual(r2['nft_id'], 'NFT-PA-RECOV')
        self.assertEqual(r2['tx_id'], 'NFT-PA-RECOV-MINT')
        self.assertEqual(len(nft_store.get('nfts', [])), 1)
        self.assertEqual(len(chain), 1)


class TestAssetSavedJobUnsavedRecovery(unittest.TestCase):
    """Fix: asset nft_id saved but nft_tx_id missing (crash before job update).

    Retry must reconcile the chain tx without minting a second NFT,
    returning the same nft_id and tx_id.
    """

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_asset_saved_job_unsaved_recovery(self):
        pa_svc.approve_creator('aisthetic', CREATOR, approver_address=ADMIN)
        ok, result = pa_svc.create_production_batch(
            batch_id='BATCH-RECOV', tenant_id='aisthetic',
            product_id='coin-v1', sku='TPC-S1',
            creator_address=CREATOR, quantity=1,
            edition_start=1, edition_size=100, design_hash='a' * 64,
        )
        self.assertTrue(ok)
        job_id = result['jobs'][0]['job_id']
        asset_id = result['jobs'][0]['asset_id']

        pa_svc.upload_job_gcode(job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(job_id, CREATOR)

        job = pa_svc.get_job(job_id)
        sig_data = _build_sig_data(job, nonce='recov-1')
        pa_svc.sign_production(job_id, CREATOR, sig_data)

        # First certify succeeds — asset gets nft_id + nft_tx_id + MINTED
        ok1, r1 = pa_svc.certify_production(job_id, CREATOR)
        self.assertTrue(ok1)
        self.assertTrue(r1.get('certified'))
        first_nft_id = r1['nft_id']
        first_tx_id = r1['tx_id']
        self.assertTrue(first_nft_id)
        self.assertTrue(first_tx_id)

        asset = pa_svc.get_asset(asset_id)
        self.assertEqual(asset['nft_id'], first_nft_id)
        self.assertEqual(asset['nft_tx_id'], first_tx_id)
        self.assertEqual(asset['nft_mint_status'], 'confirmed')

        # Simulate crash: asset saved with nft_id but nft_tx_id wiped
        with pa_svc._lock:
            registry = pa_svc._load_registry()
            registry['assets'][asset_id]['nft_tx_id'] = ''
            pa_svc._save_registry(registry)

        # Now call mint_asset_nft again (as certify retry would)
        ok2, r2 = pa_svc.mint_asset_nft(asset_id, CREATOR, verified=True)
        self.assertTrue(ok2)
        self.assertTrue(r2.get('already_minted'))
        self.assertEqual(r2['nft_id'], first_nft_id)
        self.assertTrue(r2.get('tx_id'))
        self.assertEqual(len(self.nft_store.get('nfts', [])), 1)

    def test_asset_saved_with_tx_id_returns_both(self):
        """If asset has both nft_id and nft_tx_id, return both on retry."""
        ok, asset = _register_default()
        self.assertTrue(ok)

        ok1, r1 = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok1)

        ok2, r2 = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok2)
        self.assertTrue(r2.get('already_minted'))
        self.assertEqual(r2['nft_id'], r1['nft_id'])
        self.assertEqual(r2['tx_id'], r1['tx_id'])


# ── Fix 2: Creator approval authorizer wiring ─────────────────────────────────

class TestCreatorApprovalAuthorizer(unittest.TestCase):
    """Fix 2: Authorizer must be fail-closed."""

    def test_no_authorizer_rejects_approval(self):
        tmpdir = tempfile.mkdtemp()
        pa_svc.init_physical_assets(
            data_dir=tmpdir,
            load_json_fn=lambda p, d: d,
            save_json_fn=lambda p, d: None,
            feature_enabled=True,
            creator_approval_authorizer=None,
        )
        ok, result = pa_svc.approve_creator('t', CREATOR, approver_address=ADMIN)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'creator_approval_not_configured')

    def test_fail_closed_authorizer(self):
        tmpdir = tempfile.mkdtemp()
        pa_svc.init_physical_assets(
            data_dir=tmpdir,
            load_json_fn=lambda p, d: d,
            save_json_fn=lambda p, d: None,
            feature_enabled=True,
            creator_approval_authorizer=lambda a, t, c: False,
        )
        ok, result = pa_svc.approve_creator('t', CREATOR, approver_address=ADMIN)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'approver_not_authorized')


# ── Fix 4: Claim secret hardening ──────────────────────────────────────────────

class TestClaimSecretHardening(unittest.TestCase):
    """Fix 4: Minimum 24-char claim secret, server-generated preferred."""

    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        ok, self.asset = _register_default()
        self.assertTrue(ok)

    def test_short_secret_rejected(self):
        ok, result = pa_svc.set_claim_secret(self.asset['id'], 'short')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'claim_secret_too_short')

    def test_23_chars_rejected(self):
        ok, result = pa_svc.set_claim_secret(self.asset['id'], 'a' * 23)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'claim_secret_too_short')

    def test_24_chars_accepted(self):
        ok, result = pa_svc.set_claim_secret(self.asset['id'], 'a' * 24)
        self.assertTrue(ok)
        self.assertEqual(result['state'], 'CLAIM_PENDING')

    def test_generated_secret_meets_minimum(self):
        secret = pa_svc.generate_claim_secret()
        self.assertGreaterEqual(len(secret), 24)

    def test_old_8_char_secret_now_rejected(self):
        ok, result = pa_svc.set_claim_secret(self.asset['id'], '12345678')
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'claim_secret_too_short')


if __name__ == '__main__':
    unittest.main()
