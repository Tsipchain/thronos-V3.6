"""
Settlement integration tests — proves real THR wallet balance decrease
and real Pythia pool position increase through the escrow flow.

These tests import server.py (for the authoritative ledger functions)
and exercise the full path:
  signed intent → secp256k1 verification → wallet debit → pool credit
  → escrow record with settlement_status='settled'
"""

import hashlib
import json
import os
import sys
import tempfile
import time

import pytest

os.environ.setdefault("EARN_DB_PATH", ":memory:")
os.environ["POOL_TEST_MODE"] = "1"

_SYSTEM_THR_ADDR = "THR" + "00" * 20
_AI_AGENT_ADDR = "THR" + "11" * 20

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils
from cryptography.hazmat.primitives import hashes
from decimal import Decimal

from services.earn_account import EarnAccountStore, EarnError
from services.wallet_settlement_adapter import (
    WalletSettlementAdapter,
    WalletInsufficientBalance,
    PoolCreditFailed,
)

_TEST_KEY = "test-settlement-integration-key-abcdef0123"


def _generate_wallet_keypair():
    private_key = ec.generate_private_key(ec.SECP256K1())
    pub_numbers = private_key.public_key().public_numbers()
    x = pub_numbers.x.to_bytes(32, "big")
    y = pub_numbers.y.to_bytes(32, "big")
    prefix = b"\x02" if y[-1] % 2 == 0 else b"\x03"
    compressed_hex = (prefix + x).hex()
    return private_key, compressed_hex


def _sign_intent(private_key, intent: dict) -> str:
    signed = {
        "action": str(intent["action"]),
        "amount": str(intent["amount"]),
        "campaign_id": str(intent["campaign_id"]),
        "intent_id": str(intent["intent_id"]),
        "nonce": str(intent["nonce"]),
    }
    if intent.get("wallet_address"):
        signed["wallet_address"] = str(intent["wallet_address"])
    message = json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(message).digest()
    sig = private_key.sign(
        digest, ec.ECDSA(ec_utils.Prehashed(hashes.SHA256())),
    )
    r, s = ec_utils.decode_dss_signature(sig)
    return r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex()


_PRIVKEY, _PUBKEY = _generate_wallet_keypair()
_WALLET_ADDR = "THR" + "AB" * 20


@pytest.fixture()
def server_module():
    import server
    return server


@pytest.fixture()
def data_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture()
def settlement_env(server_module, data_dir):
    """Set up isolated ledger files for settlement testing."""
    originals = {
        attr: getattr(server_module, attr)
        for attr in (
            "LEDGER_FILE", "CHAIN_FILE", "POOL_LIQUIDITY_LEDGER_FILE",
            "POOL_POSITIONS_FILE", "PYTHIA_SYSTEM_THR_ADDRESS",
            "AI_WALLET_ADDRESS", "TX_LOG_FILE", "WALLET_HISTORY_FILE",
        )
    }

    server_module.LEDGER_FILE = os.path.join(data_dir, "ledger.json")
    server_module.CHAIN_FILE = os.path.join(data_dir, "phantom_tx_chain.json")
    server_module.POOL_LIQUIDITY_LEDGER_FILE = os.path.join(data_dir, "pool_liquidity_ledger.json")
    server_module.POOL_POSITIONS_FILE = os.path.join(data_dir, "pool_positions.json")
    server_module.TX_LOG_FILE = os.path.join(data_dir, "tx_log.json")
    server_module.WALLET_HISTORY_FILE = os.path.join(data_dir, "wallet_history.json")
    server_module.PYTHIA_SYSTEM_THR_ADDRESS = _SYSTEM_THR_ADDR
    server_module.AI_WALLET_ADDRESS = _AI_AGENT_ADDR

    os.makedirs(data_dir, exist_ok=True)

    server_module.save_json(server_module.LEDGER_FILE, {
        _WALLET_ADDR: 1000.0,
        _SYSTEM_THR_ADDR: 0.0,
        _AI_AGENT_ADDR: 0.0,
    })
    server_module.save_json(server_module.CHAIN_FILE, [])
    server_module.save_json(server_module.TX_LOG_FILE, [])
    server_module.save_json(server_module.WALLET_HISTORY_FILE, [])
    server_module.save_json(server_module.POOL_LIQUIDITY_LEDGER_FILE, {})
    server_module.save_json(server_module.POOL_POSITIONS_FILE, {})

    yield server_module

    for attr, val in originals.items():
        setattr(server_module, attr, val)


@pytest.fixture()
def store_with_adapter(settlement_env):
    adapter = WalletSettlementAdapter(pool_id="bsc-usdt")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = EarnAccountStore(path, _TEST_KEY, settlement_adapter=adapter)
    adv = s.register("settle-test@example.com", "SecurePass123!")
    uid = adv["earn_user_id"]
    challenge = s.wallet_link_challenge(uid, _WALLET_ADDR)
    s.complete_wallet_link(
        challenge_id=challenge["challenge_id"],
        earn_user_id=uid,
        wallet_address=_WALLET_ADDR,
        public_key=_PUBKEY,
    )
    camp = s.create_campaign(
        advertiser_id=uid,
        name="Settlement Integration Campaign",
        campaign_type="cpm",
        bid_amount="1.000000",
    )
    yield {
        "store": s,
        "uid": uid,
        "campaign_id": camp["campaign_id"],
        "server": settlement_env,
    }
    os.unlink(path)


def _execute_deposit(ctx, amount_str, private_key=None):
    if private_key is None:
        private_key = _PRIVKEY
    store = ctx["store"]
    intent = store.escrow_create_intent(
        ctx["uid"], ctx["campaign_id"], "deposit", amount_str,
    )
    sig = _sign_intent(private_key, intent)
    return store.escrow_execute(
        intent["intent_id"], ctx["uid"],
        intent["nonce"], wallet_signature=sig,
    )


class TestRealSettlement:
    """Prove that real wallet balances decrease and pool positions increase."""

    # 1. Successful wallet debit + Pythia pool credit
    def test_wallet_debited_and_pool_credited(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]

        bal_before = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])
        pool_pos_before = srv._load_pool_positions().get(_WALLET_ADDR, {}).get("bsc-usdt")

        result = _execute_deposit(ctx, "50.000000")

        assert result["settlement_status"] == "settled"
        assert result["wallet_tx_id"] is not None
        assert result["wallet_tx_id"].startswith("TX-")
        assert result["pool_receipt_id"] is not None
        assert result["pool_receipt_id"].startswith("POOL-")
        assert result["pool_position_id"] == f"{_WALLET_ADDR}:bsc-usdt"

        ledger_after = srv.load_json(srv.LEDGER_FILE, {})
        bal_after = float(ledger_after[_WALLET_ADDR])
        assert bal_after < bal_before
        deducted = bal_before - bal_after
        assert deducted >= 50.0

        positions = srv._load_pool_positions()
        pos = positions[_WALLET_ADDR]["bsc-usdt"]
        assert pos["thr_side_balance"] >= 50.0
        assert pos["lp_position_balance"] >= 50.0

        system_bal = float(ledger_after.get(srv.PYTHIA_SYSTEM_THR_ADDRESS, 0))
        assert system_bal >= 50.0

        chain = srv.load_json(srv.CHAIN_FILE, [])
        tx_ids = [t["tx_id"] for t in chain]
        assert result["wallet_tx_id"] in tx_ids

    # 2. Insufficient THR balance
    def test_insufficient_thr_balance(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]

        ledger = srv.load_json(srv.LEDGER_FILE, {})
        ledger[_WALLET_ADDR] = 0.001
        srv.save_json(srv.LEDGER_FILE, ledger)

        with pytest.raises(EarnError, match="insufficient_thr_balance"):
            _execute_deposit(ctx, "100.000000")

        ledger_after = srv.load_json(srv.LEDGER_FILE, {})
        assert float(ledger_after[_WALLET_ADDR]) == 0.001

    # 3. Invalid signature rejected (no wallet or pool changes)
    def test_invalid_sig_no_settlement(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]

        bal_before = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])

        intent = ctx["store"].escrow_create_intent(
            ctx["uid"], ctx["campaign_id"], "deposit", "10.000000",
        )
        bad_sig = "aa" * 64
        with pytest.raises(EarnError, match="invalid_wallet_signature"):
            ctx["store"].escrow_execute(
                intent["intent_id"], ctx["uid"],
                intent["nonce"], wallet_signature=bad_sig,
            )

        bal_after = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])
        assert bal_after == bal_before

    # 4. Nonce replay rejected
    def test_nonce_replay_no_double_debit(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]

        intent = ctx["store"].escrow_create_intent(
            ctx["uid"], ctx["campaign_id"], "deposit", "20.000000",
        )
        sig = _sign_intent(_PRIVKEY, intent)
        ctx["store"].escrow_execute(
            intent["intent_id"], ctx["uid"],
            intent["nonce"], wallet_signature=sig,
        )

        bal_after_first = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])

        with pytest.raises(EarnError, match="invalid_or_expired_intent"):
            ctx["store"].escrow_execute(
                intent["intent_id"], ctx["uid"],
                intent["nonce"], wallet_signature=sig,
            )

        bal_after_replay = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])
        assert bal_after_replay == bal_after_first

    # 5. Duplicate idempotency key rejected
    def test_duplicate_idempotency_no_double_debit(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]
        store = ctx["store"]

        intent1 = store.escrow_create_intent(
            ctx["uid"], ctx["campaign_id"], "deposit", "15.000000",
        )
        sig1 = _sign_intent(_PRIVKEY, intent1)
        result1 = store.escrow_execute(
            intent1["intent_id"], ctx["uid"],
            intent1["nonce"], wallet_signature=sig1,
        )
        idem_key = result1["idempotency_key"]
        bal_after_first = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])

        import secrets as _sec
        with store._tx() as con:
            nonce2 = _sec.token_urlsafe(24)
            iid2 = "esci_" + _sec.token_urlsafe(18)
            now = int(time.time())
            con.execute(
                """INSERT INTO earn_escrow_intents
                   (intent_id, earn_user_id, campaign_id, action,
                    amount, nonce, idempotency_key, wallet_address,
                    requires_wallet_sig, expires_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
                (iid2, ctx["uid"], ctx["campaign_id"], "deposit",
                 "15.000000", nonce2, idem_key, _WALLET_ADDR,
                 now + 300, now),
            )
        dup_intent = {
            "intent_id": iid2, "campaign_id": ctx["campaign_id"],
            "action": "deposit", "amount": "15.000000",
            "nonce": nonce2, "wallet_address": _WALLET_ADDR,
        }
        sig2 = _sign_intent(_PRIVKEY, dup_intent)
        with pytest.raises(EarnError, match="duplicate_intent"):
            store.escrow_execute(iid2, ctx["uid"], nonce2, wallet_signature=sig2)

        bal_after_dup = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])
        assert bal_after_dup == bal_after_first

    # 6. Pool credit failure rolls back wallet debit
    def test_pool_credit_failure_reverses_wallet_debit(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]
        store = ctx["store"]

        bal_before = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])

        original_save = srv._save_pool_ledger
        call_count = [0]

        def failing_save(ledger):
            call_count[0] += 1
            raise RuntimeError("simulated pool ledger write failure")

        srv._save_pool_ledger = failing_save
        try:
            with pytest.raises(EarnError, match="pool_credit_failed"):
                _execute_deposit(ctx, "30.000000")
        finally:
            srv._save_pool_ledger = original_save

        bal_after = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])
        # The principal (30 THR) is restored by the reversal.
        # The network fee (0.5% = 0.15 THR) is non-refundable — it was
        # already split (50% burned, 50% to AI agent wallet).
        fee = 30.0 * 0.005
        assert abs(bal_after - (bal_before - fee)) < 0.01

        chain = srv.load_json(srv.CHAIN_FILE, [])
        reversals = [t for t in chain if t.get("type") == "reversal"]
        assert len(reversals) >= 1
        assert reversals[-1]["amount"] == 30.0

    # 7. Wallet debit failure leaves pool and escrow unchanged
    def test_wallet_debit_failure_leaves_all_unchanged(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]

        ledger = srv.load_json(srv.LEDGER_FILE, {})
        ledger[_WALLET_ADDR] = 0.0001
        srv.save_json(srv.LEDGER_FILE, ledger)

        positions_before = srv._load_pool_positions()
        escrow_bal_before = ctx["store"].escrow_balance(ctx["campaign_id"])

        with pytest.raises(EarnError, match="insufficient_thr_balance"):
            _execute_deposit(ctx, "500.000000")

        positions_after = srv._load_pool_positions()
        assert positions_after == positions_before

        escrow_bal_after = ctx["store"].escrow_balance(ctx["campaign_id"])
        assert escrow_bal_after == escrow_bal_before

    # 8. Wrong wallet address rejected — no wallet or pool changes
    def test_wrong_wallet_no_settlement(self, store_with_adapter):
        ctx = store_with_adapter
        srv = ctx["server"]
        store = ctx["store"]

        bal_before = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])

        intent = store.escrow_create_intent(
            ctx["uid"], ctx["campaign_id"], "deposit", "10.000000",
        )
        wrong_wallet = "THR" + "FF" * 20
        with store._tx() as con:
            con.execute(
                "UPDATE earn_escrow_intents SET wallet_address = ? WHERE intent_id = ?",
                (wrong_wallet, intent["intent_id"]),
            )
        intent["wallet_address"] = wrong_wallet
        sig = _sign_intent(_PRIVKEY, intent)
        with pytest.raises(EarnError, match="wallet_address_mismatch"):
            store.escrow_execute(
                intent["intent_id"], ctx["uid"],
                intent["nonce"], wallet_signature=sig,
            )

        bal_after = float(srv.load_json(srv.LEDGER_FILE, {})[_WALLET_ADDR])
        assert bal_after == bal_before
