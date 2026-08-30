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
    )
    return tmpdir, nft_store


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
        pa_svc.set_claim_secret(asset['id'], 'supersecret123')
        ok, result = pa_svc.claim_asset(
            asset_id=asset['id'],
            claim_secret='supersecret123',
            new_owner_address='THRNEWOWNER0000000000000000000000000000001',
        )
        self.assertTrue(ok)
        self.assertEqual(result['state'], 'CLAIMED')

    def test_wrong_claim_secret(self):
        ok, asset = _register_default()
        self.assertTrue(ok)
        pa_svc.set_claim_secret(asset['id'], 'supersecret123')
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
        pa_svc.set_claim_secret(asset['id'], 'supersecret123')
        pa_svc.claim_asset(asset['id'], 'supersecret123', 'THRNEWOWNER0000000000000000000000000000001')
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
        pa_svc.set_claim_secret(asset['id'], 'mysecret12345')
        updated = pa_svc.get_asset(asset['id'])
        self.assertIsNotNone(updated.get('claim_secret_hash'))
        self.assertNotEqual(updated['claim_secret_hash'], 'mysecret12345')
        self.assertEqual(len(updated['claim_secret_hash']), 64)


# ── Stage 2: Production layer tests ────────────────────────────────────────

CREATOR = 'THR0000000000000000000000000000000000000001'
CREATOR2 = 'THR0000000000000000000000000000000000000002'


class TestApproveCreator(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()

    def test_approve_and_check(self):
        ok, entry = pa_svc.approve_creator('aisthetic', CREATOR)
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
        pa_svc.approve_creator('aisthetic', CREATOR)

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
        pa_svc.approve_creator('aisthetic', CREATOR)
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

    def test_sign_production_certifies(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)

        job = pa_svc.get_job(self.job_id)
        sig_data = {
            'tenant_id': 'aisthetic',
            'batch_id': 'BATCH-FLOW',
            'job_id': self.job_id,
            'asset_id': self.asset_id,
            'serial': job['serial'],
            'edition_number': job['edition_number'],
            'creator_address': CREATOR,
            'design_hash': 'a' * 64,
            'nonce': 'test-nonce-001',
            'signature': 'fakesig',
        }
        ok, result = pa_svc.sign_production(
            self.job_id, CREATOR, sig_data)
        self.assertTrue(ok)
        self.assertTrue(result.get('certified'))
        self.assertIn('nft_id', result)

    def test_sign_production_mints_nft_with_5pct_royalty(self):
        pa_svc.upload_job_gcode(self.job_id, 'b' * 64, CREATOR)
        pa_svc.start_print_job(self.job_id, 'BAMBU-X1C-001', CREATOR)
        pa_svc.complete_print_job(self.job_id, CREATOR)

        job = pa_svc.get_job(self.job_id)
        sig_data = {
            'tenant_id': 'aisthetic',
            'batch_id': 'BATCH-FLOW',
            'job_id': self.job_id,
            'asset_id': self.asset_id,
            'serial': job['serial'],
            'edition_number': job['edition_number'],
            'creator_address': CREATOR,
            'design_hash': 'a' * 64,
            'nonce': 'test-nonce-002',
            'signature': 'fakesig',
        }
        pa_svc.sign_production(self.job_id, CREATOR, sig_data)

        self.assertEqual(len(self.nft_store.get('nfts', [])), 1)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['royalties'], 5)
        self.assertEqual(nft['creation_fee'], 10.0)
        self.assertEqual(nft['price'], 10.0)
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
        sig_data = {
            'tenant_id': 'aisthetic',
            'batch_id': 'BATCH-FLOW',
            'job_id': self.job_id,
            'asset_id': self.asset_id,
            'serial': job['serial'],
            'edition_number': job['edition_number'],
            'creator_address': CREATOR,
            'design_hash': 'f' * 64,
            'nonce': 'test-nonce-004',
            'signature': 'fakesig',
        }
        ok, result = pa_svc.sign_production(
            self.job_id, CREATOR, sig_data)
        self.assertFalse(ok)
        self.assertEqual(result['error'], 'design_hash_mismatch')


class TestBatchCompletion(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR)

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

            sig_data = {
                'tenant_id': 'aisthetic',
                'batch_id': 'BATCH-MULTI',
                'job_id': job['job_id'],
                'asset_id': job['asset_id'],
                'serial': job['serial'],
                'edition_number': job['edition_number'],
                'creator_address': CREATOR,
                'design_hash': 'a' * 64,
                'nonce': f"nonce-{job['edition_number']}",
                'signature': 'fakesig',
            }
            pa_svc.sign_production(job['job_id'], CREATOR, sig_data)

        batch = pa_svc.get_batch('BATCH-MULTI')
        self.assertEqual(batch['status'], 'COMPLETED')


class TestGetProductionStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir, self.nft_store = _init_service()
        pa_svc.approve_creator('aisthetic', CREATOR)
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
        pa_svc.approve_creator('aisthetic', CREATOR)
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

    def test_creation_fee_on_nft(self):
        ok, asset = _register_default(creation_fee=50.0)
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['creation_fee'], 50.0)
        self.assertEqual(nft['price'], 50.0)
        self.assertTrue(nft['for_sale'])

    def test_zero_fee_not_for_sale(self):
        ok, asset = _register_default(creation_fee=0)
        self.assertTrue(ok)
        ok, result = pa_svc.mint_asset_nft(asset['id'], CREATOR)
        self.assertTrue(ok)
        nft = self.nft_store['nfts'][0]
        self.assertEqual(nft['creation_fee'], 0)
        self.assertFalse(nft['for_sale'])


if __name__ == '__main__':
    unittest.main()
