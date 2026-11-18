"""Security and accounting contract for view-only ad billing."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import os
import sqlite3
import tempfile
import time

import pytest

from services.earn_account import EarnAccountStore, EarnError


@pytest.fixture()
def store(monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "view-only-delivery-secret")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
        path = handle.name
    instance = EarnAccountStore(path, "view-only-identity-key")
    yield instance
    os.unlink(path)


def _credit(store, user_id, amount="20.000000"):
    now = int(time.time())
    with store._tx() as con:
        con.execute(
            """INSERT INTO thc_ledger
               (entry_id, earn_user_id, source, source_ref, amount, state,
                note, created_at, updated_at)
               VALUES (?,?,?,?,?,'confirmed','synthetic view-only test',?,?)""",
            ("credit_" + hashlib.sha256(os.urandom(16)).hexdigest(), user_id,
             "synthetic_test", os.urandom(8).hex(), amount, now, now),
        )


def _publisher(store, user_id, placement="earn"):
    pub = store.publisher_register(user_id, "test", "Test publisher")
    store.publisher_add_placement(
        pub["publisher_id"], user_id, placement, "https://publisher.example",
    )
    store.publisher_update_postback(
        pub["publisher_id"], user_id,
        "https://publisher.example/events", "publisher-secret",
    )
    store.publisher_moderate(pub["publisher_id"], "approve")
    return pub["publisher_id"]


def _fund(store, user_id, token, campaign_id, amount):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    intent = store.escrow_create_intent_walletless(
        user_id, campaign_id, "deposit", amount, token_hash,
    )
    return store.escrow_execute_walletless(
        intent["intent_id"], user_id, intent["nonce"], intent["csrf_token"],
        token_hash,
    )


def _active(store, *, budget="0.150000", target=None, placement="earn",
            cpm="50.000000"):
    account = store.register(
        f"ad-{os.urandom(6).hex()}@example.com", "SecurePass123!",
    )
    user_id = account["earn_user_id"]
    # Login needs the generated address, so read it back without exposing any
    # secret material.
    with store._tx() as con:
        address = con.execute(
            "SELECT email FROM earn_accounts WHERE earn_user_id=?", (user_id,),
        ).fetchone()["email"]
    _, token = store.login(address, "SecurePass123!")
    _credit(store, user_id, "20.000000")
    publisher_id = _publisher(store, user_id, placement)
    campaign = store.create_campaign(
        user_id, "View campaign", campaign_type="cpm", bid_amount=cpm,
        approved_max_cpm=cpm, total_budget=budget, placement=placement,
        view_target=target,
    )
    creative = store.add_creative(
        campaign["campaign_id"], user_id, "Safe product",
        "https://cdn.example.com/ad.png", "https://shop.example.com/item",
    )
    assert creative["status"] == "approved"
    funded = _fund(store, user_id, token, campaign["campaign_id"], budget)
    assert funded["campaign_status"] == "active"
    return user_id, publisher_id, campaign["campaign_id"]


def _serve(store, publisher_id, placement="earn", viewer="viewer_1234567890"):
    return store.verified_serve(
        placement, publisher_id, viewer, "GR", "publisher-secret",
    )


def _view(store, served):
    return store.verified_record_event(
        served["proof"]["proof_id"], "view",
        served["proof"]["proof_token"],
        viewable_ms=1200, visible_percent=75, page_visible=True,
    )


def test_new_cpc_contracts_are_closed(store):
    user = store.register("cpc@example.com", "SecurePass123!")
    with pytest.raises(EarnError, match="cpc_campaigns_closed"):
        store.create_campaign(
            user["earn_user_id"], "CPC", campaign_type="cpc",
            total_budget="1.000000",
        )


def test_safe_content_auto_approves_and_risky_content_waits(store):
    user = store.register("policy@example.com", "SecurePass123!")
    campaign = store.create_campaign(
        user["earn_user_id"], "Safe", total_budget="2.000000",
    )
    assert campaign["status"] == "funding_required"
    safe = store.add_creative(
        campaign["campaign_id"], user["earn_user_id"], "Safe offer",
        "https://cdn.example/ad.png", "https://shop.example/item",
    )
    risky = store.add_creative(
        campaign["campaign_id"], user["earn_user_id"], "Casino offer",
        "https://cdn.example/risky.png", "https://shop.example/risky",
    )
    assert safe["status"] == "approved"
    assert risky["status"] == "manual_review"


def test_manual_rejection_cannot_be_auto_bypassed(store):
    user = store.register("reject@example.com", "SecurePass123!")
    campaign = store.create_campaign(
        user["earn_user_id"], "Rejected", total_budget="2.000000",
    )
    store.moderate_campaign(campaign["campaign_id"], "reject", "operator")
    evaluated = store.evaluate_campaign_policy(campaign["campaign_id"], apply=True)
    assert evaluated["decision"] == "rejected"
    assert store.get_campaign(campaign["campaign_id"])["status"] == "rejected"


def test_click_is_analytics_only_and_view_is_exactly_once(store):
    user_id, publisher_id, campaign_id = _active(store)
    served = _serve(store, publisher_id)
    click = store.verified_record_event(
        served["proof"]["proof_id"], "click", served["proof"]["proof_token"],
    )
    assert click["charged_amount"] == "0.000000"
    view = _view(store, served)
    assert view["charged_amount"] == "0.050000"
    replay = _view(store, served)
    assert replay["idempotent"] is True
    balance = store.thc_balance(user_id)
    assert balance["spent"] == "0.050000"
    assert balance["reserved"] == "0.100000"
    report = store.campaign_report(campaign_id, user_id)
    assert report["verified_views"] == 1
    assert report["clicks"] == 1
    assert report["ctr"] == 100.0


@pytest.mark.parametrize("kwargs", [
    {},
    {"viewable_ms": 999, "visible_percent": 75, "page_visible": True},
    {"viewable_ms": 1200, "visible_percent": 49, "page_visible": True},
    {"viewable_ms": 1200, "visible_percent": 75, "page_visible": False},
])
def test_fake_or_unqualified_view_is_zero_charge(store, kwargs):
    user_id, publisher_id, campaign_id = _active(store)
    served = _serve(store, publisher_id)
    with pytest.raises(EarnError, match="view_not_qualifying"):
        store.verified_record_event(
            served["proof"]["proof_id"], "view",
            served["proof"]["proof_token"], **kwargs,
        )
    assert store.thc_balance(user_id)["spent"] == "0.000000"
    assert store.campaign_report(campaign_id, user_id)["verified_views"] == 0


def test_pause_keeps_reservation_and_cancel_refunds_only_unspent(store):
    user_id, publisher_id, campaign_id = _active(store)
    _view(store, _serve(store, publisher_id))
    store.pause_campaign(campaign_id, user_id)
    assert store.thc_balance(user_id)["reserved"] == "0.100000"
    cancelled = store.cancel_campaign(campaign_id, user_id)
    assert cancelled["refunded"] == "0.100000"
    balance = store.thc_balance(user_id)
    assert balance["reserved"] == "0.000000"
    assert balance["spent"] == "0.050000"


def test_view_target_completes_and_refunds_residual(store):
    user_id, publisher_id, campaign_id = _active(
        store, budget="0.150000", target=2,
    )
    _view(store, _serve(store, publisher_id, viewer="viewer_target_0001"))
    _view(store, _serve(store, publisher_id, viewer="viewer_target_0002"))
    campaign = store.get_campaign(campaign_id)
    assert campaign["status"] == "completed"
    assert store.thc_balance(user_id)["spent"] == "0.100000"
    assert store.thc_balance(user_id)["reserved"] == "0.000000"


def test_sub_view_budget_remainder_completes_and_refunds(store):
    user_id, publisher_id, campaign_id = _active(
        store, budget="0.075000", cpm="50.000000",
    )
    _view(store, _serve(store, publisher_id))
    campaign = store.get_campaign(campaign_id)
    assert campaign["status"] == "exhausted"
    assert store.thc_balance(user_id)["spent"] == "0.050000"
    assert store.thc_balance(user_id)["reserved"] == "0.000000"


def test_concurrent_duplicate_event_cannot_overspend(store):
    user_id, publisher_id, campaign_id = _active(store, budget="0.050000")
    served = _serve(store, publisher_id)

    def submit():
        return _view(store, served)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: submit(), range(8)))
    assert sum(r.get("idempotent") is not True for r in results) == 1
    assert store.thc_balance(user_id)["spent"] == "0.050000"
    assert store.treasury_summary()["total_balance"] == "0.050000"
    assert store.get_campaign(campaign_id)["status"] == "exhausted"


def test_sensitive_wallet_placement_never_serves_paid(store):
    user = store.register("walletpub@example.com", "SecurePass123!")
    publisher_id = _publisher(store, user["earn_user_id"], "wallet_signing")
    result = store.verified_serve(
        "wallet_signing", publisher_id, "viewer_wallet_12345", "GR",
        "publisher-secret",
    )
    assert result == {"ad": None, "reason": "excluded_placement"}


def test_pricing_quote_is_versioned_but_geo_weights_are_inactive(store):
    pricing = store.get_ad_pricing()
    assert len(pricing) == 1
    assert pricing[0]["billing_model"] == "verified_view"
    assert pricing[0]["pricing_version"] == "thronos-view-fixed-v1"
    assert pricing[0]["dynamic_geo_pricing_active"] is False


def test_existing_active_cpc_is_held_without_releasing_reservation(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = EarnAccountStore(str(path), "legacy-key")
    user = legacy.register("legacy@example.com", "SecurePass123!")
    now = int(time.time())
    with legacy._tx() as con:
        con.execute(
            """INSERT INTO earn_ad_campaigns
               (campaign_id, advertiser_id, name, campaign_type, bid_amount,
                daily_budget, total_budget, placement, status, impressions,
                clicks, spent, created_at, updated_at)
               VALUES ('legacy-cpc',?,'Legacy CPC','cpc','1.000000','0',
                       '5.000000','earn','active',0,0,'0.000000',?,?)""",
            (user["earn_user_id"], now, now),
        )
        con.execute(
            """INSERT INTO earn_thc_reservations
               (reservation_id, earn_user_id, reservation_type, amount, state,
                source_ref, idempotency_key, created_at, updated_at)
               VALUES ('legacy-res',?,'ad_escrow','5.000000','reserved',
                       'legacy-cpc','legacy-idem',?,?)""",
            (user["earn_user_id"], now, now),
        )
    # Reopening runs the additive migration policy.
    reopened = EarnAccountStore(str(path), "legacy-key")
    campaign = reopened.get_campaign("legacy-cpc")
    assert campaign["status"] == "legacy_contract_review"
    assert campaign["migration_state"] == "cpc_contract_action_required"
    assert campaign["thc_still_reserved"] == "5.000000"

