"""
ThronosChain Contract Proof Module — CONTRACT_ANCHOR_V1

Anchors OPS agreement proofs to the canonical ThronosChain ledger
(phantom_tx_chain.json) as real chain transactions.  This is NOT
a parallel blockchain — it uses the existing master write path:
load_json(CHAIN_FILE) → append → save_json(CHAIN_FILE).

A separate contract_proof_ledger.json serves only as a fast lookup
index keyed by manifest_sha256.

Security invariants:
  - Strict payload allowlist: unexpected fields → hard 422 (not stripped)
  - PII rejection: name/email/phone/address fields → hard 422
  - Opaque hashed references: raw agreement_id/tenant_id/agreement_ref
    never go on-chain; replaced by contract_ref_hash / tenant_ref_hash
  - Master-only writes: replica nodes → 403
  - Idempotent: same manifest_sha256 + identical canonical payload → existing proof
  - Conflict: same manifest_sha256 + different payload → 409
  - Service wallet never exposed in API responses, logs, or on-chain records
  - Fail-closed: missing THRONOS_CONTRACT_PROOF_API_KEY → hard error
"""

import hashlib
import json
import logging
import os
import re
import time
import threading
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

TX_TYPE = "CONTRACT_ANCHOR_V1"
PROOF_VERSION = "1"

ALLOWED_PAYLOAD_FIELDS = frozenset({
    "proof_version",
    "document_sha256",
    "manifest_sha256",
    "contract_ref_hash",
    "tenant_ref_hash",
    "agreement_version",
    "signing_method_class",
    "idempotency_key",
})

SIGNING_METHOD_CLASSES = ("QES", "VERIFIED_ESIGN", "MIXED")

PII_FIELD_PATTERNS = re.compile(
    r"(name|email|phone|mobile|address|street|city|postcode"
    r"|zip|ssn|passport|dob|birth|national_id|tax_id"
    r"|iban|account_number|card_number)",
    re.IGNORECASE,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_PROOF_LOCK = threading.Lock()


class ContractProofConfigError(Exception):
    pass


def _validate_sha256(value: str, field_name: str = "hash") -> str:
    if not _SHA256_RE.match(value or ""):
        raise ValueError(
            f"Invalid {field_name}: must be 64 lowercase hex chars, "
            f"got '{value}'"
        )
    return value


def _reject_pii_fields(payload: dict) -> None:
    for key in payload:
        if PII_FIELD_PATTERNS.search(key):
            raise ValueError(
                f"PII field '{key}' is not allowed in contract proof payloads. "
                "No customer personal data goes on-chain."
            )


def _reject_unexpected_fields(payload: dict) -> None:
    unexpected = set(payload.keys()) - ALLOWED_PAYLOAD_FIELDS
    if unexpected:
        raise ValueError(
            f"Unexpected fields in payload: {sorted(unexpected)}. "
            f"Only these fields are allowed: {sorted(ALLOWED_PAYLOAD_FIELDS)}"
        )


def _canonical_payload_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _proof_index_path(data_dir: str) -> str:
    return os.path.join(data_dir, "contract_proof_ledger.json")


def _load_proof_index(data_dir: str) -> list:
    path = _proof_index_path(data_dir)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load contract proof index: %s", e)
    return []


def _save_proof_index(data_dir: str, index: list) -> None:
    path = _proof_index_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _find_existing_proof(index: list, manifest_sha256: str) -> Optional[dict]:
    for entry in index:
        if entry.get("manifest_sha256") == manifest_sha256:
            return entry
    return None


def _safe_public_projection(record: dict) -> dict:
    return {
        "ok": True,
        "type": record.get("type", TX_TYPE),
        "proof_version": record.get("proof_version", PROOF_VERSION),
        "document_sha256": record.get("document_sha256"),
        "manifest_sha256": record.get("manifest_sha256"),
        "contract_ref_hash": record.get("contract_ref_hash"),
        "tenant_ref_hash": record.get("tenant_ref_hash"),
        "agreement_version": record.get("agreement_version"),
        "signing_method_class": record.get("signing_method_class"),
        "txid": record.get("tx_id"),
        "block_height": record.get("block_height"),
        "timestamp": record.get("timestamp"),
        "status": record.get("status"),
    }


def validate_anchor_payload(payload: dict) -> dict:
    _reject_pii_fields(payload)
    _reject_unexpected_fields(payload)

    required = (
        "document_sha256", "manifest_sha256", "contract_ref_hash",
        "tenant_ref_hash", "signing_method_class", "idempotency_key",
    )
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    if payload["signing_method_class"] not in SIGNING_METHOD_CLASSES:
        raise ValueError(
            f"Invalid signing_method_class '{payload['signing_method_class']}'; "
            f"must be one of {SIGNING_METHOD_CLASSES}"
        )

    _validate_sha256(payload["document_sha256"], "document_sha256")
    _validate_sha256(payload["manifest_sha256"], "manifest_sha256")
    _validate_sha256(payload["contract_ref_hash"], "contract_ref_hash")
    _validate_sha256(payload["tenant_ref_hash"], "tenant_ref_hash")
    _validate_sha256(payload["idempotency_key"], "idempotency_key")

    if payload["idempotency_key"] != payload["manifest_sha256"]:
        raise ValueError(
            "idempotency_key must equal manifest_sha256 to prevent "
            "duplicate anchors for the same manifest."
        )

    validated = {k: payload[k] for k in ALLOWED_PAYLOAD_FIELDS if k in payload}
    validated["proof_version"] = payload.get("proof_version", PROOF_VERSION)
    return validated


def anchor_contract_proof(
    payload: dict,
    data_dir: str,
    chain_file: str,
    load_json_fn,
    save_json_fn,
    persist_normalized_tx_fn,
    update_last_block_fn,
    is_master_node: bool,
) -> Tuple[dict, bool]:
    """
    Anchor a contract proof to the canonical ThronosChain ledger.

    Returns (proof_record, created):
      - created=True: new chain tx written
      - created=False: idempotent hit, existing record returned

    Raises:
      PermissionError — replica node
      ValueError — validation failure or idempotency conflict (409)
    """
    if not is_master_node:
        raise PermissionError(
            "Contract proof writes are master-only. "
            "Replica nodes must forward to the master API."
        )

    validated = validate_anchor_payload(payload)
    manifest_sha256 = validated["manifest_sha256"]
    payload_fingerprint = _canonical_payload_fingerprint(validated)

    with _PROOF_LOCK:
        index = _load_proof_index(data_dir)
        existing = _find_existing_proof(index, manifest_sha256)

        if existing:
            if existing.get("payload_fingerprint") != payload_fingerprint:
                raise ValueError(
                    "IDEMPOTENCY_CONFLICT: manifest_sha256 already anchored "
                    "with a different payload. Cannot overwrite."
                )
            return (existing, False)

        chain = load_json_fn(chain_file, [])
        chain_height = len(chain)
        ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        tx_id = f"CONTRACT-ANCHOR-{int(time.time())}-{os.urandom(4).hex()}"

        chain_tx = {
            "type": TX_TYPE,
            "tx_id": tx_id,
            "timestamp": ts,
            "status": "confirmed",
            "height": chain_height,
            "amount": 0.0,
            "fee_burned": 0.0,
            "proof_version": validated.get("proof_version", PROOF_VERSION),
            "document_sha256": validated["document_sha256"],
            "manifest_sha256": validated["manifest_sha256"],
            "contract_ref_hash": validated["contract_ref_hash"],
            "tenant_ref_hash": validated["tenant_ref_hash"],
            "agreement_version": validated.get("agreement_version"),
            "signing_method_class": validated["signing_method_class"],
        }

        chain.append(chain_tx)
        save_json_fn(chain_file, chain)

        if persist_normalized_tx_fn:
            persist_normalized_tx_fn(chain_tx)
        if update_last_block_fn:
            update_last_block_fn(chain_tx, is_block=False)

        index_record = {
            **chain_tx,
            "payload_fingerprint": payload_fingerprint,
            "block_height": chain_height,
        }
        index.append(index_record)
        _save_proof_index(data_dir, index)

    logger.info(
        "CONTRACT_ANCHOR_V1: anchored tx_id=%s manifest=%s",
        tx_id, manifest_sha256,
    )
    return (index_record, True)


def get_proof_by_manifest(data_dir: str, manifest_sha256: str) -> Optional[dict]:
    _validate_sha256(manifest_sha256, "manifest_sha256")
    index = _load_proof_index(data_dir)
    return _find_existing_proof(index, manifest_sha256)


def register_contract_proof_routes(
    app,
    data_dir: str,
    chain_file: str,
    is_master_fn,
    load_json_fn,
    save_json_fn,
    persist_normalized_tx_fn,
    update_last_block_fn,
    contract_proof_api_key: str,
):
    from flask import request, jsonify

    def _check_contract_proof_auth(req) -> bool:
        if not contract_proof_api_key:
            return False
        provided = (
            req.headers.get("X-API-Key")
            or req.headers.get("X-Internal-Key")
            or ""
        ).strip()
        return provided == contract_proof_api_key

    @app.route("/api/contracts/anchor", methods=["POST"])
    def api_contract_anchor():
        if not _check_contract_proof_auth(request):
            return jsonify({"error": "Unauthorized", "code": "AUTH_REQUIRED"}), 401

        if not is_master_fn():
            return jsonify({
                "error": "Contract proof writes are master-only",
                "code": "REPLICA_REJECTED",
            }), 403

        try:
            body = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Invalid JSON body"}), 400

        if not isinstance(body, dict):
            return jsonify({"error": "Payload must be a JSON object"}), 400

        try:
            record, created = anchor_contract_proof(
                payload=body,
                data_dir=data_dir,
                chain_file=chain_file,
                load_json_fn=load_json_fn,
                save_json_fn=save_json_fn,
                persist_normalized_tx_fn=persist_normalized_tx_fn,
                update_last_block_fn=update_last_block_fn,
                is_master_node=True,
            )
            projection = _safe_public_projection(record)
            projection["created"] = created
            return jsonify(projection), 201 if created else 200

        except ValueError as e:
            err_str = str(e)
            if "IDEMPOTENCY_CONFLICT" in err_str:
                return jsonify({"error": err_str, "code": "IDEMPOTENCY_CONFLICT"}), 409
            return jsonify({"error": err_str, "code": "VALIDATION_ERROR"}), 422
        except PermissionError as e:
            return jsonify({"error": str(e), "code": "REPLICA_REJECTED"}), 403

    @app.route("/api/contracts/proof/<manifest_sha256>", methods=["GET"])
    def api_contract_proof_lookup(manifest_sha256):
        """Public verification endpoint — no auth required."""
        try:
            _validate_sha256(manifest_sha256, "manifest_sha256")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        proof = get_proof_by_manifest(data_dir, manifest_sha256)
        if proof:
            return jsonify(_safe_public_projection(proof)), 200
        return jsonify({"ok": False, "proof": None}), 404
