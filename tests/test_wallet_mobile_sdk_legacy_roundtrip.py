import copy
import json
import os
import subprocess
import time
from pathlib import Path

import wallet_v1_production_final as verifier


ROOT = Path(__file__).resolve().parents[1]
VECTOR_SCRIPT = ROOT / "tests" / "fixtures" / "mobile_sdk_legacy_signed_tx.cjs"


class _SyntheticRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def exists(self, key):
        return key in self.values

    def setex(self, key, _ttl, value):
        self.values[key] = value


def _signed_vector(nonce, claimed_from=None):
    command = ["node", str(VECTOR_SCRIPT), nonce]
    if claimed_from:
        command.append(claimed_from)
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(result.stdout)


def _binding(vector):
    return {
        "bindings": {
            vector["legacyAddress"]: {
                "address": vector["legacyAddress"],
                "public_key": vector["publicKey"],
                "public_key_address": vector["canonicalAddress"],
                "proof": "synthetic_verified_recovery",
                "status": "active",
            }
        }
    }


def test_historical_mobile_sdk_signed_envelope_requires_explicit_backend_binding(tmp_path, monkeypatch):
    vector = _signed_vector(f"historical-authorized-{time.time_ns()}")
    assert vector["legacyAddress"] == "THR7BBE7B233ED012758E8C1A7281AA805D26177F66"
    assert vector["canonicalAddress"] == "THR3A2D4145A4F098523B3E8127F1DA87CFC55B8E79"
    assert vector["legacyAddress"] != vector["canonicalAddress"]

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    verifier.REDIS_CLIENT = _SyntheticRedis()
    ok, error = verifier.verify_signed_transaction_core(vector["signedTx"])
    assert not ok
    assert "no_binding" in error

    (tmp_path / "wallet_v1_public_key_bindings.json").write_text(
        json.dumps(_binding(vector)), encoding="utf-8"
    )
    verifier.REDIS_CLIENT = _SyntheticRedis()
    ok, error = verifier.verify_signed_transaction_core(vector["signedTx"])
    assert (ok, error) == (True, "")


def test_historical_mobile_sdk_rejects_replay_tampering_and_unrelated_identity(tmp_path, monkeypatch):
    vector = _signed_vector(f"historical-negative-{time.time_ns()}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "wallet_v1_public_key_bindings.json").write_text(
        json.dumps(_binding(vector)), encoding="utf-8"
    )

    redis = _SyntheticRedis()
    verifier.REDIS_CLIENT = redis
    assert verifier.verify_signed_transaction_core(vector["signedTx"])[0] is True
    replay_ok, replay_error = verifier.verify_signed_transaction_core(vector["signedTx"])
    assert replay_ok is False
    assert "replay_detected" in replay_error

    tampered = copy.deepcopy(vector["signedTx"])
    tampered["nonce"] = f"tampered-{time.time_ns()}"
    tampered["amount"] = 8
    verifier.REDIS_CLIENT = _SyntheticRedis()
    tampered_ok, tampered_error = verifier.verify_signed_transaction_core(tampered)
    assert tampered_ok is False
    assert "signature_invalid" in tampered_error

    unrelated = _signed_vector(
        f"unrelated-{time.time_ns()}",
        "THR" + "F" * 40,
    )
    verifier.REDIS_CLIENT = _SyntheticRedis()
    unrelated_ok, unrelated_error = verifier.verify_signed_transaction_core(unrelated["signedTx"])
    assert unrelated_ok is False
    assert "address_binding_invalid" in unrelated_error


def test_historical_binding_rejects_different_public_key(tmp_path, monkeypatch):
    vector = _signed_vector(f"binding-mismatch-{time.time_ns()}")
    binding = _binding(vector)
    binding["bindings"][vector["legacyAddress"]]["public_key"] = "02" + "11" * 32
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "wallet_v1_public_key_bindings.json").write_text(
        json.dumps(binding), encoding="utf-8"
    )
    verifier.REDIS_CLIENT = _SyntheticRedis()
    ok, error = verifier.verify_signed_transaction_core(vector["signedTx"])
    assert ok is False
    assert "binding_key_mismatch" in error


def test_historical_binding_rejects_explicitly_inactive_record(tmp_path, monkeypatch):
    vector = _signed_vector(f"binding-inactive-{time.time_ns()}")
    binding = _binding(vector)
    binding["bindings"][vector["legacyAddress"]]["status"] = "revoked"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "wallet_v1_public_key_bindings.json").write_text(
        json.dumps(binding), encoding="utf-8"
    )
    verifier.REDIS_CLIENT = _SyntheticRedis()
    ok, error = verifier.verify_signed_transaction_core(vector["signedTx"])
    assert ok is False
    assert "binding_inactive:revoked" in error
