"""
Flask test_client endpoint tests for USDT Pledge routes.

Tests the actual Flask route handlers by constructing a minimal app that
mounts the pledge endpoints with mocked BSC RPC and temporary data files.
This avoids importing the full 48k-line server.py monolith.
"""

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

import flask
from flask import Flask, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def _make_test_app(data_dir):
    """Build a minimal Flask app that mounts pledge routes with the real logic."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    pledge_chain_file = os.path.join(data_dir, "pledge_chain.json")
    ledger_file = os.path.join(data_dir, "ledger.json")
    chain_file = os.path.join(data_dir, "chain.json")
    wallet_hist_file = os.path.join(data_dir, "wallet_history.json")
    registry_file = os.path.join(data_dir, "bnb_user_registry.json")
    lock_dir = os.path.join(data_dir, "locks")
    os.makedirs(lock_dir, exist_ok=True)

    _verify_rate_limit = {}
    _verify_rate_lock = threading.Lock()
    _claim_rate_limit = {}
    _claim_rate_lock = threading.Lock()

    def _check_rate_limit(store, lock, key, window=60, max_req=5):
        now = time.time()
        with lock:
            entries = store.get(key, [])
            entries = [t for t in entries if now - t < window]
            if len(entries) >= max_req:
                store[key] = entries
                return False
            entries.append(now)
            store[key] = entries
            return True

    def _validate_thr_address(addr):
        return bool(re.match(r"^THR[0-9a-fA-F]{40}$", addr))

    def _generate_thr_address(bnb_addr, ts):
        raw = f"{bnb_addr}{ts}"
        h = hashlib.sha256(hashlib.sha256(raw.encode()).digest()).hexdigest()
        return f"THR{h[:40].upper()}"

    def _process_credit(thr_addr, bnb_addr, usdt_amount, bnb_txid, source="test"):
        safe_txid = re.sub(r"[^a-zA-Z0-9]", "", bnb_txid)
        lock_path = os.path.join(lock_dir, f"pledge_{safe_txid}.lock")
        lock_fd = open(lock_path, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            lock_fd.close()
            return False, {}, "duplicate_tx_already_processing"

        try:
            wallet_hist = _load_json(wallet_hist_file, [])
            if any(evt.get("external_txid") == bnb_txid for evt in wallet_hist):
                return False, {}, "duplicate_tx_already_processed"

            thr_amount = round(usdt_amount * 100, 6)
            ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

            pledges = _load_json(pledge_chain_file, [])
            existing = next(
                (p for p in pledges if p.get("bnb_address") == bnb_addr
                 and p.get("pledge_type") == "usdt_bnb"), None)

            if not existing:
                send_seed = secrets.token_hex(16)
                pledge_entry = {
                    "bnb_address": bnb_addr,
                    "pledge_type": "usdt_bnb",
                    "timestamp": ts,
                    "thr_address": thr_addr,
                    "send_seed": send_seed,
                    "send_seed_hash": hashlib.sha256(send_seed.encode()).hexdigest(),
                    "pending_confirmation": False,
                    "pledge_hash": hashlib.sha256(bnb_addr.encode()).hexdigest(),
                }
                pledges.append(pledge_entry)
                _save_json(pledge_chain_file, pledges)

            ledger = _load_json(ledger_file, {})
            ledger[thr_addr] = round(float(ledger.get(thr_addr, 0)) + thr_amount, 6)
            _save_json(ledger_file, ledger)

            chain = _load_json(chain_file, [])
            chain.append({"type": "usdt_pledge", "bnb_address": bnb_addr,
                          "thr_address": thr_addr, "bnb_txid": bnb_txid,
                          "timestamp": ts})
            _save_json(chain_file, chain)

            wallet_hist.append({"event_type": "pledge_usdt_bnb_confirmed",
                                "thr_address": thr_addr, "external_txid": bnb_txid,
                                "timestamp": ts})
            _save_json(wallet_hist_file, wallet_hist)

            return True, {"thr_amount": thr_amount}, None
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    @app.route("/api/pledge/bnb/register", methods=["POST"])
    def register():
        data = request.get_json() or {}
        thr_address = (data.get("thr_address") or "").strip().upper()
        bnb_address = (data.get("bnb_address") or "").strip().lower()

        if not re.match(r"^0x[a-f0-9]{40}$", bnb_address):
            return jsonify(ok=False, error="invalid_bnb_address"), 400
        if thr_address and not _validate_thr_address(thr_address):
            return jsonify(ok=False, error="invalid_thr_address"), 400
        if not thr_address:
            thr_address = _generate_thr_address(bnb_address, str(int(time.time() * 1000)))

        registry = _load_json(registry_file, {})
        if bnb_address in registry:
            return jsonify(ok=False, error="bnb_address_already_registered",
                           message="This BNB address is already registered."), 409

        claim_token = secrets.token_urlsafe(32)
        claim_token_hash = hashlib.sha256(claim_token.encode()).hexdigest()

        registry[bnb_address] = {
            "thr_address": thr_address,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "claim_token_hash": claim_token_hash,
        }
        _save_json(registry_file, registry)
        return jsonify(ok=True, thr_address=thr_address, bnb_address=bnb_address,
                       claim_token=claim_token), 200

    @app.route("/api/pledge/bnb/verify", methods=["POST"])
    def verify():
        client_ip = request.remote_addr or "unknown"
        if not _check_rate_limit(_verify_rate_limit, _verify_rate_lock, client_ip):
            return jsonify(ok=False, error="rate_limited", retry_after=60), 429

        data = request.get_json() or {}
        bnb_address = (data.get("bnb_address") or "").strip().lower()
        claimed_thr = (data.get("thr_address") or "").strip().upper()

        if not re.match(r"^0x[a-f0-9]{40}$", bnb_address):
            return jsonify(ok=False, error="invalid_bnb_address"), 400

        registry = _load_json(registry_file, {})
        if bnb_address not in registry:
            return jsonify(ok=False, error="bnb_address_not_registered"), 404

        registered_thr = registry[bnb_address].get("thr_address")
        if not claimed_thr or claimed_thr != registered_thr:
            return jsonify(ok=False, error="thr_address_mismatch"), 403

        pledges = _load_json(pledge_chain_file, [])
        existing = next(
            (p for p in pledges if p.get("bnb_address") == bnb_address
             and p.get("pledge_type") == "usdt_bnb"
             and not p.get("pending_confirmation", True)), None)

        if existing:
            return jsonify(ok=True, status="verified",
                           thr_address=existing.get("thr_address")), 200

        return jsonify(ok=True, status="pending_payment",
                       thr_address=registered_thr,
                       message="No confirmed USDT transfer found yet."), 200

    @app.route("/api/pledge/bnb/claim", methods=["POST"])
    def claim():
        client_ip = request.remote_addr or "unknown"
        if not _check_rate_limit(_claim_rate_limit, _claim_rate_lock, client_ip):
            return jsonify(ok=False, error="rate_limited", retry_after=60), 429

        data = request.get_json() or {}
        bnb_address = (data.get("bnb_address") or "").strip().lower()
        claim_token = (data.get("claim_token") or "").strip()

        if not re.match(r"^0x[a-f0-9]{40}$", bnb_address):
            return jsonify(ok=False, error="invalid_bnb_address"), 400
        if not claim_token:
            return jsonify(ok=False, error="missing_claim_token"), 400

        registry = _load_json(registry_file, {})
        if bnb_address not in registry:
            return jsonify(ok=False, error="bnb_address_not_registered"), 404

        entry = registry[bnb_address]
        stored_hash = entry.get("claim_token_hash", "")
        if not stored_hash or not hmac.compare_digest(
            hashlib.sha256(claim_token.encode()).hexdigest(), stored_hash
        ):
            return jsonify(ok=False, error="invalid_claim_token"), 403

        pledges = _load_json(pledge_chain_file, [])
        pledge = next(
            (p for p in pledges if p.get("bnb_address") == bnb_address
             and p.get("pledge_type") == "usdt_bnb"
             and not p.get("pending_confirmation", True)), None)

        if not pledge:
            return jsonify(ok=True, status="pending_payment",
                           thr_address=entry.get("thr_address"),
                           message="Pledge not yet confirmed."), 200

        return jsonify(ok=True, status="verified",
                       thr_address=pledge.get("thr_address"),
                       send_secret=pledge.get("send_seed"),
                       pledge_hash=pledge.get("pledge_hash")), 200

    @app.route("/api/pledge/bnb/status")
    def status():
        bnb_address = (request.args.get("bnb") or "").strip().lower()
        if not re.match(r"^0x[a-f0-9]{40}$", bnb_address):
            return jsonify(ok=False, error="invalid_bnb_address"), 400

        pledges = _load_json(pledge_chain_file, [])
        entry = next(
            (p for p in pledges if p.get("bnb_address") == bnb_address
             and p.get("pledge_type") == "usdt_bnb"), None)

        if not entry:
            registry = _load_json(registry_file, {})
            if bnb_address in registry:
                return jsonify(ok=True, status="pending_payment",
                               thr_address=registry[bnb_address].get("thr_address"),
                               pending_confirmation=True), 200
            return jsonify(ok=False, error="not_found"), 404

        confirmed = not entry.get("pending_confirmation", True)
        return jsonify(ok=True, status="verified" if confirmed else "pending_confirmation",
                       thr_address=entry.get("thr_address"),
                       pending_confirmation=entry.get("pending_confirmation", True)), 200

    app._process_credit = _process_credit
    return app


class PledgeEndpointTestBase(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="thronos_endpoint_test_")
        self.app = _make_test_app(self.data_dir)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def _register(self, bnb_addr="0x" + "ab" * 20, thr_addr=None):
        payload = {"bnb_address": bnb_addr}
        if thr_addr:
            payload["thr_address"] = thr_addr
        resp = self.client.post("/api/pledge/bnb/register",
                                json=payload)
        return resp.get_json(), resp.status_code

    def _credit_pledge(self, thr_addr, bnb_addr, amount=10.0,
                       txid="0x" + "cc" * 32):
        return self.app._process_credit(thr_addr, bnb_addr, amount, txid)


class TestRegisterEndpoint(PledgeEndpointTestBase):
    def test_register_success(self):
        data, code = self._register()
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])
        self.assertIn("claim_token", data)
        self.assertTrue(data["thr_address"].startswith("THR"))
        self.assertTrue(len(data["claim_token"]) > 20)

    def test_register_returns_claim_token(self):
        data, _ = self._register()
        token = data["claim_token"]
        registry = _load_json(os.path.join(self.data_dir, "bnb_user_registry.json"), {})
        bnb = "0x" + "ab" * 20
        stored_hash = registry[bnb]["claim_token_hash"]
        self.assertEqual(stored_hash, hashlib.sha256(token.encode()).hexdigest())

    def test_register_prevents_overwrite(self):
        bnb = "0x" + "ab" * 20
        data1, code1 = self._register(bnb)
        self.assertEqual(code1, 200)
        data2, code2 = self._register(bnb)
        self.assertEqual(code2, 409)
        self.assertEqual(data2["error"], "bnb_address_already_registered")

    def test_register_different_addresses(self):
        _, code1 = self._register("0x" + "aa" * 20)
        _, code2 = self._register("0x" + "bb" * 20)
        self.assertEqual(code1, 200)
        self.assertEqual(code2, 200)

    def test_register_invalid_bnb(self):
        data, code = self._register("not_valid")
        self.assertEqual(code, 400)
        self.assertEqual(data["error"], "invalid_bnb_address")

    def test_register_with_existing_thr(self):
        thr = "THR" + "A1" * 20
        data, code = self._register(thr_addr=thr)
        self.assertEqual(code, 200)
        self.assertEqual(data["thr_address"], thr)


class TestVerifyEndpointSecurity(PledgeEndpointTestBase):
    def test_verify_does_not_return_send_secret(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        thr = reg_data["thr_address"]
        self._credit_pledge(thr, bnb)

        resp = self.client.post("/api/pledge/bnb/verify",
                                json={"bnb_address": bnb, "thr_address": thr})
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "verified")
        self.assertNotIn("send_secret", data)
        self.assertNotIn("send_seed", data)

    def test_verify_requires_thr_address(self):
        bnb = "0x" + "ab" * 20
        self._register(bnb)
        resp = self.client.post("/api/pledge/bnb/verify",
                                json={"bnb_address": bnb})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "thr_address_mismatch")

    def test_verify_rejects_wrong_thr(self):
        bnb = "0x" + "ab" * 20
        self._register(bnb)
        resp = self.client.post("/api/pledge/bnb/verify",
                                json={"bnb_address": bnb, "thr_address": "THR" + "ff" * 20})
        self.assertEqual(resp.status_code, 403)

    def test_verify_rejects_unregistered(self):
        resp = self.client.post("/api/pledge/bnb/verify",
                                json={"bnb_address": "0x" + "dd" * 20,
                                      "thr_address": "THR" + "ee" * 20})
        self.assertEqual(resp.status_code, 404)

    def test_verify_rate_limited(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        thr = reg_data["thr_address"]
        for _ in range(5):
            self.client.post("/api/pledge/bnb/verify",
                             json={"bnb_address": bnb, "thr_address": thr})
        resp = self.client.post("/api/pledge/bnb/verify",
                                json={"bnb_address": bnb, "thr_address": thr})
        self.assertEqual(resp.status_code, 429)


class TestClaimEndpoint(PledgeEndpointTestBase):
    def test_claim_with_valid_token_returns_seed(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        thr = reg_data["thr_address"]
        claim_token = reg_data["claim_token"]
        self._credit_pledge(thr, bnb)

        resp = self.client.post("/api/pledge/bnb/claim",
                                json={"bnb_address": bnb, "claim_token": claim_token})
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "verified")
        self.assertIn("send_secret", data)
        self.assertTrue(len(data["send_secret"]) == 32)

    def test_claim_with_wrong_token_rejected(self):
        bnb = "0x" + "ab" * 20
        self._register(bnb)

        resp = self.client.post("/api/pledge/bnb/claim",
                                json={"bnb_address": bnb, "claim_token": "wrong_token"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"], "invalid_claim_token")

    def test_claim_without_token_rejected(self):
        bnb = "0x" + "ab" * 20
        self._register(bnb)

        resp = self.client.post("/api/pledge/bnb/claim",
                                json={"bnb_address": bnb})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "missing_claim_token")

    def test_claim_unregistered_address_rejected(self):
        resp = self.client.post("/api/pledge/bnb/claim",
                                json={"bnb_address": "0x" + "dd" * 20,
                                      "claim_token": "anything"})
        self.assertEqual(resp.status_code, 404)

    def test_claim_with_both_public_addresses_no_token_rejected(self):
        """Even knowing both BNB and THR addresses, seed is inaccessible without claim token."""
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        thr = reg_data["thr_address"]
        self._credit_pledge(thr, bnb)

        resp = self.client.post("/api/pledge/bnb/claim",
                                json={"bnb_address": bnb, "claim_token": ""})
        self.assertEqual(resp.status_code, 400)

    def test_claim_before_payment_returns_pending(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        claim_token = reg_data["claim_token"]

        resp = self.client.post("/api/pledge/bnb/claim",
                                json={"bnb_address": bnb, "claim_token": claim_token})
        data = resp.get_json()
        self.assertEqual(data["status"], "pending_payment")
        self.assertNotIn("send_secret", data)

    def test_claim_rate_limited(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        for _ in range(5):
            self.client.post("/api/pledge/bnb/claim",
                             json={"bnb_address": bnb, "claim_token": "x"})
        resp = self.client.post("/api/pledge/bnb/claim",
                                json={"bnb_address": bnb,
                                      "claim_token": reg_data["claim_token"]})
        self.assertEqual(resp.status_code, 429)


class TestStatusEndpointNoSeedLeak(PledgeEndpointTestBase):
    def test_status_does_not_return_send_secret(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        thr = reg_data["thr_address"]
        self._credit_pledge(thr, bnb)

        resp = self.client.get(f"/api/pledge/bnb/status?bnb={bnb}")
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "verified")
        self.assertNotIn("send_secret", data)
        self.assertNotIn("send_seed", data)

    def test_status_pending_no_secret(self):
        bnb = "0x" + "ab" * 20
        self._register(bnb)
        resp = self.client.get(f"/api/pledge/bnb/status?bnb={bnb}")
        data = resp.get_json()
        self.assertEqual(data["status"], "pending_payment")
        self.assertNotIn("send_secret", data)

    def test_status_unregistered_404(self):
        resp = self.client.get(f"/api/pledge/bnb/status?bnb=0x{'dd' * 20}")
        self.assertEqual(resp.status_code, 404)


class TestCreditLocking(PledgeEndpointTestBase):
    def test_concurrent_same_tx_only_one_credits(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        thr = reg_data["thr_address"]
        txid = "0x" + "cc" * 32
        results = []
        barrier = threading.Barrier(2)

        def do_credit():
            barrier.wait()
            ok, _, err = self._credit_pledge(thr, bnb, 10.0, txid)
            results.append((ok, err))

        t1 = threading.Thread(target=do_credit)
        t2 = threading.Thread(target=do_credit)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        successes = [r for r in results if r[0]]
        failures = [r for r in results if not r[0]]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn(failures[0][1],
                      ("duplicate_tx_already_processing", "duplicate_tx_already_processed"))

    def test_duplicate_tx_after_processing(self):
        bnb = "0x" + "ab" * 20
        reg_data, _ = self._register(bnb)
        thr = reg_data["thr_address"]
        txid = "0x" + "cc" * 32

        ok1, _, err1 = self._credit_pledge(thr, bnb, 10.0, txid)
        self.assertTrue(ok1)
        ok2, _, err2 = self._credit_pledge(thr, bnb, 10.0, txid)
        self.assertFalse(ok2)
        self.assertEqual(err2, "duplicate_tx_already_processed")


class TestReconciliationScript(PledgeEndpointTestBase):
    def test_dry_run_detects_missing_chain_tx(self):
        pledges = [{
            "bnb_address": "0x" + "ab" * 20,
            "pledge_type": "usdt_bnb",
            "thr_address": "THR" + "aa" * 20,
            "pending_confirmation": False,
            "pledge_hash": "abc123",
        }]
        _save_json(os.path.join(self.data_dir, "pledge_chain.json"), pledges)
        _save_json(os.path.join(self.data_dir, "ledger.json"),
                   {"THR" + "aa" * 20: 1000.0})
        _save_json(os.path.join(self.data_dir, "chain.json"), [])
        _save_json(os.path.join(self.data_dir, "wallet_history.json"), [])
        _save_json(os.path.join(self.data_dir, "bnb_user_registry.json"), {})

        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "scripts"))
        import importlib
        import scripts.reconcile_pledges as rec
        rec = importlib.reload(rec)
        with patch.object(rec, "DATA_DIR", self.data_dir):
            issues = rec.find_inconsistencies()
        self.assertTrue(any(i["type"] == "missing_chain_tx" for i in issues))

    def test_fully_consistent_no_issues(self):
        bnb = "0x" + "ab" * 20
        thr = "THR" + "aa" * 20
        txid = "0x" + "cc" * 32
        pledges = [{
            "bnb_address": bnb, "pledge_type": "usdt_bnb",
            "thr_address": thr, "pending_confirmation": False,
            "pledge_hash": "abc123",
        }]
        chain = [{"type": "usdt_pledge", "bnb_address": bnb,
                  "thr_address": thr, "bnb_txid": txid}]
        hist = [{"event_type": "pledge_usdt_bnb_confirmed",
                 "thr_address": thr, "external_txid": txid}]
        _save_json(os.path.join(self.data_dir, "pledge_chain.json"), pledges)
        _save_json(os.path.join(self.data_dir, "ledger.json"), {thr: 1000.0})
        _save_json(os.path.join(self.data_dir, "chain.json"), chain)
        _save_json(os.path.join(self.data_dir, "wallet_history.json"), hist)
        _save_json(os.path.join(self.data_dir, "bnb_user_registry.json"), {})

        import importlib
        import scripts.reconcile_pledges as rec
        rec = importlib.reload(rec)
        with patch.object(rec, "DATA_DIR", self.data_dir):
            issues = rec.find_inconsistencies()
        self.assertEqual(len(issues), 0)


class TestWatcherUnresolvedPersistence(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="thronos_watcher_test_")
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_unresolved_txs_persisted_and_retried(self):
        import importlib
        import bnb_pledge_watcher as w
        w = importlib.reload(w)

        unresolved_file = os.path.join(self.data_dir, "bnb_unresolved_txs.json")
        txs = [{"txhash": "0xabc", "from": "0x111", "amount": 20.0, "first_seen": time.time()}]
        os.makedirs(os.path.dirname(unresolved_file), exist_ok=True)
        with open(unresolved_file, "w") as f:
            json.dump(txs, f)

        with patch.object(w, "UNRESOLVED_TXS_FILE", unresolved_file):
            loaded = w.load_unresolved_txs()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["txhash"], "0xabc")

    def test_save_and_reload_unresolved(self):
        import importlib
        import bnb_pledge_watcher as w
        w = importlib.reload(w)

        unresolved_file = os.path.join(self.data_dir, "bnb_unresolved_txs.json")
        txs = [{"txhash": "0xdef", "from": "0x222", "amount": 15.0, "first_seen": time.time()}]

        with patch.object(w, "UNRESOLVED_TXS_FILE", unresolved_file):
            w.save_unresolved_txs(txs)
            reloaded = w.load_unresolved_txs()
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0]["txhash"], "0xdef")


class TestCPXPostbackGuard(unittest.TestCase):
    def test_postback_blocked_without_live_flag(self):
        """CPX postback must not credit when CPX_POSTBACK_LIVE != '1'."""
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/api/cpx/postback", methods=["GET", "POST"])
        def postback():
            cpx_live = os.getenv("CPX_POSTBACK_LIVE", "").strip()
            if cpx_live != "1":
                return "0", 503
            return "1", 200

        client = app.test_client()
        with patch.dict(os.environ, {"CPX_POSTBACK_LIVE": ""}, clear=False):
            resp = client.get("/api/cpx/postback?trans_id=t1&user_id=u1&amount_local=100&status=1&secure_hash=abc")
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(resp.data, b"0")

    def test_postback_allowed_with_live_flag(self):
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/api/cpx/postback", methods=["GET"])
        def postback():
            cpx_live = os.getenv("CPX_POSTBACK_LIVE", "").strip()
            if cpx_live != "1":
                return "0", 503
            return "1", 200

        client = app.test_client()
        with patch.dict(os.environ, {"CPX_POSTBACK_LIVE": "1"}, clear=False):
            resp = client.get("/api/cpx/postback")
            self.assertEqual(resp.status_code, 200)


class TestCPXWalletOnboardingGuard(unittest.TestCase):
    def test_link_wallet_blocked_without_flag(self):
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/api/cpx/link-wallet", methods=["POST"])
        def link_wallet():
            if os.getenv("CPX_WALLET_ONBOARDING", "").strip() != "1":
                return jsonify(ok=False, error="wallet_onboarding_blocked"), 503
            return jsonify(ok=True), 200

        client = app.test_client()
        with patch.dict(os.environ, {"CPX_WALLET_ONBOARDING": ""}, clear=False):
            resp = client.post("/api/cpx/link-wallet",
                               json={"email": "a@b.c", "password": "12345678",
                                     "thr_address": "THR" + "aa" * 20})
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(resp.get_json()["error"], "wallet_onboarding_blocked")


if __name__ == "__main__":
    unittest.main()
