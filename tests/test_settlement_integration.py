"""Containment tests for the deprecated THR ad-settlement adapter.

Campaign budgets are denominated in THC and use the authoritative Earn
reservation ledger. A configured legacy adapter must therefore fail closed;
it may not debit THR or create a Pythia liquidity position for an ad budget.
"""

import hashlib
import json
import os
import sys
import tempfile

import pytest

os.environ.setdefault("EARN_DB_PATH", ":memory:")
os.environ.setdefault(
    "EDU_DB_PATH", os.path.join(tempfile.gettempdir(), "thronos-test-l2e.db"),
)
os.environ["POOL_TEST_MODE"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils

from services.earn_account import EarnAccountStore, EarnError
from services.wallet_settlement_adapter import WalletSettlementAdapter


_SYSTEM_THR_ADDR = "THR" + "00" * 20
_AI_AGENT_ADDR = "THR" + "11" * 20
_WALLET_ADDR = "THR" + "AB" * 20
_TEST_KEY = "test-settlement-integration-key-abcdef0123"


def _generate_wallet_keypair():
    private_key = ec.generate_private_key(ec.SECP256K1())
    pub_numbers = private_key.public_key().public_numbers()
    x = pub_numbers.x.to_bytes(32, "big")
    y = pub_numbers.y.to_bytes(32, "big")
    prefix = b"\x02" if y[-1] % 2 == 0 else b"\x03"
    return private_key, (prefix + x).hex()


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
    signature = private_key.sign(
        digest, ec.ECDSA(ec_utils.Prehashed(hashes.SHA256())),
    )
    r, s = ec_utils.decode_dss_signature(signature)
    return r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex()


_PRIVKEY, _PUBKEY = _generate_wallet_keypair()


@pytest.fixture()
def settlement_env(tmp_path):
    import server

    attrs = (
        "LEDGER_FILE", "CHAIN_FILE", "POOL_LIQUIDITY_LEDGER_FILE",
        "POOL_POSITIONS_FILE", "PYTHIA_SYSTEM_THR_ADDRESS",
        "AI_WALLET_ADDRESS", "TX_LOG_FILE", "WALLET_HISTORY_FILE",
    )
    originals = {attr: getattr(server, attr) for attr in attrs}
    server.LEDGER_FILE = str(tmp_path / "ledger.json")
    server.CHAIN_FILE = str(tmp_path / "phantom_tx_chain.json")
    server.POOL_LIQUIDITY_LEDGER_FILE = str(tmp_path / "pool_liquidity_ledger.json")
    server.POOL_POSITIONS_FILE = str(tmp_path / "pool_positions.json")
    server.TX_LOG_FILE = str(tmp_path / "tx_log.json")
    server.WALLET_HISTORY_FILE = str(tmp_path / "wallet_history.json")
    server.PYTHIA_SYSTEM_THR_ADDRESS = _SYSTEM_THR_ADDR
    server.AI_WALLET_ADDRESS = _AI_AGENT_ADDR
    server.save_json(server.LEDGER_FILE, {
        _WALLET_ADDR: 1000.0,
        _SYSTEM_THR_ADDR: 0.0,
        _AI_AGENT_ADDR: 0.0,
    })
    server.save_json(server.CHAIN_FILE, [])
    server.save_json(server.TX_LOG_FILE, [])
    server.save_json(server.WALLET_HISTORY_FILE, [])
    server.save_json(server.POOL_LIQUIDITY_LEDGER_FILE, {})
    server.save_json(server.POOL_POSITIONS_FILE, {})
    yield server
    for attr, value in originals.items():
        setattr(server, attr, value)


@pytest.fixture()
def store_with_adapter(settlement_env, tmp_path):
    store = EarnAccountStore(
        str(tmp_path / "earn.db"),
        _TEST_KEY,
        settlement_adapter=WalletSettlementAdapter(pool_id="bsc-usdt"),
    )
    advertiser = store.register("settle-test@example.com", "SecurePass123!")
    user_id = advertiser["earn_user_id"]
    challenge = store.wallet_link_challenge(user_id, _WALLET_ADDR)
    store.complete_wallet_link(
        challenge_id=challenge["challenge_id"],
        earn_user_id=user_id,
        wallet_address=_WALLET_ADDR,
        public_key=_PUBKEY,
    )
    campaign = store.create_campaign(
        advertiser_id=user_id,
        name="Settlement Boundary Campaign",
        campaign_type="cpm",
        bid_amount="1.000000",
    )
    return {
        "store": store,
        "uid": user_id,
        "campaign_id": campaign["campaign_id"],
        "server": settlement_env,
    }


def _new_signed_intent(context, amount="50.000000"):
    intent = context["store"].escrow_create_intent(
        context["uid"], context["campaign_id"], "deposit", amount,
    )
    return intent, _sign_intent(_PRIVKEY, intent)


def _snapshot(context):
    server = context["server"]
    return {
        "ledger": server.load_json(server.LEDGER_FILE, {}),
        "chain": server.load_json(server.CHAIN_FILE, []),
        "pool": server.load_json(server.POOL_LIQUIDITY_LEDGER_FILE, {}),
        "positions": server.load_json(server.POOL_POSITIONS_FILE, {}),
        "escrow": context["store"].escrow_balance(context["campaign_id"]),
    }


class TestLegacySettlementContainment:

    def test_adapter_fails_closed_without_asset_mutation(self, store_with_adapter):
        before = _snapshot(store_with_adapter)
        intent, signature = _new_signed_intent(store_with_adapter)
        with pytest.raises(EarnError, match="legacy_thr_ad_settlement_disabled"):
            store_with_adapter["store"].escrow_execute(
                intent["intent_id"], store_with_adapter["uid"],
                intent["nonce"], wallet_signature=signature,
            )
        assert _snapshot(store_with_adapter) == before

    def test_failed_boundary_check_is_retry_safe(self, store_with_adapter):
        intent, signature = _new_signed_intent(store_with_adapter, "20.000000")
        for _ in range(2):
            with pytest.raises(EarnError, match="legacy_thr_ad_settlement_disabled"):
                store_with_adapter["store"].escrow_execute(
                    intent["intent_id"], store_with_adapter["uid"],
                    intent["nonce"], wallet_signature=signature,
                )
        assert _snapshot(store_with_adapter)["escrow"] == "0.000000"

    def test_invalid_signature_fails_before_boundary(self, store_with_adapter):
        before = _snapshot(store_with_adapter)
        intent, _ = _new_signed_intent(store_with_adapter, "10.000000")
        with pytest.raises(EarnError, match="invalid_wallet_signature"):
            store_with_adapter["store"].escrow_execute(
                intent["intent_id"], store_with_adapter["uid"],
                intent["nonce"], wallet_signature="aa" * 64,
            )
        assert _snapshot(store_with_adapter) == before

    def test_wallet_mismatch_fails_before_boundary(self, store_with_adapter):
        context = store_with_adapter
        before = _snapshot(context)
        intent = context["store"].escrow_create_intent(
            context["uid"], context["campaign_id"], "deposit", "10.000000",
        )
        wrong_wallet = "THR" + "FF" * 20
        with context["store"]._tx() as connection:
            connection.execute(
                "UPDATE earn_escrow_intents SET wallet_address=? WHERE intent_id=?",
                (wrong_wallet, intent["intent_id"]),
            )
        intent["wallet_address"] = wrong_wallet
        signature = _sign_intent(_PRIVKEY, intent)
        with pytest.raises(EarnError, match="wallet_address_mismatch"):
            context["store"].escrow_execute(
                intent["intent_id"], context["uid"],
                intent["nonce"], wallet_signature=signature,
            )
        assert _snapshot(context) == before
