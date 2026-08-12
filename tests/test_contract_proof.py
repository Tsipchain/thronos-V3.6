"""
Tests for CONTRACT_ANCHOR_V1 contract proof module.

15 tests covering:
  - Payload validation (allowlist, PII rejection, required fields)
  - SHA-256 validation
  - Master/replica guard
  - Idempotent anchoring
  - Service wallet isolation
  - API endpoints (anchor + lookup)
  - Transaction ID determinism
"""

import hashlib
import json
import os
import tempfile
import pytest

from contract_proof import (
    TX_TYPE,
    ALLOWED_PAYLOAD_FIELDS,
    ContractProofConfigError,
    validate_anchor_payload,
    anchor_contract_proof,
    get_proof_by_manifest,
    _generate_tx_id,
    _validate_sha256,
    _reject_pii_fields,
    _filter_to_allowlist,
    _load_proof_ledger,
    register_contract_proof_routes,
)


def _valid_payload(**overrides):
    base = {
        "agreement_id": 42,
        "tenant_id": 6,
        "agreement_ref": "AGR-2026-001",
        "agreement_version": "1",
        "document_sha256": hashlib.sha256(b"doc-content").hexdigest(),
        "manifest_sha256": hashlib.sha256(b"manifest-content").hexdigest(),
        "signature_method": "VERIFIED_ESIGN",
        "chain_mode": "managed_anchor",
    }
    base.update(overrides)
    return base


@pytest.fixture
def data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestPayloadAllowlist:
    def test_allowed_fields_pass_through(self):
        payload = _valid_payload()
        result = validate_anchor_payload(payload)
        for key in result:
            assert key in ALLOWED_PAYLOAD_FIELDS

    def test_extra_fields_stripped(self):
        payload = _valid_payload(extra_field="should-be-removed", notes="also-removed")
        result = validate_anchor_payload(payload)
        assert "extra_field" not in result
        assert "notes" not in result

    def test_pii_field_rejected(self):
        payload = _valid_payload(signer_email="user@example.com")
        with pytest.raises(ValueError, match="PII field"):
            validate_anchor_payload(payload)

    def test_pii_name_field_rejected(self):
        payload = _valid_payload(signer_name="John Doe")
        with pytest.raises(ValueError, match="PII field"):
            validate_anchor_payload(payload)

    def test_pii_phone_field_rejected(self):
        payload = _valid_payload(contact_phone="+1234567890")
        with pytest.raises(ValueError, match="PII field"):
            validate_anchor_payload(payload)

    def test_pii_address_field_rejected(self):
        payload = _valid_payload(billing_address="123 Main St")
        with pytest.raises(ValueError, match="PII field"):
            validate_anchor_payload(payload)


class TestSHA256Validation:
    def test_valid_sha256_accepted(self):
        h = hashlib.sha256(b"test").hexdigest()
        assert _validate_sha256(h) == h

    def test_uppercase_sha256_rejected(self):
        h = hashlib.sha256(b"test").hexdigest().upper()
        with pytest.raises(ValueError, match="64 lowercase hex"):
            _validate_sha256(h)

    def test_short_hash_rejected(self):
        with pytest.raises(ValueError, match="64 lowercase hex"):
            _validate_sha256("abcdef1234")


class TestRequiredFields:
    def test_missing_agreement_id_raises(self):
        payload = _valid_payload()
        del payload["agreement_id"]
        with pytest.raises(ValueError, match="Missing required fields"):
            validate_anchor_payload(payload)

    def test_invalid_signature_method_raises(self):
        payload = _valid_payload(signature_method="INVALID")
        with pytest.raises(ValueError, match="Invalid signature_method"):
            validate_anchor_payload(payload)

    def test_invalid_chain_mode_raises(self):
        payload = _valid_payload(chain_mode="self_anchor")
        with pytest.raises(ValueError, match="Invalid chain_mode"):
            validate_anchor_payload(payload)


class TestMasterReplicaGuard:
    def test_replica_node_rejected(self, data_dir):
        payload = _valid_payload()
        with pytest.raises(PermissionError, match="master-only"):
            anchor_contract_proof(
                payload=payload,
                data_dir=data_dir,
                is_master_node=False,
                service_wallet="THR_CONTRACT_SERVICE",
            )

    def test_master_node_accepted(self, data_dir):
        payload = _valid_payload()
        result = anchor_contract_proof(
            payload=payload,
            data_dir=data_dir,
            is_master_node=True,
            service_wallet="THR_CONTRACT_SERVICE",
        )
        assert result["type"] == TX_TYPE
        assert result["status"] == "anchored"


class TestIdempotentAnchoring:
    def test_duplicate_manifest_returns_existing(self, data_dir):
        payload = _valid_payload()
        first = anchor_contract_proof(
            payload=payload,
            data_dir=data_dir,
            is_master_node=True,
            service_wallet="THR_CONTRACT_SERVICE",
        )
        second = anchor_contract_proof(
            payload=payload,
            data_dir=data_dir,
            is_master_node=True,
            service_wallet="THR_CONTRACT_SERVICE",
        )
        assert first["tx_id"] == second["tx_id"]
        assert first["timestamp"] == second["timestamp"]
        ledger = _load_proof_ledger(data_dir)
        assert len(ledger) == 1


class TestServiceWalletIsolation:
    def test_proof_record_carries_service_wallet(self, data_dir):
        payload = _valid_payload()
        result = anchor_contract_proof(
            payload=payload,
            data_dir=data_dir,
            is_master_node=True,
            service_wallet="THR_CONTRACT_PROOF_WALLET",
        )
        assert result["service_wallet"] == "THR_CONTRACT_PROOF_WALLET"

    def test_different_service_wallet_from_user_wallet(self, data_dir):
        payload = _valid_payload()
        result = anchor_contract_proof(
            payload=payload,
            data_dir=data_dir,
            is_master_node=True,
            service_wallet="THR_CONTRACT_PROOF_WALLET",
        )
        assert result["service_wallet"] != "THR_USER_WALLET"
        assert "THR_CONTRACT" in result["service_wallet"]


class TestTransactionID:
    def test_tx_id_deterministic(self):
        manifest = hashlib.sha256(b"same-manifest").hexdigest()
        id1 = _generate_tx_id(manifest)
        id2 = _generate_tx_id(manifest)
        assert id1 == id2

    def test_tx_id_differs_for_different_manifests(self):
        m1 = hashlib.sha256(b"manifest-1").hexdigest()
        m2 = hashlib.sha256(b"manifest-2").hexdigest()
        assert _generate_tx_id(m1) != _generate_tx_id(m2)

    def test_tx_id_is_16_hex_chars(self):
        manifest = hashlib.sha256(b"test").hexdigest()
        tx_id = _generate_tx_id(manifest)
        assert len(tx_id) == 16
        assert all(c in "0123456789abcdef" for c in tx_id)


class TestProofLookup:
    def test_lookup_existing_proof(self, data_dir):
        payload = _valid_payload()
        anchored = anchor_contract_proof(
            payload=payload,
            data_dir=data_dir,
            is_master_node=True,
            service_wallet="THR_CONTRACT_SERVICE",
        )
        found = get_proof_by_manifest(data_dir, payload["manifest_sha256"])
        assert found is not None
        assert found["tx_id"] == anchored["tx_id"]

    def test_lookup_nonexistent_returns_none(self, data_dir):
        fake_hash = hashlib.sha256(b"nonexistent").hexdigest()
        assert get_proof_by_manifest(data_dir, fake_hash) is None


class TestAPIEndpoints:
    @pytest.fixture
    def client(self, data_dir):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True

        def _auth_check(req):
            return req.headers.get("X-API-Key") == "test-api-key"

        register_contract_proof_routes(
            app=app,
            data_dir=data_dir,
            is_master_fn=lambda: True,
            service_wallet="THR_CONTRACT_SERVICE",
            auth_check_fn=_auth_check,
        )
        with app.test_client() as c:
            yield c

    def test_anchor_endpoint_success(self, client):
        payload = _valid_payload()
        resp = client.post(
            "/api/contracts/anchor",
            json=payload,
            headers={"X-API-Key": "test-api-key"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["ok"] is True
        assert data["proof"]["type"] == TX_TYPE

    def test_anchor_endpoint_unauthorized(self, client):
        resp = client.post(
            "/api/contracts/anchor",
            json=_valid_payload(),
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_anchor_endpoint_pii_rejected(self, client):
        payload = _valid_payload(customer_email="leak@example.com")
        resp = client.post(
            "/api/contracts/anchor",
            json=payload,
            headers={"X-API-Key": "test-api-key"},
        )
        assert resp.status_code == 422
        assert "PII" in resp.get_json()["error"]

    def test_lookup_endpoint_success(self, client, data_dir):
        payload = _valid_payload()
        anchor_contract_proof(
            payload=payload,
            data_dir=data_dir,
            is_master_node=True,
            service_wallet="THR_CONTRACT_SERVICE",
        )
        resp = client.get(
            f"/api/contracts/proof/{payload['manifest_sha256']}",
            headers={"X-API-Key": "test-api-key"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["proof"]["type"] == TX_TYPE

    def test_lookup_endpoint_not_found(self, client):
        fake = hashlib.sha256(b"missing").hexdigest()
        resp = client.get(
            f"/api/contracts/proof/{fake}",
            headers={"X-API-Key": "test-api-key"},
        )
        assert resp.status_code == 404

    def test_anchor_endpoint_replica_rejected(self, data_dir):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_contract_proof_routes(
            app=app,
            data_dir=data_dir,
            is_master_fn=lambda: False,
            service_wallet="THR_CONTRACT_SERVICE",
            auth_check_fn=lambda req: True,
        )
        with app.test_client() as c:
            resp = c.post(
                "/api/contracts/anchor",
                json=_valid_payload(),
            )
            assert resp.status_code == 403
            assert resp.get_json()["code"] == "REPLICA_REJECTED"
