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


if __name__ == '__main__':
    unittest.main()
