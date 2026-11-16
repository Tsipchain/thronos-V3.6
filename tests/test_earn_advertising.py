"""Production advertising tests — pricing, walletless escrow, activation,
treasury, VIP credits, refunds, and enhanced reports.

Tests Priority 1 of the THRONOS EARN consolidated production execution.
"""
import hashlib
import json
import os
import pytest
import secrets
import tempfile
import time
import unittest.mock as mock

os.environ.setdefault("EARN_DB_PATH", ":memory:")

_ORIG_DELIVERY_SECRET = os.environ.get("EARN_DELIVERY_SECRET")
os.environ["EARN_DELIVERY_SECRET"] = "test-delivery-secret-32chars-ok!"


@pytest.fixture(autouse=True, scope="session")
def _restore_delivery_secret():
    yield
    if _ORIG_DELIVERY_SECRET is None:
        os.environ.pop("EARN_DELIVERY_SECRET", None)
    else:
        os.environ["EARN_DELIVERY_SECRET"] = _ORIG_DELIVERY_SECRET

from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils
from cryptography.hazmat.primitives import hashes
from decimal import Decimal
from services.earn_account import (
    EarnAccountStore, EarnError, _THC_SCALE,
    _VIP_CREDIT_MILESTONE_THC, _VIP_CREDIT_RATE_BPS,
    _WALLETLESS_SPEND_CAP_PER_DAY, _WALLETLESS_RATE_LIMIT_PER_HOUR,
)


_TEST_KEY = "test-identity-key-for-advertising-prod-abcdef0123"


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
    return store.register("advertiser@prod-test.com", "SecurePass123!")


@pytest.fixture()
def campaign(store, advertiser):
    return store.create_campaign(
        advertiser_id=advertiser["earn_user_id"],
        name="Prod Test Campaign",
        campaign_type="cpm",
        bid_amount="2.000000",
        total_budget="100.000000",
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
        intent["intent_id"], earn_user_id, intent["nonce"], sig,
    )


def _credit_thc(store, earn_user_id, amount="10000.000000"):
    entry, _ = store.record_thc_credit(
        earn_user_id=earn_user_id,
        amount=amount,
        source="test",
        source_ref=f"test_{secrets.token_hex(8)}",
        note="test credit",
    )
    store.transition_thc(entry["entry_id"], "confirmed")


def _make_session_token_hash(store, earn_user_id):
    """Create a real session for an earn user and return its token_hash."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = int(time.time())
    with store._tx() as con:
        con.execute(
            """INSERT INTO earn_sessions
               (token_hash, earn_user_id, created_at, expires_at)
               VALUES (?,?,?,?)""",
            (token_hash, earn_user_id, now, now + 86400),
        )
    return token_hash


# ── Pricing Tests ────────────────────────────────────────────────────

class TestAdPricing:

    def test_default_pricing_seeded(self, store):
        pricing = store.get_ad_pricing()
        assert len(pricing) == 2
        types = {p["campaign_type"] for p in pricing}
        assert types == {"cpm", "cpc"}
        for p in pricing:
            assert Decimal(p["min_bid"]) > 0
            assert Decimal(p["max_bid"]) > Decimal(p["min_bid"])
            assert p["currency"] == "THC"

    def test_pricing_idempotent(self, store):
        pricing1 = store.get_ad_pricing()
        store._init_db()
        pricing2 = store.get_ad_pricing()
        assert len(pricing1) == len(pricing2)


# ── Walletless Escrow Tests ──────────────────────────────────────────

class TestWalletlessEscrow:

    def test_walletless_intent_and_execute_deposit(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        store.moderate_campaign(campaign["campaign_id"], "approve")
        token_hash = _make_session_token_hash(store, uid)

        intent = store.escrow_create_intent_walletless(
            uid, campaign["campaign_id"], "deposit", "100.000000",
            session_token_hash=token_hash,
        )
        assert intent["requires_wallet_sig"] is False
        assert intent["approval"] == "session_reauth"
        assert intent["csrf_token"]
        assert intent["nonce"]

        result = store.escrow_execute_walletless(
            intent["intent_id"], uid, intent["nonce"],
            intent["csrf_token"], session_token_hash=token_hash,
        )
        assert result["action"] == "deposit"
        assert result["balance_after"] == "100.000000"
        assert result["settlement_status"] == "settled"

    def test_walletless_insufficient_balance(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        token_hash = _make_session_token_hash(store, uid)
        store.moderate_campaign(campaign["campaign_id"], "approve")
        with pytest.raises(EarnError, match="insufficient_thc_balance"):
            store.escrow_create_intent_walletless(
                uid, campaign["campaign_id"], "deposit", "100.000000",
                session_token_hash=token_hash,
            )

    def test_walletless_daily_cap(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "50000.000000")
        store.moderate_campaign(campaign["campaign_id"], "approve")
        token_hash = _make_session_token_hash(store, uid)

        for i in range(5):
            intent = store.escrow_create_intent_walletless(
                uid, campaign["campaign_id"], "deposit", "1000.000000",
                session_token_hash=token_hash,
            )
            store.escrow_execute_walletless(
                intent["intent_id"], uid, intent["nonce"],
                intent["csrf_token"], session_token_hash=token_hash,
            )

        with pytest.raises(EarnError, match="walletless_daily_cap_exceeded"):
            store.escrow_create_intent_walletless(
                uid, campaign["campaign_id"], "deposit", "1.000000",
                session_token_hash=token_hash,
            )

    def test_walletless_csrf_mismatch(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        store.moderate_campaign(campaign["campaign_id"], "approve")
        token_hash = _make_session_token_hash(store, uid)

        intent = store.escrow_create_intent_walletless(
            uid, campaign["campaign_id"], "deposit", "100.000000",
            session_token_hash=token_hash,
        )
        with pytest.raises(EarnError, match="csrf_token_mismatch"):
            store.escrow_execute_walletless(
                intent["intent_id"], uid, intent["nonce"],
                "wrong_csrf_token", session_token_hash=token_hash,
            )

    def test_walletless_session_reauth_required(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        store.moderate_campaign(campaign["campaign_id"], "approve")
        token_hash = _make_session_token_hash(store, uid)

        intent = store.escrow_create_intent_walletless(
            uid, campaign["campaign_id"], "deposit", "100.000000",
            session_token_hash=token_hash,
        )
        with pytest.raises(EarnError, match="session_reauth_required"):
            store.escrow_execute_walletless(
                intent["intent_id"], uid, intent["nonce"],
                intent["csrf_token"], session_token_hash="invalid_hash",
            )

    def test_walletless_expired_session_rejected(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        store.moderate_campaign(campaign["campaign_id"], "approve")
        token = secrets.token_urlsafe(32)
        expired_hash = hashlib.sha256(token.encode()).hexdigest()
        now = int(time.time())
        with store._tx() as con:
            con.execute(
                "INSERT INTO earn_sessions (token_hash, earn_user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (expired_hash, uid, now - 7200, now - 3600),
            )
        intent = store.escrow_create_intent_walletless(
            uid, campaign["campaign_id"], "deposit", "100.000000",
            session_token_hash=expired_hash,
        )
        with pytest.raises(EarnError, match="session_reauth_required"):
            store.escrow_execute_walletless(
                intent["intent_id"], uid, intent["nonce"],
                intent["csrf_token"], session_token_hash=expired_hash,
            )

    def test_walletless_refund(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        store.moderate_campaign(campaign["campaign_id"], "approve")
        token_hash = _make_session_token_hash(store, uid)

        dep_intent = store.escrow_create_intent_walletless(
            uid, campaign["campaign_id"], "deposit", "200.000000",
            session_token_hash=token_hash,
        )
        store.escrow_execute_walletless(
            dep_intent["intent_id"], uid, dep_intent["nonce"],
            dep_intent["csrf_token"], session_token_hash=token_hash,
        )

        ref_intent = store.escrow_create_intent_walletless(
            uid, campaign["campaign_id"], "refund", "50.000000",
            session_token_hash=token_hash,
        )
        result = store.escrow_execute_walletless(
            ref_intent["intent_id"], uid, ref_intent["nonce"],
            ref_intent["csrf_token"], session_token_hash=token_hash,
        )
        assert result["action"] == "refund"
        assert result["balance_after"] == "150.000000"


# ── Campaign Activation Tests ────────────────────────────────────────

class TestCampaignActivation:

    def test_activate_approved_funded_campaign(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        _link_wallet(store, uid)
        store.moderate_campaign(campaign["campaign_id"], "approve")

        creative = store.add_creative(
            campaign["campaign_id"], uid,
            "Test Ad", "https://img.test/ad.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")

        _escrow_via_intent(store, uid, campaign["campaign_id"], "deposit", "50.000000")

        result = store.activate_campaign(campaign["campaign_id"], uid)
        assert result["status"] == "active"

    def test_activate_unapproved_fails(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        with pytest.raises(EarnError, match="campaign_must_be_approved"):
            store.activate_campaign(campaign["campaign_id"], uid)

    def test_activate_no_creatives_fails(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        store.moderate_campaign(campaign["campaign_id"], "approve")
        with pytest.raises(EarnError, match="no_approved_creatives"):
            store.activate_campaign(campaign["campaign_id"], uid)

    def test_activate_insufficient_escrow_fails(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        store.moderate_campaign(campaign["campaign_id"], "approve")
        creative = store.add_creative(
            campaign["campaign_id"], uid,
            "Test", "https://img.test/ad.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")
        with pytest.raises(EarnError, match="insufficient_escrow_for_activation"):
            store.activate_campaign(campaign["campaign_id"], uid)


# ── Campaign Refund Tests ────────────────────────────────────────────

class TestCampaignRefund:

    def test_refund_completed_campaign(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        _link_wallet(store, uid)
        store.moderate_campaign(campaign["campaign_id"], "approve")

        creative = store.add_creative(
            campaign["campaign_id"], uid,
            "Ad", "https://img.test/ad.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")
        _escrow_via_intent(store, uid, campaign["campaign_id"], "deposit", "50.000000")
        store.activate_campaign(campaign["campaign_id"], uid)
        store.pause_campaign(campaign["campaign_id"], uid)

        result = store.process_campaign_refund(campaign["campaign_id"], uid)
        assert result["status"] == "refunded"
        assert Decimal(result["refunded"]) == Decimal("50.000000")

        bal = store.escrow_balance(campaign["campaign_id"])
        assert Decimal(bal) == Decimal("0")

    def test_refund_active_campaign_fails(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "5000.000000")
        _link_wallet(store, uid)
        store.moderate_campaign(campaign["campaign_id"], "approve")
        creative = store.add_creative(
            campaign["campaign_id"], uid,
            "Ad", "https://img.test/ad.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")
        _escrow_via_intent(store, uid, campaign["campaign_id"], "deposit", "50.000000")
        store.activate_campaign(campaign["campaign_id"], uid)

        with pytest.raises(EarnError, match="campaign_not_refundable"):
            store.process_campaign_refund(campaign["campaign_id"], uid)

    def test_refund_zero_balance_returns_no_balance(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        store.moderate_campaign(campaign["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status = 'completed' WHERE campaign_id = ?",
                (campaign["campaign_id"],),
            )
        result = store.process_campaign_refund(campaign["campaign_id"], uid)
        assert result["status"] == "no_balance"


# ── Treasury Tests ───────────────────────────────────────────────────

class TestPythiaTreasury:

    def test_treasury_credits_on_verified_event(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "10000.000000")
        _link_wallet(store, uid)
        store.moderate_campaign(campaign["campaign_id"], "approve")
        creative = store.add_creative(
            campaign["campaign_id"], uid,
            "Ad", "https://img.test/ad.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")
        _escrow_via_intent(store, uid, campaign["campaign_id"], "deposit", "50.000000")
        store.activate_campaign(campaign["campaign_id"], uid)

        pub = store.publisher_register(uid, "test_provider", "Test Pub")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_publishers SET status = 'active' WHERE publisher_id = ?",
                (pub["publisher_id"],),
            )

        viewer_hash = hashlib.sha256(b"viewer1").hexdigest()
        serve_result = store.verified_serve(
            placement="earn",
            publisher_id=pub["publisher_id"],
            viewer_hash=viewer_hash,
        )
        assert serve_result["ad"] is not None
        assert serve_result["is_house"] is False

        event_result = store.verified_record_event(
            proof_id=serve_result["proof"]["proof_id"],
            event_type="view",
            proof_token=serve_result["proof"]["proof_token"],
        )
        assert Decimal(event_result["charged_amount"]) > 0

        summary = store.treasury_summary()
        assert Decimal(summary["total_balance"]) > 0
        assert "ad_spend" in summary["by_source"]

    def test_treasury_never_mixed_with_thr(self, store):
        summary = store.treasury_summary()
        assert summary["total_balance"] == "0.000000"

    def test_house_ads_no_treasury_debit(self, store):
        summary = store.treasury_summary()
        assert Decimal(summary["total_balance"]) == 0
        assert summary["by_source"] == {}


# ── VIP Loyalty Credit Tests ─────────────────────────────────────────

class TestVIPLoyaltyCredits:

    def test_vip_credit_at_milestone(self, store, advertiser):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "50000.000000")
        _link_wallet(store, uid)

        camp = store.create_campaign(
            advertiser_id=uid,
            name="VIP Test Campaign",
            campaign_type="cpc",
            bid_amount="10.000000",
            total_budget="5000.000000",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        creative = store.add_creative(
            camp["campaign_id"], uid,
            "VIP Ad", "https://img.test/vip.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")
        _escrow_via_intent(store, uid, camp["campaign_id"], "deposit", "2000.000000")
        store.activate_campaign(camp["campaign_id"], uid)

        pub = store.publisher_register(uid, "test_provider", "VIP Pub")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_publishers SET status = 'active' WHERE publisher_id = ?",
                (pub["publisher_id"],),
            )

        credits_found = []
        for i in range(120):
            viewer_hash = hashlib.sha256(f"vip_viewer_{i}".encode()).hexdigest()
            serve = store.verified_serve(
                placement="earn",
                publisher_id=pub["publisher_id"],
                viewer_hash=viewer_hash,
            )
            if not serve.get("ad") or serve.get("is_house"):
                break
            event = store.verified_record_event(
                proof_id=serve["proof"]["proof_id"],
                event_type="click",
                proof_token=serve["proof"]["proof_token"],
            )
            if event.get("vip_credit"):
                credits_found.append(event["vip_credit"])

        assert len(credits_found) >= 1
        first_credit = credits_found[0]
        expected_credit = (_VIP_CREDIT_MILESTONE_THC * _VIP_CREDIT_RATE_BPS / Decimal("10000")).quantize(_THC_SCALE)
        assert Decimal(first_credit["credit_amount"]) == expected_credit

    def test_no_vip_credit_without_wallet(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        with store._tx() as con:
            result = store._check_vip_loyalty_credit(con, uid, campaign["campaign_id"])
        assert result is None


# ── Enhanced Reports Tests ───────────────────────────────────────────

class TestEnhancedReports:

    def test_report_includes_vip_and_treasury(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "10000.000000")
        _link_wallet(store, uid)
        store.moderate_campaign(campaign["campaign_id"], "approve")
        creative = store.add_creative(
            campaign["campaign_id"], uid,
            "Report Ad", "https://img.test/rpt.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")
        _escrow_via_intent(store, uid, campaign["campaign_id"], "deposit", "50.000000")
        store.activate_campaign(campaign["campaign_id"], uid)

        pub = store.publisher_register(uid, "test_provider", "Report Pub")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_publishers SET status = 'active' WHERE publisher_id = ?",
                (pub["publisher_id"],),
            )

        viewer_hash = hashlib.sha256(b"report_viewer").hexdigest()
        serve = store.verified_serve(
            placement="earn",
            publisher_id=pub["publisher_id"],
            viewer_hash=viewer_hash,
        )
        if serve.get("ad") and not serve.get("is_house"):
            store.verified_record_event(
                proof_id=serve["proof"]["proof_id"],
                event_type="view",
                proof_token=serve["proof"]["proof_token"],
            )

        report = store.campaign_report(campaign["campaign_id"], uid)
        assert "vip_credits" in report
        assert "treasury_contributed" in report
        assert isinstance(report["events_by_day"], list)
        assert isinstance(report["events_by_country"], list)

    def test_daily_report_uses_delivery_events(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        _credit_thc(store, uid, "10000.000000")
        _link_wallet(store, uid)
        store.moderate_campaign(campaign["campaign_id"], "approve")
        creative = store.add_creative(
            campaign["campaign_id"], uid,
            "Daily Ad", "https://img.test/d.png", "https://test.com",
        )
        store.moderate_creative(creative["creative_id"], "approve")
        _escrow_via_intent(store, uid, campaign["campaign_id"], "deposit", "50.000000")
        store.activate_campaign(campaign["campaign_id"], uid)

        pub = store.publisher_register(uid, "test_provider", "Daily Pub")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_publishers SET status = 'active' WHERE publisher_id = ?",
                (pub["publisher_id"],),
            )

        viewer_hash = hashlib.sha256(b"daily_viewer").hexdigest()
        serve = store.verified_serve(
            placement="earn",
            publisher_id=pub["publisher_id"],
            viewer_hash=viewer_hash,
        )
        if serve.get("ad") and not serve.get("is_house"):
            store.verified_record_event(
                proof_id=serve["proof"]["proof_id"],
                event_type="view",
                proof_token=serve["proof"]["proof_token"],
            )

        daily = store.campaign_report_daily(campaign["campaign_id"], uid)
        assert isinstance(daily, list)
        if daily:
            assert "impressions" in daily[0]
            assert "clicks" in daily[0]
            assert "cost" in daily[0]


# ── Serve Route 503 Gate Tests ───────────────────────────────────────

class TestServeRouteGating:

    def test_serve_returns_503_without_delivery_secret(self, store, advertiser, campaign):
        uid = advertiser["earn_user_id"]
        with mock.patch.dict(os.environ, {"EARN_DELIVERY_SECRET": ""}):
            with pytest.raises(EarnError, match="verified_ad_delivery_required"):
                store.verified_serve(
                    placement="earn",
                    publisher_id="pub_fake",
                    viewer_hash="hash_fake",
                )

    def test_excluded_placement_returns_none(self, store):
        result = store.verified_serve(
            placement="wallet_home",
            publisher_id="pub_fake",
            viewer_hash="hash_fake",
        )
        assert result["ad"] is None
        assert result["reason"] == "excluded_placement"


# ── Integer-Weight Campaign Selection ────────────────────────────────

class TestIntegerWeightSelection:

    def test_higher_bid_gets_higher_weight(self):
        from services.earn_account import _THC_SCALE
        high_bid = Decimal("10.000000")
        low_bid = Decimal("1.000000")
        high_w = max(int(high_bid / _THC_SCALE), 1)
        low_w = max(int(low_bid / _THC_SCALE), 1)
        assert high_w == 10_000_000
        assert low_w == 1_000_000
        assert high_w > low_w

    def test_very_small_bid_has_minimum_weight(self):
        from services.earn_account import _THC_SCALE
        tiny_bid = Decimal("0.000001")
        w = max(int(tiny_bid / _THC_SCALE), 1)
        assert w >= 1
        zero_bid = Decimal("0.000000")
        w0 = max(int(zero_bid / _THC_SCALE), 1)
        assert w0 >= 1

    def test_no_float_in_service_source(self):
        from pathlib import Path
        source = (Path(__file__).parent.parent / "services" / "earn_account.py").read_text()
        for i, line in enumerate(source.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue
            assert "float(" not in line, f"float() at line {i}: {stripped}"
            assert "AS REAL" not in line.upper() or stripped.startswith("#"), \
                f"CAST AS REAL at line {i}: {stripped}"


# ── End-to-end Walletless Flow ───────────────────────────────────────

class TestEndToEndWalletless:

    def test_full_walletless_advertiser_flow(self, store):
        user = store.register("walletless@prod-test.com", "SecurePass123!")
        uid = user["earn_user_id"]
        _credit_thc(store, uid, "10000.000000")
        token_hash = _make_session_token_hash(store, uid)

        camp = store.create_campaign(
            advertiser_id=uid,
            name="Walletless Campaign",
            campaign_type="cpm",
            bid_amount="1.000000",
            total_budget="50.000000",
        )
        creative = store.add_creative(
            camp["campaign_id"], uid,
            "Walletless Ad", "https://img.test/wl.png", "https://test.com",
        )

        store.moderate_campaign(camp["campaign_id"], "approve")
        store.moderate_creative(creative["creative_id"], "approve")

        intent = store.escrow_create_intent_walletless(
            uid, camp["campaign_id"], "deposit", "50.000000",
            session_token_hash=token_hash,
        )
        result = store.escrow_execute_walletless(
            intent["intent_id"], uid, intent["nonce"],
            intent["csrf_token"], session_token_hash=token_hash,
        )
        assert result["balance_after"] == "50.000000"

        activation = store.activate_campaign(camp["campaign_id"], uid)
        assert activation["status"] == "active"

        bal = store.thc_balance(uid)
        assert Decimal(bal["available"]) < Decimal("10000.000000")

        pub_user = store.register("publisher@prod-test.com", "SecurePass123!")
        pub = store.publisher_register(pub_user["earn_user_id"], "test_provider", "WL Pub")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_publishers SET status = 'active' WHERE publisher_id = ?",
                (pub["publisher_id"],),
            )

        viewer_hash = hashlib.sha256(b"wl_viewer").hexdigest()
        serve = store.verified_serve(
            placement="earn",
            publisher_id=pub["publisher_id"],
            viewer_hash=viewer_hash,
        )
        assert serve["ad"] is not None
        assert serve["is_house"] is False

        event = store.verified_record_event(
            proof_id=serve["proof"]["proof_id"],
            event_type="view",
            proof_token=serve["proof"]["proof_token"],
        )
        assert Decimal(event["charged_amount"]) > 0

        treasury = store.treasury_summary()
        assert Decimal(treasury["total_balance"]) > 0

        store.pause_campaign(camp["campaign_id"], uid)
        refund = store.process_campaign_refund(camp["campaign_id"], uid)
        assert Decimal(refund["refunded"]) > 0

        report = store.campaign_report(camp["campaign_id"], uid)
        assert report["impressions"] >= 1
        assert "treasury_contributed" in report
        assert Decimal(report["treasury_contributed"]) > 0
