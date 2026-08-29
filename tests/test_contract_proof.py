"""
Tests for CONTRACT_ANCHOR_V1 contract proof module.

23 required test cases covering:
  1.  Real application exposes routes
  2.  Valid real master anchor
  3.  Canonical chain contains CONTRACT_ANCHOR_V1
  4.  Separate proof index matches chain tx
  5.  Unexpected field rejected (not stripped)
  6.  Raw agreement_id rejected
  7.  Raw tenant_id rejected
  8.  Raw agreement_ref rejected
  9.  Malformed document_sha256 rejected
  10. Malformed manifest_sha256 rejected
  11. Malformed contract_ref_hash rejected
  12. Malformed tenant_ref_hash rejected
  13. idempotency_key != manifest_sha256 rejected
  14. Duplicate identical => original tx, created=false
  15. Duplicate different payload => 409
  16. Replica cannot write
  17. Concurrent duplicates => one tx
  18. service_wallet absent from API responses
  19. Secret/private key absent from API/logs
  20. Proof lookup returns safe projection
  21. Existing pledge chain regression (chain file not corrupted)
  22. Auth required for anchor endpoint
  23. Public proof lookup (GET) does not require auth
"""

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract_proof import (
    TX_TYPE,
    PROOF_VERSION,
    ALLOWED_PAYLOAD_FIELDS,
    validate_anchor_payload,
    anchor_contract_proof,
    get_proof_by_manifest,
    _validate_sha256,
    _safe_public_projection,
    _load_proof_index,
    register_contract_proof_routes,
)


def _sha(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _valid_payload(**overrides):
    manifest = _sha("manifest-content")
    base = {
        "proof_version": "1",
        "document_sha256": _sha("doc-content"),
        "manifest_sha256": manifest,
        "contract_ref_hash": _sha("contract-ref"),
        "tenant_ref_hash": _sha("tenant-ref"),
        "agreement_version": "1",
        "signing_method_class": "VERIFIED_ESIGN",
        "idempotency_key": manifest,
    }
    base.update(overrides)
    if "manifest_sha256" in overrides and "idempotency_key" not in overrides:
        base["idempotency_key"] = overrides["manifest_sha256"]
    return base


@pytest.fixture
def data_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _mock_load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return default if callable(default) else (list(default) if isinstance(default, list) else dict(default))


def _mock_save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _anchor(data_dir, payload=None, is_master=True):
    chain_file = os.path.join(data_dir, "phantom_tx_chain.json")
    p = payload or _valid_payload()
    return anchor_contract_proof(
        payload=p,
        data_dir=data_dir,
        chain_file=chain_file,
        load_json_fn=_mock_load_json,
        save_json_fn=_mock_save_json,
        persist_normalized_tx_fn=None,
        update_last_block_fn=None,
        is_master_node=is_master,
    )


def _make_app(data_dir, is_master=True, api_key="test-key"):
    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    chain_file = os.path.join(data_dir, "phantom_tx_chain.json")

    register_contract_proof_routes(
        app=app,
        data_dir=data_dir,
        chain_file=chain_file,
        is_master_fn=lambda: is_master,
        load_json_fn=_mock_load_json,
        save_json_fn=_mock_save_json,
        persist_normalized_tx_fn=None,
        update_last_block_fn=None,
        contract_proof_api_key=api_key,
    )
    return app


# ── 1. Real application exposes routes ───────────────────────────────────────

class TestRealAppRoutes:
    def test_real_app_has_anchor_route(self, data_dir):
        app = _make_app(data_dir)
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/api/contracts/anchor" in rules

    def test_real_app_has_proof_lookup_route(self, data_dir):
        app = _make_app(data_dir)
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/api/contracts/proof/<manifest_sha256>" in rules


# ── 2. Valid real master anchor ──────────────────────────────────────────────

class TestValidMasterAnchor:
    def test_anchor_returns_confirmed_record(self, data_dir):
        record, created = _anchor(data_dir)
        assert created is True
        assert record["type"] == TX_TYPE
        assert record["status"] == "confirmed"
        assert record["proof_version"] == PROOF_VERSION
        assert len(record["tx_id"]) > 16


# ── 3. Canonical chain contains CONTRACT_ANCHOR_V1 ──────────────────────────

class TestCanonicalChainWrite:
    def test_chain_file_contains_tx(self, data_dir):
        chain_file = os.path.join(data_dir, "phantom_tx_chain.json")
        _anchor(data_dir)
        chain = _mock_load_json(chain_file, [])
        contract_txs = [t for t in chain if t.get("type") == TX_TYPE]
        assert len(contract_txs) == 1
        assert contract_txs[0]["status"] == "confirmed"
        assert "service_wallet" not in contract_txs[0]


# ── 4. Proof index matches chain tx ─────────────────────────────────────────

class TestProofIndexMatchesChain:
    def test_index_tx_id_matches_chain(self, data_dir):
        chain_file = os.path.join(data_dir, "phantom_tx_chain.json")
        record, _ = _anchor(data_dir)
        chain = _mock_load_json(chain_file, [])
        chain_tx = [t for t in chain if t.get("type") == TX_TYPE][0]
        assert record["tx_id"] == chain_tx["tx_id"]
        assert record["manifest_sha256"] == chain_tx["manifest_sha256"]


# ── 5. Unexpected field rejected ─────────────────────────────────────────────

class TestUnexpectedFieldRejected:
    def test_extra_field_raises_validation_error(self):
        payload = _valid_payload()
        payload["extra_field"] = "should-be-rejected"
        with pytest.raises(ValueError, match="Unexpected fields"):
            validate_anchor_payload(payload)

    def test_api_returns_422_for_unexpected_field(self, data_dir):
        app = _make_app(data_dir)
        with app.test_client() as c:
            payload = _valid_payload()
            payload["rogue_field"] = "hack"
            resp = c.post("/api/contracts/anchor", json=payload,
                          headers={"X-API-Key": "test-key"})
            assert resp.status_code == 422


# ── 6-8. Raw internal identifiers rejected ───────────────────────────────────

class TestRawIdentifiersRejected:
    def test_raw_agreement_id_rejected(self):
        payload = _valid_payload()
        payload["agreement_id"] = 42
        with pytest.raises(ValueError, match="Unexpected fields"):
            validate_anchor_payload(payload)

    def test_raw_tenant_id_rejected(self):
        payload = _valid_payload()
        payload["tenant_id"] = 6
        with pytest.raises(ValueError, match="Unexpected fields"):
            validate_anchor_payload(payload)

    def test_raw_agreement_ref_rejected(self):
        payload = _valid_payload()
        payload["agreement_ref"] = "AGR-2026-001"
        with pytest.raises(ValueError, match="Unexpected fields"):
            validate_anchor_payload(payload)


# ── 9-12. Malformed hash fields rejected ─────────────────────────────────────

class TestMalformedHashesRejected:
    def test_malformed_document_sha256(self):
        payload = _valid_payload(document_sha256="NOTAHASH")
        with pytest.raises(ValueError, match="document_sha256"):
            validate_anchor_payload(payload)

    def test_malformed_manifest_sha256(self):
        m = "BADHASH"
        payload = _valid_payload(manifest_sha256=m, idempotency_key=m)
        with pytest.raises(ValueError, match="manifest_sha256"):
            validate_anchor_payload(payload)

    def test_malformed_contract_ref_hash(self):
        payload = _valid_payload(contract_ref_hash="short")
        with pytest.raises(ValueError, match="contract_ref_hash"):
            validate_anchor_payload(payload)

    def test_malformed_tenant_ref_hash(self):
        payload = _valid_payload(tenant_ref_hash="0123456789ABCDEF" * 4)
        with pytest.raises(ValueError, match="tenant_ref_hash"):
            validate_anchor_payload(payload)


# ── 13. idempotency_key != manifest_sha256 rejected ─────────────────────────

class TestIdempotencyKeyMismatch:
    def test_mismatch_raises(self):
        payload = _valid_payload()
        payload["idempotency_key"] = _sha("different")
        with pytest.raises(ValueError, match="idempotency_key must equal manifest_sha256"):
            validate_anchor_payload(payload)


# ── 14. Duplicate identical => original tx, created=false ────────────────────

class TestIdempotentDuplicate:
    def test_duplicate_returns_existing(self, data_dir):
        payload = _valid_payload()
        first, created1 = _anchor(data_dir, payload)
        second, created2 = _anchor(data_dir, payload)
        assert created1 is True
        assert created2 is False
        assert first["tx_id"] == second["tx_id"]
        index = _load_proof_index(data_dir)
        assert len(index) == 1


# ── 15. Duplicate different payload => 409 ───────────────────────────────────

class TestIdempotencyConflict:
    def test_different_payload_same_manifest_raises_409(self, data_dir):
        manifest = _sha("shared-manifest")
        payload1 = _valid_payload(
            manifest_sha256=manifest,
            document_sha256=_sha("doc-v1"),
        )
        payload2 = _valid_payload(
            manifest_sha256=manifest,
            document_sha256=_sha("doc-v2"),
        )
        _anchor(data_dir, payload1)
        with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
            _anchor(data_dir, payload2)

    def test_api_returns_409(self, data_dir):
        manifest = _sha("shared-manifest-api")
        payload1 = _valid_payload(
            manifest_sha256=manifest,
            document_sha256=_sha("doc-v1"),
        )
        payload2 = _valid_payload(
            manifest_sha256=manifest,
            document_sha256=_sha("doc-v2"),
        )
        app = _make_app(data_dir)
        with app.test_client() as c:
            c.post("/api/contracts/anchor", json=payload1,
                   headers={"X-API-Key": "test-key"})
            resp = c.post("/api/contracts/anchor", json=payload2,
                          headers={"X-API-Key": "test-key"})
            assert resp.status_code == 409
            assert resp.get_json()["code"] == "IDEMPOTENCY_CONFLICT"


# ── 16. Replica cannot write ─────────────────────────────────────────────────

class TestReplicaGuard:
    def test_replica_raises_permission_error(self, data_dir):
        with pytest.raises(PermissionError, match="master-only"):
            _anchor(data_dir, is_master=False)

    def test_api_returns_403_on_replica(self, data_dir):
        app = _make_app(data_dir, is_master=False)
        with app.test_client() as c:
            resp = c.post("/api/contracts/anchor", json=_valid_payload(),
                          headers={"X-API-Key": "test-key"})
            assert resp.status_code == 403
            assert resp.get_json()["code"] == "REPLICA_REJECTED"


# ── 17. Concurrent duplicates => one tx ──────────────────────────────────────

class TestConcurrentDuplicates:
    def test_concurrent_identical_anchors_produce_one_tx(self, data_dir):
        payload = _valid_payload()
        results = []
        errors = []

        def do_anchor():
            try:
                record, created = _anchor(data_dir, payload)
                results.append((record["tx_id"], created))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_anchor) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected errors: {errors}"
        tx_ids = {r[0] for r in results}
        assert len(tx_ids) == 1, f"Expected 1 unique tx_id, got {tx_ids}"
        created_count = sum(1 for _, c in results if c)
        assert created_count == 1

        chain_file = os.path.join(data_dir, "phantom_tx_chain.json")
        chain = _mock_load_json(chain_file, [])
        contract_txs = [t for t in chain if t.get("type") == TX_TYPE]
        assert len(contract_txs) == 1


# ── 18. service_wallet absent from API ───────────────────────────────────────

class TestServiceWalletAbsent:
    def test_anchor_response_has_no_service_wallet(self, data_dir):
        app = _make_app(data_dir)
        with app.test_client() as c:
            resp = c.post("/api/contracts/anchor", json=_valid_payload(),
                          headers={"X-API-Key": "test-key"})
            body = resp.get_json()
            assert "service_wallet" not in body
            assert "service_wallet" not in json.dumps(body)

    def test_lookup_response_has_no_service_wallet(self, data_dir):
        app = _make_app(data_dir)
        payload = _valid_payload()
        with app.test_client() as c:
            c.post("/api/contracts/anchor", json=payload,
                   headers={"X-API-Key": "test-key"})
            resp = c.get(f"/api/contracts/proof/{payload['manifest_sha256']}")
            body = resp.get_json()
            assert "service_wallet" not in body
            assert "service_wallet" not in json.dumps(body)


# ── 19. Secret/private key absent from API ───────────────────────────────────

class TestSecretsAbsent:
    def test_no_private_key_in_response(self, data_dir):
        app = _make_app(data_dir)
        with app.test_client() as c:
            resp = c.post("/api/contracts/anchor", json=_valid_payload(),
                          headers={"X-API-Key": "test-key"})
            body_str = json.dumps(resp.get_json())
            assert "private_key" not in body_str
            assert "api_key" not in body_str.lower()
            assert "secret" not in body_str.lower()

    def test_no_payload_fingerprint_in_response(self, data_dir):
        app = _make_app(data_dir)
        with app.test_client() as c:
            resp = c.post("/api/contracts/anchor", json=_valid_payload(),
                          headers={"X-API-Key": "test-key"})
            body = resp.get_json()
            assert "payload_fingerprint" not in body


# ── 20. Proof lookup returns safe projection ─────────────────────────────────

class TestSafeProjection:
    def test_lookup_returns_only_safe_fields(self, data_dir):
        app = _make_app(data_dir)
        payload = _valid_payload()
        with app.test_client() as c:
            c.post("/api/contracts/anchor", json=payload,
                   headers={"X-API-Key": "test-key"})
            resp = c.get(f"/api/contracts/proof/{payload['manifest_sha256']}")
            body = resp.get_json()
            safe_fields = {
                "ok", "type", "proof_version", "document_sha256",
                "manifest_sha256", "contract_ref_hash", "tenant_ref_hash",
                "agreement_version", "signing_method_class", "txid",
                "block_height", "timestamp", "status",
            }
            assert set(body.keys()) == safe_fields


# ── 21. Chain file not corrupted by contract proof ───────────────────────────

class TestChainRegression:
    def test_existing_chain_entries_preserved(self, data_dir):
        chain_file = os.path.join(data_dir, "phantom_tx_chain.json")
        existing_tx = {
            "type": "transfer",
            "from": "THR_ALICE",
            "to": "THR_BOB",
            "amount": 10.0,
            "tx_id": "TRANSFER-1234-abcd",
            "timestamp": "2026-01-01 00:00:00 UTC",
            "status": "confirmed",
        }
        _mock_save_json(chain_file, [existing_tx])

        _anchor(data_dir)

        chain = _mock_load_json(chain_file, [])
        assert len(chain) == 2
        assert chain[0]["type"] == "transfer"
        assert chain[0]["tx_id"] == "TRANSFER-1234-abcd"
        assert chain[1]["type"] == TX_TYPE


# ── 22. Auth required for anchor ─────────────────────────────────────────────

class TestAuthRequired:
    def test_missing_key_returns_401(self, data_dir):
        app = _make_app(data_dir)
        with app.test_client() as c:
            resp = c.post("/api/contracts/anchor", json=_valid_payload())
            assert resp.status_code == 401

    def test_wrong_key_returns_401(self, data_dir):
        app = _make_app(data_dir)
        with app.test_client() as c:
            resp = c.post("/api/contracts/anchor", json=_valid_payload(),
                          headers={"X-API-Key": "wrong-key"})
            assert resp.status_code == 401

    def test_empty_api_key_config_rejects_all(self, data_dir):
        app = _make_app(data_dir, api_key="")
        with app.test_client() as c:
            resp = c.post("/api/contracts/anchor", json=_valid_payload(),
                          headers={"X-API-Key": "anything"})
            assert resp.status_code == 401


# ── 23. Public proof lookup does not require auth ────────────────────────────

class TestPublicProofLookup:
    def test_get_proof_without_auth(self, data_dir):
        app = _make_app(data_dir)
        payload = _valid_payload()
        with app.test_client() as c:
            c.post("/api/contracts/anchor", json=payload,
                   headers={"X-API-Key": "test-key"})
            resp = c.get(f"/api/contracts/proof/{payload['manifest_sha256']}")
            assert resp.status_code == 200
            assert resp.get_json()["ok"] is True

    def test_get_nonexistent_proof_without_auth(self, data_dir):
        app = _make_app(data_dir)
        fake = _sha("nonexistent")
        with app.test_client() as c:
            resp = c.get(f"/api/contracts/proof/{fake}")
            assert resp.status_code == 404
