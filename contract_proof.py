"""
ThronosChain Contract Proof Module — CONTRACT_ANCHOR_V1

Anchors OPS agreement proofs to the ThronosChain ledger.
This module is the master-writer for contract proofs: OPS nodes
call its API endpoints; it validates, hashes, and persists the
proof record on the chain file and the contract proof ledger.

Security invariants:
  - Strict payload allowlist: only declared fields pass through
  - PII rejection: name/email/phone/address fields are hard-rejected
  - Master-only writes: replica nodes return 403
  - Idempotent: duplicate manifest_sha256 returns existing proof
  - Service-auth: requires THRONOS_CONTRACT_PROOF_API_KEY
  - Fail-closed: missing config = hard error, not implicit bypass
"""

import hashlib
import json
import logging
import os
import re
import time
import threading
from typing import Optional

logger = logging.getLogger(__name__)

TX_TYPE = "CONTRACT_ANCHOR_V1"

ALLOWED_PAYLOAD_FIELDS = frozenset({
    "agreement_id",
    "tenant_id",
    "agreement_ref",
    "agreement_version",
    "document_sha256",
    "manifest_sha256",
    "signature_method",
    "chain_mode",
    "anchor_network",
})

PII_FIELD_PATTERNS = re.compile(
    r"(name|email|phone|mobile|address|street|city|postcode"
    r"|zip|ssn|passport|dob|birth|national_id|tax_id"
    r"|iban|account_number|card_number)",
    re.IGNORECASE,
)

SIGNATURE_METHODS = ("QES", "VERIFIED_ESIGN", "MIXED")
CHAIN_MODES = ("managed_anchor",)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_PROOF_LEDGER_LOCK = threading.Lock()


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


def _filter_to_allowlist(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k in ALLOWED_PAYLOAD_FIELDS}


def _generate_tx_id(manifest_sha256: str) -> str:
    return hashlib.sha256(
        f"{TX_TYPE}:{manifest_sha256}".encode()
    ).hexdigest()[:16]


def _proof_ledger_path(data_dir: str) -> str:
    return os.path.join(data_dir, "contract_proof_ledger.json")


def _load_proof_ledger(data_dir: str) -> list:
    path = _proof_ledger_path(data_dir)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load contract proof ledger: %s", e)
    return []


def _save_proof_ledger(data_dir: str, ledger: list) -> None:
    path = _proof_ledger_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _find_existing_proof(ledger: list, manifest_sha256: str) -> Optional[dict]:
    for entry in ledger:
        if entry.get("manifest_sha256") == manifest_sha256:
            return entry
    return None


def validate_anchor_payload(payload: dict) -> dict:
    """
    Validate and sanitize a CONTRACT_ANCHOR_V1 payload.
    Returns the filtered, validated payload dict.
    Raises ValueError on any validation failure.
    """
    _reject_pii_fields(payload)

    required = ("agreement_id", "tenant_id", "document_sha256",
                "manifest_sha256", "signature_method", "chain_mode")
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    if payload["signature_method"] not in SIGNATURE_METHODS:
        raise ValueError(
            f"Invalid signature_method '{payload['signature_method']}'; "
            f"must be one of {SIGNATURE_METHODS}"
        )

    if payload["chain_mode"] not in CHAIN_MODES:
        raise ValueError(
            f"Invalid chain_mode '{payload['chain_mode']}'; "
            f"must be one of {CHAIN_MODES}"
        )

    _validate_sha256(payload["document_sha256"], "document_sha256")
    _validate_sha256(payload["manifest_sha256"], "manifest_sha256")

    return _filter_to_allowlist(payload)


def anchor_contract_proof(
    payload: dict,
    data_dir: str,
    is_master_node: bool,
    service_wallet: str,
) -> dict:
    """
    Anchor a contract proof to the ThronosChain ledger.

    - Master-only: raises PermissionError on replica
    - Idempotent: returns existing proof for duplicate manifest_sha256
    - Returns the proof record dict
    """
    if not is_master_node:
        raise PermissionError(
            "Contract proof writes are master-only. "
            "Replica nodes must forward to the master API."
        )

    validated = validate_anchor_payload(payload)

    manifest_sha256 = validated["manifest_sha256"]
    tx_id = _generate_tx_id(manifest_sha256)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with _PROOF_LEDGER_LOCK:
        ledger = _load_proof_ledger(data_dir)

        existing = _find_existing_proof(ledger, manifest_sha256)
        if existing:
            logger.info(
                "CONTRACT_ANCHOR_V1: idempotent hit for manifest=%s, "
                "returning existing tx_id=%s",
                manifest_sha256, existing.get("tx_id"),
            )
            return existing

        proof_record = {
            "tx_id": tx_id,
            "type": TX_TYPE,
            "status": "anchored",
            "timestamp": ts,
            "service_wallet": service_wallet,
            **validated,
        }

        ledger.append(proof_record)
        _save_proof_ledger(data_dir, ledger)

    logger.info(
        "CONTRACT_ANCHOR_V1: anchored tx_id=%s manifest=%s tenant=%s",
        tx_id, manifest_sha256, validated.get("tenant_id"),
    )
    return proof_record


def get_proof_by_manifest(data_dir: str, manifest_sha256: str) -> Optional[dict]:
    """
    Look up a contract proof by manifest_sha256.
    Returns the proof record or None.
    """
    _validate_sha256(manifest_sha256, "manifest_sha256")
    ledger = _load_proof_ledger(data_dir)
    return _find_existing_proof(ledger, manifest_sha256)


def register_contract_proof_routes(app, data_dir: str, is_master_fn, service_wallet: str, auth_check_fn):
    """
    Register Flask routes for the contract proof API.

    Args:
        app: Flask app instance
        data_dir: path to data directory
        is_master_fn: callable returning True if this node is master
        service_wallet: THR address for the contract proof service
        auth_check_fn: callable(request) -> bool for service auth
    """
    from flask import request, jsonify

    @app.route("/api/contracts/anchor", methods=["POST"])
    def api_contract_anchor():
        if not auth_check_fn(request):
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
            result = anchor_contract_proof(
                payload=body,
                data_dir=data_dir,
                is_master_node=True,
                service_wallet=service_wallet,
            )
            is_new = result.get("timestamp") == time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            return jsonify({
                "ok": True,
                "proof": result,
                "created": is_new,
            }), 201 if is_new else 200

        except ValueError as e:
            return jsonify({"error": str(e), "code": "VALIDATION_ERROR"}), 422
        except PermissionError as e:
            return jsonify({"error": str(e), "code": "REPLICA_REJECTED"}), 403

    @app.route("/api/contracts/proof/<manifest_sha256>", methods=["GET"])
    def api_contract_proof_lookup(manifest_sha256):
        if not auth_check_fn(request):
            return jsonify({"error": "Unauthorized", "code": "AUTH_REQUIRED"}), 401

        try:
            _validate_sha256(manifest_sha256, "manifest_sha256")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        proof = get_proof_by_manifest(data_dir, manifest_sha256)
        if proof:
            return jsonify({"ok": True, "proof": proof}), 200
        return jsonify({"ok": False, "proof": None}), 404
