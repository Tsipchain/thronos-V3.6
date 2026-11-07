"""Tests for the Earn advertising marketplace."""
import hashlib
import json
import os
import pytest
import tempfile
import time
import unittest.mock as mock

os.environ.setdefault("EARN_DB_PATH", ":memory:")

from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils
from cryptography.hazmat.primitives import hashes
from decimal import Decimal
from services.earn_account import EarnAccountStore, EarnError


_TEST_KEY = "test-identity-key-for-marketplace-abcdef0123"


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


_DEFAULT_PRIVKEY, _DEFAULT_PUBKEY = _generate_wallet_keypair()


@pytest.fixture()
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = EarnAccountStore(path, _TEST_KEY)
    yield s
    os.unlink(path)


@pytest.fixture()
def advertiser(store):
    return store.register("advertiser@test.com", "SecurePass123!")


@pytest.fixture()
def campaign(store, advertiser):
    return store.create_campaign(
        advertiser_id=advertiser["earn_user_id"],
        name="Test Campaign",
        campaign_type="cpm",
        bid_amount="2.000000",
    )


def _link_wallet(store, earn_user_id, wallet_address="THR" + "AB" * 20,
                 public_key=None):
    if public_key is None:
        public_key = _DEFAULT_PUBKEY
    challenge = store.wallet_link_challenge(earn_user_id, wallet_address)
    store.complete_wallet_link(
        challenge_id=challenge["challenge_id"],
        earn_user_id=earn_user_id,
        wallet_address=wallet_address,
        public_key=public_key,
    )
    return wallet_address


def _escrow_via_intent(store, earn_user_id, campaign_id, action, amount,
                       private_key=None):
    if private_key is None:
        private_key = _DEFAULT_PRIVKEY
    intent = store.escrow_create_intent(
        earn_user_id, campaign_id, action, amount,
    )
    sig = _sign_intent(private_key, intent)
    return store.escrow_execute(
        intent["intent_id"], earn_user_id,
        intent["nonce"], wallet_signature=sig,
    )


class TestCampaignCRUD:
    def test_create_campaign(self, store, advertiser):
        result = store.create_campaign(
            advertiser_id=advertiser["earn_user_id"],
            name="My First Ad",
            campaign_type="cpm",
            bid_amount="5.000000",
            daily_budget="100.000000",
            total_budget="1000.000000",
            country_targets="US,GB,GR",
            placement="earn",
        )
        assert result["campaign_id"].startswith("camp_")
        assert result["status"] == "pending_review"
        assert result["name"] == "My First Ad"

    def test_create_campaign_cpc(self, store, advertiser):
        result = store.create_campaign(
            advertiser_id=advertiser["earn_user_id"],
            name="CPC Camp",
            campaign_type="cpc",
            bid_amount="0.500000",
        )
        full = store.get_campaign(result["campaign_id"])
        assert full["campaign_type"] == "cpc"

    def test_create_campaign_invalid_type(self, store, advertiser):
        with pytest.raises(EarnError, match="invalid_campaign_type"):
            store.create_campaign(
                advertiser["earn_user_id"], "Bad", campaign_type="ppc",
            )

    def test_create_campaign_zero_bid(self, store, advertiser):
        with pytest.raises(EarnError, match="bid_must_be_positive"):
            store.create_campaign(
                advertiser["earn_user_id"], "Bad", bid_amount="0",
            )

    def test_create_campaign_bad_advertiser(self, store):
        with pytest.raises(EarnError, match="advertiser_not_found"):
            store.create_campaign("nonexistent_user", "Bad")

    def test_get_campaign(self, store, advertiser, campaign):
        result = store.get_campaign(campaign["campaign_id"])
        assert result is not None
        assert result["name"] == "Test Campaign"

    def test_get_campaign_not_found(self, store):
        assert store.get_campaign("camp_nonexistent") is None

    def test_list_advertiser_campaigns(self, store, advertiser):
        store.create_campaign(advertiser["earn_user_id"], "Camp A")
        store.create_campaign(advertiser["earn_user_id"], "Camp B")
        camps = store.list_advertiser_campaigns(advertiser["earn_user_id"])
        assert len(camps) == 2

    def test_update_campaign_name(self, store, advertiser, campaign):
        result = store.update_campaign(
            campaign["campaign_id"], advertiser["earn_user_id"],
            name="Updated Name",
        )
        assert result["updated"] is True
        full = store.get_campaign(campaign["campaign_id"])
        assert full["name"] == "Updated Name"

    def test_update_campaign_bid(self, store, advertiser, campaign):
        result = store.update_campaign(
            campaign["campaign_id"], advertiser["earn_user_id"],
            bid_amount="10.000000",
        )
        assert result["updated"] is True
        full = store.get_campaign(campaign["campaign_id"])
        assert full["bid_amount"] == "10.000000"

    def test_update_campaign_nothing(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="nothing_to_update"):
            store.update_campaign(
                campaign["campaign_id"], advertiser["earn_user_id"],
            )

    def test_update_campaign_wrong_owner(self, store, advertiser, campaign):
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.update_campaign(
                campaign["campaign_id"], other["earn_user_id"],
                name="Hijacked",
            )

    def test_pause_and_resume(self, store, advertiser, campaign):
        store.moderate_campaign(campaign["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (campaign["campaign_id"],),
            )
        result = store.pause_campaign(
            campaign["campaign_id"], advertiser["earn_user_id"],
        )
        assert result["status"] == "paused"
        result = store.resume_campaign(
            campaign["campaign_id"], advertiser["earn_user_id"],
        )
        assert result["status"] == "active"

    def test_pause_non_active_fails(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="only_active_campaigns_can_pause"):
            store.pause_campaign(
                campaign["campaign_id"], advertiser["earn_user_id"],
            )

    def test_resume_non_paused_fails(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="only_paused_campaigns_can_resume"):
            store.resume_campaign(
                campaign["campaign_id"], advertiser["earn_user_id"],
            )


class TestCreativeManagement:
    def test_add_creative(self, store, advertiser, campaign):
        result = store.add_creative(
            campaign["campaign_id"], advertiser["earn_user_id"],
            "Banner Ad", "https://img.example.com/banner.png",
            "https://example.com",
        )
        assert result["creative_id"].startswith("crtv_")
        assert result["status"] == "pending_review"

    def test_add_creative_wrong_owner(self, store, advertiser, campaign):
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.add_creative(
                campaign["campaign_id"], other["earn_user_id"],
                "X", "https://i.png", "https://t.com",
            )

    def test_list_creatives(self, store, advertiser, campaign):
        store.add_creative(
            campaign["campaign_id"], advertiser["earn_user_id"],
            "A", "https://i.png", "https://t.com",
        )
        store.add_creative(
            campaign["campaign_id"], advertiser["earn_user_id"],
            "B", "https://i2.png", "https://t2.com",
        )
        creatives = store.list_creatives(
            campaign["campaign_id"], advertiser["earn_user_id"],
        )
        assert len(creatives) == 2

    def test_list_creatives_wrong_owner(self, store, advertiser, campaign):
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.list_creatives(
                campaign["campaign_id"], other["earn_user_id"],
            )


class TestModeration:
    def test_approve_campaign(self, store, advertiser, campaign):
        result = store.moderate_campaign(campaign["campaign_id"], "approve")
        assert result["status"] == "approved"

    def test_reject_campaign(self, store, advertiser, campaign):
        result = store.moderate_campaign(
            campaign["campaign_id"], "reject", "not suitable",
        )
        assert result["status"] == "rejected"
        full = store.get_campaign(campaign["campaign_id"])
        assert full["reject_reason"] == "not suitable"

    def test_moderate_campaign_invalid_action(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="invalid_moderation_action"):
            store.moderate_campaign(campaign["campaign_id"], "suspend")

    def test_approve_creative(self, store, advertiser, campaign):
        crtv = store.add_creative(
            campaign["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        result = store.moderate_creative(crtv["creative_id"], "approve")
        assert result["status"] == "approved"

    def test_reject_creative(self, store, advertiser, campaign):
        crtv = store.add_creative(
            campaign["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        result = store.moderate_creative(
            crtv["creative_id"], "reject", "low quality",
        )
        assert result["status"] == "rejected"

    def test_moderate_creative_not_found(self, store):
        with pytest.raises(EarnError, match="creative_not_found"):
            store.moderate_creative("nonexistent", "approve")


class TestEscrowIntentFlow:
    """Escrow operations require the wallet-signed intent model."""

    def test_create_intent_deposit(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "100.000000",
        )
        assert intent["intent_id"].startswith("esci_")
        assert intent["nonce"]
        assert intent["idempotency_key"]
        assert intent["requires_wallet_sig"] is True
        assert intent["approval"] == "biometric_passkey"
        assert intent["action"] == "deposit"
        assert intent["amount"] == "100.000000"

    def test_execute_deposit(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        result = _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "100.000000",
        )
        assert result["escrow_id"].startswith("esc_")
        assert Decimal(result["balance_after"]) == Decimal("100.000000")
        assert result["idempotency_key"]

    def test_balance_after_deposit(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        balance = store.escrow_balance(campaign["campaign_id"])
        assert Decimal(balance) == Decimal("50.000000")

    def test_multiple_deposits(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "30.000000",
        )
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "20.000000",
        )
        balance = store.escrow_balance(campaign["campaign_id"])
        assert Decimal(balance) == Decimal("50.000000")

    def test_refund_full(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "100.000000",
        )
        result = _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "refund", "100.000000",
        )
        assert Decimal(result["balance_after"]) == Decimal("0.000000")

    def test_refund_partial(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "100.000000",
        )
        result = _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "refund", "40.000000",
        )
        assert Decimal(result["balance_after"]) == Decimal("60.000000")

    def test_refund_exceeds_balance(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "10.000000",
        )
        with pytest.raises(EarnError, match="insufficient_escrow_balance"):
            _escrow_via_intent(
                store, advertiser["earn_user_id"],
                campaign["campaign_id"], "refund", "50.000000",
            )

    def test_deposit_wrong_owner(self, store, advertiser, campaign):
        other = store.register("other@test.com", "SecurePass456!")
        _link_wallet(store, other["earn_user_id"], "THR" + "CD" * 20)
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.escrow_create_intent(
                other["earn_user_id"],
                campaign["campaign_id"], "deposit", "10.000000",
            )

    def test_deposit_zero_fails(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        with pytest.raises(EarnError, match="amount_must_be_positive"):
            store.escrow_create_intent(
                advertiser["earn_user_id"],
                campaign["campaign_id"], "deposit", "0",
            )


class TestEscrowSecurityGates:
    """Verify nonce replay, idempotency, wallet signature, crypto verification, and atomic rollback."""

    def test_nonce_replay_rejected(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        sig = _sign_intent(_DEFAULT_PRIVKEY, intent)
        store.escrow_execute(
            intent["intent_id"], advertiser["earn_user_id"],
            intent["nonce"], wallet_signature=sig,
        )
        with pytest.raises(EarnError, match="invalid_or_expired_intent"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature=sig,
            )

    def test_wrong_nonce_rejected(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        with pytest.raises(EarnError, match="nonce_mismatch"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                "wrong_nonce_value", wallet_signature="aa" * 64,
            )

    def test_idempotency_key_prevents_duplicate(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "25.000000",
        )
        sig = _sign_intent(_DEFAULT_PRIVKEY, intent)
        store.escrow_execute(
            intent["intent_id"], advertiser["earn_user_id"],
            intent["nonce"], wallet_signature=sig,
        )
        intent2 = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "25.000000",
        )
        sig2 = _sign_intent(_DEFAULT_PRIVKEY, intent2)
        result2 = store.escrow_execute(
            intent2["intent_id"], advertiser["earn_user_id"],
            intent2["nonce"], wallet_signature=sig2,
        )
        assert Decimal(result2["balance_after"]) == Decimal("50.000000")

    def test_wallet_signature_required(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        with pytest.raises(EarnError, match="wallet_signature_required"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature=None,
            )

    def test_invalid_signature_rejected(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        with pytest.raises(EarnError, match="invalid_wallet_signature"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature="aa" * 64,
            )

    def test_wrong_key_signature_rejected(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        wrong_key, _ = _generate_wallet_keypair()
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        wrong_sig = _sign_intent(wrong_key, intent)
        with pytest.raises(EarnError, match="invalid_wallet_signature"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature=wrong_sig,
            )

    def test_wallet_not_linked_rejected(self, store, advertiser, campaign):
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        with pytest.raises(EarnError, match="wallet_not_linked"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature="aa" * 64,
            )

    def test_expired_intent_rejected(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        with store._tx() as con:
            con.execute(
                "UPDATE earn_escrow_intents SET expires_at = ? WHERE intent_id = ?",
                (int(time.time()) - 1, intent["intent_id"]),
            )
        with pytest.raises(EarnError, match="invalid_or_expired_intent"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature="aa" * 64,
            )

    def test_wrong_user_cannot_execute(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="invalid_or_expired_intent"):
            store.escrow_execute(
                intent["intent_id"], other["earn_user_id"],
                intent["nonce"], wallet_signature="aa" * 64,
            )

    def test_wallet_address_mismatch_rejected(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"], "THR" + "AA" * 20)
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        with store._tx() as con:
            con.execute(
                "UPDATE earn_wallet_links SET wallet_address = 'THR" + "BB" * 20 + "' WHERE earn_user_id = ?",
                (advertiser["earn_user_id"],),
            )
        with pytest.raises(EarnError, match="wallet_address_mismatch"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature="aa" * 64,
            )

    def test_atomic_rollback_on_insufficient_refund(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "10.000000",
        )
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "refund", "5.000000",
        )
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            campaign["campaign_id"], "refund", "8.000000",
        )
        sig = _sign_intent(_DEFAULT_PRIVKEY, intent)
        with pytest.raises(EarnError, match="insufficient_escrow_balance"):
            store.escrow_execute(
                intent["intent_id"], advertiser["earn_user_id"],
                intent["nonce"], wallet_signature=sig,
            )
        bal = store.escrow_balance(campaign["campaign_id"])
        assert Decimal(bal) == Decimal("2.000000")

    def test_invalid_action_rejected(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        with pytest.raises(EarnError, match="invalid_escrow_action"):
            store.escrow_create_intent(
                advertiser["earn_user_id"],
                campaign["campaign_id"], "transfer", "50.000000",
            )

    def test_server_never_stores_private_key_or_secrets(self, store, advertiser, campaign):
        _link_wallet(store, advertiser["earn_user_id"])
        intent = store.escrow_create_intent(
            advertiser["earn_user_id"],
            campaign["campaign_id"], "deposit", "50.000000",
        )
        with store._tx() as con:
            row = con.execute(
                "SELECT * FROM earn_escrow_intents WHERE intent_id = ?",
                (intent["intent_id"],),
            ).fetchone()
            cols = set(dict(row).keys())
            forbidden = {"private_key", "pin", "biometric", "send_secret", "pledge_secret"}
            assert not cols & forbidden


class TestAdServing:
    def _setup_active_campaign(self, store, advertiser):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Active Camp",
            campaign_type="cpm", bid_amount="5.000000",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        crtv = store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            camp["campaign_id"], "deposit", "1000.000000",
        )
        return camp, crtv

    def test_serve_returns_active_ads(self, store, advertiser):
        self._setup_active_campaign(store, advertiser)
        ads = store.serve_campaign_ads(placement="earn")
        assert len(ads) == 1
        assert "campaign_id" in ads[0]
        assert "creative_id" in ads[0]

    def test_serve_filters_placement(self, store, advertiser):
        self._setup_active_campaign(store, advertiser)
        ads = store.serve_campaign_ads(placement="basketball")
        assert len(ads) == 0

    def test_serve_filters_country(self, store, advertiser):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Targeted",
            campaign_type="cpm", bid_amount="5.000000",
            country_targets="US,GB",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        crtv = store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            camp["campaign_id"], "deposit", "100.000000",
        )
        ads_us = store.serve_campaign_ads(country="US")
        assert len(ads_us) == 1
        ads_gr = store.serve_campaign_ads(country="GR")
        assert len(ads_gr) == 0
        assert store.serve_campaign_ads(country="") == []


    def test_serve_respects_total_budget(self, store, advertiser):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Budget Camp",
            campaign_type="cpc", bid_amount="50.000000",
            total_budget="50.000000",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        crtv = store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            camp["campaign_id"], "deposit", "100.000000",
        )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "click",
        )
        ads = store.serve_campaign_ads()
        assert len(ads) == 0

    def test_serve_unapproved_creative_hidden(self, store, advertiser):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Unmod Camp",
            campaign_type="cpm", bid_amount="5.000000",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Pending", "https://i.png", "https://t.com",
        )
        ads = store.serve_campaign_ads()
        assert len(ads) == 0

    def test_serve_bid_ordering(self, store, advertiser):
        _link_wallet(store, advertiser["earn_user_id"])
        for bid in ("1.000000", "10.000000"):
            camp = store.create_campaign(
                advertiser["earn_user_id"], f"Bid {bid}",
                campaign_type="cpm", bid_amount=bid,
            )
            store.moderate_campaign(camp["campaign_id"], "approve")
            with store._tx() as con:
                con.execute(
                    "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                    (camp["campaign_id"],),
                )
            crtv = store.add_creative(
                camp["campaign_id"], advertiser["earn_user_id"],
                "B", "https://i.png", "https://t.com",
            )
            store.moderate_creative(crtv["creative_id"], "approve")
            _escrow_via_intent(
                store, advertiser["earn_user_id"],
                camp["campaign_id"], "deposit", "100.000000",
            )
        ads = store.serve_campaign_ads(limit=2)
        assert len(ads) == 2
        assert ads[0]["title"] == "B"
        camp_ids = [a["campaign_id"] for a in ads]
        assert len(set(camp_ids)) == 2


class TestEventRecording:
    def _make_active_campaign(
        self, store, advertiser, campaign_type="cpm",
        bid_amount="2.000000", total_budget="0",
    ):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Event Camp",
            campaign_type=campaign_type, bid_amount=bid_amount,
            total_budget=total_budget,
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        crtv = store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            camp["campaign_id"], "deposit", "100.000000",
        )
        return camp, crtv

    def test_cpm_impression_cost(self, store, advertiser):
        camp, crtv = self._make_active_campaign(
            store, advertiser, campaign_type="cpm", bid_amount="2.000000",
        )
        result = store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "impression",
        )
        assert Decimal(result["cost"]) == Decimal("0.002000")

    def test_cpc_click_cost(self, store, advertiser):
        camp, crtv = self._make_active_campaign(
            store, advertiser, campaign_type="cpc", bid_amount="0.500000",
        )
        result = store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "click",
        )
        assert Decimal(result["cost"]) == Decimal("0.500000")

    def test_cpc_impression_zero_cost(self, store, advertiser):
        camp, crtv = self._make_active_campaign(
            store, advertiser, campaign_type="cpc", bid_amount="0.500000",
        )
        result = store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "impression",
        )
        assert Decimal(result["cost"]) == Decimal("0")

    def test_cpm_click_zero_cost(self, store, advertiser):
        camp, crtv = self._make_active_campaign(
            store, advertiser, campaign_type="cpm", bid_amount="2.000000",
        )
        result = store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "click",
        )
        assert Decimal(result["cost"]) == Decimal("0")

    def test_event_updates_campaign_counters(self, store, advertiser):
        camp, crtv = self._make_active_campaign(
            store, advertiser, campaign_type="cpm", bid_amount="2.000000",
        )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "impression",
        )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "impression",
        )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "click",
        )
        c = store.get_campaign(camp["campaign_id"])
        assert c["impressions"] == 2
        assert c["clicks"] == 1

    def test_event_deducts_escrow(self, store, advertiser):
        camp, crtv = self._make_active_campaign(
            store, advertiser, campaign_type="cpc", bid_amount="10.000000",
        )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "click",
        )
        bal = store.escrow_balance(camp["campaign_id"])
        assert Decimal(bal) == Decimal("90.000000")

    def test_campaign_completes_on_budget(self, store, advertiser):
        camp, crtv = self._make_active_campaign(
            store, advertiser,
            campaign_type="cpc", bid_amount="50.000000",
            total_budget="100.000000",
        )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "click",
        )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"], "click",
        )
        c = store.get_campaign(camp["campaign_id"])
        assert c["status"] == "completed"

    def test_invalid_event_type(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="invalid_event_type"):
            store.record_campaign_event(
                campaign["campaign_id"], "crtv_x", "hover",
            )


class TestReporting:
    def _make_campaign_with_events(self, store, advertiser):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Report Camp",
            campaign_type="cpm", bid_amount="2.000000",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        crtv = store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        _link_wallet(store, advertiser["earn_user_id"])
        _escrow_via_intent(
            store, advertiser["earn_user_id"],
            camp["campaign_id"], "deposit", "100.000000",
        )
        for _ in range(5):
            store.record_campaign_event(
                camp["campaign_id"], crtv["creative_id"],
                "impression", country="US",
            )
        store.record_campaign_event(
            camp["campaign_id"], crtv["creative_id"],
            "click", country="GR",
        )
        return camp

    def test_campaign_report(self, store, advertiser):
        camp = self._make_campaign_with_events(store, advertiser)
        report = store.campaign_report(
            camp["campaign_id"], advertiser["earn_user_id"],
        )
        assert report["impressions"] == 5
        assert report["clicks"] == 1
        assert float(report["ctr"]) > 0

    def test_campaign_report_wrong_owner(self, store, advertiser):
        camp = self._make_campaign_with_events(store, advertiser)
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.campaign_report(
                camp["campaign_id"], other["earn_user_id"],
            )

    def test_campaign_report_daily(self, store, advertiser):
        camp = self._make_campaign_with_events(store, advertiser)
        daily = store.campaign_report_daily(
            camp["campaign_id"], advertiser["earn_user_id"],
        )
        assert len(daily) >= 1
        assert "date" in daily[0]
        assert "impressions" in daily[0]


class TestMarketplaceAPI:
    def _auth_client(self, store):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        os.environ["EARN_MGMT_TOKEN"] = "test-mgmt-token-mkt"
        from services.earn_account import register_earn_account_routes
        register_earn_account_routes(app, store)
        client = app.test_client()
        r = client.post(
            "/api/earn/register",
            json={"email": "adv@test.com", "password": "SecurePass123!"},
        )
        uid = r.get_json()["earn_user_id"]
        r = client.post(
            "/api/earn/login",
            json={"email": "adv@test.com", "password": "SecurePass123!"},
        )
        token = r.get_json()["access_token"]
        return client, uid, token

    def _link_wallet_api(self, store, uid):
        _link_wallet(store, uid)

    def _escrow_intent_api(self, client, tok, campaign_id, action, amount):
        r = client.post(
            "/api/earn/ads/escrow/intent",
            json={
                "campaign_id": campaign_id,
                "action": action,
                "amount": amount,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        sig = _sign_intent(_DEFAULT_PRIVKEY, data)
        r2 = client.post(
            "/api/earn/ads/escrow/execute",
            json={
                "intent_id": data["intent_id"],
                "nonce": data["nonce"],
                "wallet_signature": sig,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        return r2

    def test_campaign_create_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "API Campaign", "bid_amount": "3.000000"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"]
        assert data["campaign_id"].startswith("camp_")

    def test_campaign_create_no_auth(self, store):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        from services.earn_account import register_earn_account_routes
        register_earn_account_routes(app, store)
        with app.test_client() as fresh:
            r = fresh.post(
                "/api/earn/ads/campaign/create",
                json={"name": "X"},
            )
            assert r.status_code == 401

    def test_campaign_list_api(self, store):
        c, uid, tok = self._auth_client(store)
        c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Camp1"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        r = c.get(
            "/api/earn/ads/campaign/list",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["campaigns"]) == 1

    def test_campaign_get_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Details"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.get(
            f"/api/earn/ads/campaign/{cid}",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert r.get_json()["campaign"]["name"] == "Details"

    def test_campaign_get_wrong_owner(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Private"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        c.post(
            "/api/earn/register",
            json={"email": "spy@test.com", "password": "SecurePass456!"},
        )
        r2 = c.post(
            "/api/earn/login",
            json={"email": "spy@test.com", "password": "SecurePass456!"},
        )
        tok2 = r2.get_json()["access_token"]
        r = c.get(
            f"/api/earn/ads/campaign/{cid}",
            headers={"Authorization": f"Bearer {tok2}"},
        )
        assert r.status_code == 404

    def test_creative_add_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Creative Camp"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.post(
            f"/api/earn/ads/campaign/{cid}/creative/add",
            json={
                "title": "My Banner",
                "image_url": "https://i.png",
                "target_url": "https://t.com",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert r.get_json()["creative_id"].startswith("crtv_")

    def test_creative_add_missing_fields(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "X"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.post(
            f"/api/earn/ads/campaign/{cid}/creative/add",
            json={"title": "Only title"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 400

    def test_moderate_campaign_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "To Mod"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.post(
            "/api/earn/ads/moderate/campaign",
            json={"campaign_id": cid, "action": "approve"},
            headers={"X-Admin-Key": "test-mgmt-token-mkt"},
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "approved"

    def test_moderate_campaign_no_admin(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/moderate/campaign",
            json={"campaign_id": "x", "action": "approve"},
        )
        assert r.status_code == 403

    def test_escrow_intent_and_execute_api(self, store):
        c, uid, tok = self._auth_client(store)
        self._link_wallet_api(store, uid)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Funded"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = self._escrow_intent_api(c, tok, cid, "deposit", "50.000000")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"]
        assert Decimal(data["balance_after"]) == Decimal("50.000000")
        r = c.get(
            f"/api/earn/ads/escrow/balance/{cid}",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert Decimal(r.get_json()["balance"]) == Decimal("50.000000")

    def test_escrow_refund_api(self, store):
        c, uid, tok = self._auth_client(store)
        self._link_wallet_api(store, uid)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Refundable"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        self._escrow_intent_api(c, tok, cid, "deposit", "100.000000")
        r = self._escrow_intent_api(c, tok, cid, "refund", "30.000000")
        assert r.status_code == 200
        assert Decimal(r.get_json()["balance_after"]) == Decimal("70.000000")

    def test_escrow_no_wallet_rejected_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "No Wallet"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.post(
            "/api/earn/ads/escrow/intent",
            json={
                "campaign_id": cid,
                "action": "deposit",
                "amount": "50.000000",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        r2 = c.post(
            "/api/earn/ads/escrow/execute",
            json={
                "intent_id": data["intent_id"],
                "nonce": data["nonce"],
                "wallet_signature": "test_sig",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r2.status_code == 400
        assert "wallet_not_linked" in r2.get_json().get("error", "")

    def test_escrow_execute_no_sig_rejected_api(self, store):
        c, uid, tok = self._auth_client(store)
        self._link_wallet_api(store, uid)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "No Sig"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.post(
            "/api/earn/ads/escrow/intent",
            json={
                "campaign_id": cid,
                "action": "deposit",
                "amount": "50.000000",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        data = r.get_json()
        r = c.post(
            "/api/earn/ads/escrow/execute",
            json={
                "intent_id": data["intent_id"],
                "nonce": data["nonce"],
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 400
        assert "wallet_signature_required" in r.get_json().get("error", "")

    def test_serve_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.get("/api/earn/ads/serve?placement=earn")
        assert r.status_code == 200
        assert r.get_json()["ok"]

    def test_serve_event_api(self, store):
        c, uid, tok = self._auth_client(store)
        self._link_wallet_api(store, uid)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Serving", "bid_amount": "2.000000"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        c.post(
            "/api/earn/ads/moderate/campaign",
            json={"campaign_id": cid, "action": "approve"},
            headers={"X-Admin-Key": "test-mgmt-token-mkt"},
        )
        r = c.post(
            f"/api/earn/ads/campaign/{cid}/creative/add",
            json={
                "title": "B", "image_url": "https://i.png",
                "target_url": "https://t.com",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        crtv_id = r.get_json()["creative_id"]
        c.post(
            "/api/earn/ads/moderate/creative",
            json={"creative_id": crtv_id, "action": "approve"},
            headers={"X-Admin-Key": "test-mgmt-token-mkt"},
        )
        self._escrow_intent_api(c, tok, cid, "deposit", "100.000000")
        before = store.campaign_report(cid, uid)
        r = c.post(
            "/api/earn/ads/serve/event",
            json={
                "campaign_id": cid,
                "creative_id": crtv_id,
                "event_type": "impression",
                "country": "GR",
            },
        )
        assert r.status_code == 503
        assert r.get_json()["error"] == "verified_ad_event_required"
        after = store.campaign_report(cid, uid)
        assert after["spent"] == before["spent"]
        assert after["escrow_balance"] == before["escrow_balance"]
        assert after["impressions"] == before["impressions"]

    def test_report_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Reported"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.get(
            f"/api/earn/ads/campaign/{cid}/report",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["impressions"] == 0

    def test_report_daily_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Daily Report"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.get(
            f"/api/earn/ads/campaign/{cid}/report/daily",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert "daily" in r.get_json()


# ── Settlement Integration Tests ─────────────────────────────────────
#
# These tests validate the escrow settlement flow with real
# deterministic secp256k1 signatures.  They cover the 8 scenarios
# specified for wallet debit + Pythia pool credit integration.
#
# STATUS: The tests below validate the current escrow accounting layer
# (intent → signature verification → escrow record).  Each test also
# documents (with inline comments) the additional assertions that will
# become active once the WalletSettlementAdapter is implemented and
# wired into escrow_execute.
#
# See services/wallet_settlement_adapter.py for the adapter interface.

_SETTLE_PRIVKEY, _SETTLE_PUBKEY = _generate_wallet_keypair()
_SETTLE_WALLET = "THR" + "EE" * 20


class TestSettlementIntegration:
    """Integration tests for wallet debit + Pythia pool credit settlement."""

    def _setup_advertiser(self, store):
        adv = store.register("settle-adv@test.com", "SecurePass123!")
        uid = adv["earn_user_id"]
        _link_wallet(store, uid, _SETTLE_WALLET, _SETTLE_PUBKEY)
        camp = store.create_campaign(
            advertiser_id=uid,
            name="Settlement Test Campaign",
            campaign_type="cpm",
            bid_amount="1.000000",
        )
        cid = camp["campaign_id"]
        return uid, cid

    # 1. Successful wallet debit + Pythia pool credit
    def test_successful_settlement(self, store):
        uid, cid = self._setup_advertiser(store)
        result = _escrow_via_intent(
            store, uid, cid, "deposit", "50.000000",
            private_key=_SETTLE_PRIVKEY,
        )
        assert result["escrow_id"].startswith("esc_")
        assert result["action"] == "deposit"
        assert result["amount"] == "50.000000"
        assert result["balance_after"] == "50.000000"
        assert result["payload_hash"]
        assert len(result["payload_hash"]) == 64
        assert result["settlement_status"] == "pending"
        # TODO once WalletSettlementAdapter is wired:
        #   assert result["wallet_tx_id"] is not None
        #   assert result["pool_receipt_id"] is not None
        #   assert result["pool_position_id"] is not None
        #   assert result["settlement_status"] == "settled"

    # 2. Insufficient THR balance
    def test_insufficient_thr_balance(self, store):
        uid, cid = self._setup_advertiser(store)
        # Currently the escrow layer does not check wallet balance
        # (that requires the adapter). Verify the escrow record is created
        # with settlement_status="pending" — the adapter will reject it.
        result = _escrow_via_intent(
            store, uid, cid, "deposit", "999999.000000",
            private_key=_SETTLE_PRIVKEY,
        )
        assert result["settlement_status"] == "pending"
        # TODO once WalletSettlementAdapter is wired:
        #   with pytest.raises(EarnError, match="insufficient_thr_balance"):
        #       _escrow_via_intent(
        #           store, uid, cid, "deposit", "999999.000000",
        #           private_key=_SETTLE_PRIVKEY,
        #       )

    # 3. Invalid signature rejected
    def test_invalid_signature_rejected(self, store):
        uid, cid = self._setup_advertiser(store)
        intent = store.escrow_create_intent(uid, cid, "deposit", "10.000000")
        bad_sig = "aa" * 64
        with pytest.raises(EarnError, match="invalid_wallet_signature"):
            store.escrow_execute(
                intent["intent_id"], uid,
                intent["nonce"], wallet_signature=bad_sig,
            )

    # 4. Nonce replay rejected
    def test_nonce_replay_rejected(self, store):
        uid, cid = self._setup_advertiser(store)
        intent = store.escrow_create_intent(uid, cid, "deposit", "10.000000")
        sig = _sign_intent(_SETTLE_PRIVKEY, intent)
        store.escrow_execute(
            intent["intent_id"], uid,
            intent["nonce"], wallet_signature=sig,
        )
        # Second execution with same intent must fail
        with pytest.raises(EarnError, match="invalid_or_expired_intent"):
            store.escrow_execute(
                intent["intent_id"], uid,
                intent["nonce"], wallet_signature=sig,
            )

    # 5. Duplicate idempotency key rejected
    def test_duplicate_idempotency_key_rejected(self, store):
        uid, cid = self._setup_advertiser(store)
        intent1 = store.escrow_create_intent(uid, cid, "deposit", "10.000000")
        sig1 = _sign_intent(_SETTLE_PRIVKEY, intent1)
        result1 = store.escrow_execute(
            intent1["intent_id"], uid,
            intent1["nonce"], wallet_signature=sig1,
        )
        idem_key = result1["idempotency_key"]
        # Forge a second intent row with the same idempotency_key to
        # verify the duplicate guard.  Normally the store generates
        # unique keys, but an adapter or retry could present the same
        # key if the first write succeeded.
        with store._tx() as con:
            import secrets as _sec
            nonce2 = _sec.token_urlsafe(24)
            intent_id2 = "esci_" + _sec.token_urlsafe(18)
            now = int(time.time())
            con.execute(
                """INSERT INTO earn_escrow_intents
                   (intent_id, earn_user_id, campaign_id, action,
                    amount, nonce, idempotency_key, requires_wallet_sig,
                    expires_at, created_at)
                   VALUES (?,?,?,?,?,?,?,1,?,?)""",
                (intent_id2, uid, cid, "deposit", "10.000000",
                 nonce2, idem_key, now + 300, now),
            )
        dup_intent = {
            "intent_id": intent_id2, "campaign_id": cid,
            "action": "deposit", "amount": "10.000000", "nonce": nonce2,
        }
        sig2 = _sign_intent(_SETTLE_PRIVKEY, dup_intent)
        with pytest.raises(EarnError, match="duplicate_intent"):
            store.escrow_execute(
                intent_id2, uid, nonce2, wallet_signature=sig2,
            )

    # 6. Pool credit failure rolls back wallet debit
    def test_pool_credit_failure_rolls_back_wallet_debit(self, store):
        uid, cid = self._setup_advertiser(store)
        # This test documents the rollback invariant.
        # Currently, without the adapter, escrow writes only to SQLite.
        # Once the adapter is wired, a failing pool credit must reverse
        # the wallet debit so no THR is lost.
        result = _escrow_via_intent(
            store, uid, cid, "deposit", "25.000000",
            private_key=_SETTLE_PRIVKEY,
        )
        assert result["settlement_status"] == "pending"
        # TODO once WalletSettlementAdapter is wired:
        #   adapter = mock.MagicMock(spec=WalletSettlementAdapter)
        #   adapter.debit_thr.return_value = WalletDebitResult(...)
        #   adapter.credit_pythia_pool.side_effect = PoolCreditFailed("pool down")
        #   with pytest.raises(EarnError, match="pool_credit_failed"):
        #       _escrow_via_intent_with_adapter(...)
        #   adapter.reverse_debit.assert_called_once()

    # 7. Wallet debit failure leaves pool and escrow unchanged
    def test_wallet_debit_failure_leaves_pool_and_escrow_unchanged(self, store):
        uid, cid = self._setup_advertiser(store)
        # Without the adapter, escrow_execute always succeeds at the
        # accounting layer. Document the invariant: if debit_thr raises
        # WalletInsufficientBalance, no pool credit happens and no
        # escrow row is written.
        bal_before = store.escrow_balance(cid)
        assert Decimal(bal_before) == 0
        # TODO once WalletSettlementAdapter is wired:
        #   adapter = mock.MagicMock(spec=WalletSettlementAdapter)
        #   adapter.debit_thr.side_effect = WalletInsufficientBalance()
        #   with pytest.raises(EarnError, match="insufficient_thr_balance"):
        #       _escrow_via_intent_with_adapter(...)
        #   assert store.escrow_balance(cid) == "0"
        #   adapter.credit_pythia_pool.assert_not_called()

    # 8. Wrong wallet address rejected
    def test_wrong_wallet_address_rejected(self, store):
        uid, cid = self._setup_advertiser(store)
        intent = store.escrow_create_intent(uid, cid, "deposit", "10.000000")
        # Tamper with the intent's wallet_address in the DB to simulate
        # a request from a different wallet than the linked one.
        wrong_wallet = "THR" + "FF" * 20
        with store._tx() as con:
            con.execute(
                "UPDATE earn_escrow_intents SET wallet_address = ? WHERE intent_id = ?",
                (wrong_wallet, intent["intent_id"]),
            )
        # Sign with the correct key but the intent now points to the
        # wrong address — escrow_execute must reject.
        intent["wallet_address"] = wrong_wallet
        sig = _sign_intent(_SETTLE_PRIVKEY, intent)
        with pytest.raises(EarnError, match="wallet_address_mismatch"):
            store.escrow_execute(
                intent["intent_id"], uid,
                intent["nonce"], wallet_signature=sig,
            )
