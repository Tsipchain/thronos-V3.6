"""Production security and conservation tests for canonical paid delivery."""
import hashlib
import os
import tempfile
import time

import pytest
from flask import Flask

from services.earn_account import (
    EarnAccountStore,
    EarnError,
    register_earn_account_routes,
)


@pytest.fixture()
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
        path = handle.name
    instance = EarnAccountStore(path, "production-ad-test-key-abcdef012345")
    yield instance
    os.unlink(path)


def _credit(store, user_id, amount="5000.000000"):
    now = int(time.time())
    with store._tx() as con:
        con.execute(
            """INSERT INTO thc_ledger
               (entry_id, earn_user_id, source, source_ref, amount, state,
                note, created_at, updated_at)
               VALUES (?,?,?,?,?,'confirmed','synthetic acceptance',?,?)""",
            ("thc_synthetic", user_id, "synthetic_acceptance", "funding-5000",
             amount, now, now),
        )


def _publisher(store, user_id, placement="basketball_sidebar"):
    pub = store.publisher_register(user_id, "basketball", "Basketball")
    store.publisher_add_placement(
        pub["publisher_id"], user_id, placement, "https://basketball.example",
    )
    store.publisher_update_postback(
        pub["publisher_id"], user_id,
        "https://basketball.example/api/ad-event", "publisher-secret",
    )
    store.publisher_moderate(pub["publisher_id"], "approve")
    return pub["publisher_id"]


def _fund_walletless(store, user_id, token, campaign_id, amount):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    intent = store.escrow_create_intent_walletless(
        user_id, campaign_id, "deposit", amount, token_hash,
    )
    return store.escrow_execute_walletless(
        intent["intent_id"], user_id, intent["nonce"], intent["csrf_token"],
        token_hash,
    )


def _active_campaign(store, placement="basketball_sidebar"):
    account = store.register("ads@example.com", "SecurePass123!")
    user_id = account["earn_user_id"]
    _, token = store.login("ads@example.com", "SecurePass123!")
    _credit(store, user_id)
    publisher_id = _publisher(store, user_id, placement)
    campaign = store.create_campaign(
        user_id, "Basketball paid", campaign_type="cpc",
        bid_amount="1.000000", total_budget="1000.000000",
        placement=placement, country_targets="GR,US",
    )
    assert campaign["status"] == "funding_required"
    creative = store.add_creative(
        campaign["campaign_id"], user_id, "Basketball offer",
        "https://cdn.example.com/banner.png", "https://shop.example.com/offer",
    )
    assert creative["status"] == "approved"
    funded = _fund_walletless(
        store, user_id, token, campaign["campaign_id"], "1000.000000",
    )
    assert funded["campaign_status"] == "active"
    return user_id, publisher_id, campaign["campaign_id"], token


def test_synthetic_5000_reserve_charge_refund_conserves_thc(store, monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    user_id, publisher_id, campaign_id, _ = _active_campaign(store)

    funded = store.thc_balance(user_id)
    assert funded["total_earned"] == "5000.000000"
    assert funded["reserved"] == "1000.000000"
    assert funded["spent"] == "0.000000"
    assert funded["available"] == "4000.000000"

    served = store.verified_serve(
        "basketball_sidebar", publisher_id,
        "viewer_hash_1234567890", "GR", "publisher-secret",
    )
    assert not served["is_house"]
    event = store.verified_record_event(
        served["proof"]["proof_id"], "click",
        served["proof"]["proof_token"],
    )
    assert event["charged_amount"] == "1.000000"
    replay = store.verified_record_event(
        served["proof"]["proof_id"], "click",
        served["proof"]["proof_token"],
    )
    assert replay["idempotent"] is True

    charged = store.thc_balance(user_id)
    assert charged["spent"] == "1.000000"
    assert charged["reserved"] == "999.000000"
    assert charged["available"] == "4000.000000"

    cancelled = store.cancel_campaign(campaign_id, user_id)
    assert cancelled == {
        "campaign_id": campaign_id,
        "status": "cancelled",
        "refunded": "999.000000",
    }
    final = store.thc_balance(user_id)
    assert final["total_earned"] == "5000.000000"
    assert final["spent"] == "1.000000"
    assert final["reserved"] == "0.000000"
    assert final["available"] == "4999.000000"
    assert store.treasury_summary()["total_balance"] == "1.000000"


def test_policy_publisher_binding_and_legacy_paid_guard(store, monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    user_id, publisher_id, campaign_id, _ = _active_campaign(store)
    campaign = store.get_campaign(campaign_id)
    creatives = store.list_creatives(campaign_id, user_id)

    with pytest.raises(EarnError, match="publisher_placement_not_active"):
        store.verified_serve(
            "basketball_header_interstitial", publisher_id,
            "viewer_hash_1234567890", "GR", "publisher-secret",
        )
    with pytest.raises(EarnError, match="publisher_auth_required"):
        store.verified_serve(
            "basketball_sidebar", publisher_id,
            "viewer_hash_1234567890", "GR", "wrong-secret",
        )
    with pytest.raises(EarnError, match="verified_delivery_required"):
        store.record_campaign_event(
            campaign_id, creatives[0]["creative_id"], "click",
        )
    with pytest.raises(EarnError, match="campaign_not_found"):
        store.cancel_campaign(campaign_id, "wrong-owner")
    assert campaign["status"] == "active"


def test_basketball_bootstrap_is_idempotent_and_preflight_is_secret_safe(
    store, monkeypatch,
):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    account = store.register("publisher@example.com", "SecurePass123!")
    user_id = account["earn_user_id"]
    secret = "publisher-secret-with-at-least-32-characters"

    first = store.bootstrap_basketball_publisher(user_id, secret)
    second = store.bootstrap_basketball_publisher(user_id, secret)
    assert second["publisher_id"] == first["publisher_id"]

    with store._tx() as con:
        placements = con.execute(
            """SELECT placement_type, status
               FROM earn_publisher_placements WHERE publisher_id = ?""",
            (first["publisher_id"],),
        ).fetchall()
    assert {(row["placement_type"], row["status"]) for row in placements} == {
        ("basketball_sidebar", "active"),
        ("basketball_header_interstitial", "active"),
    }

    ready = store.publisher_delivery_preflight(first["publisher_id"], secret)
    assert ready == {
        "delivery_secret_configured": True,
        "publisher_active": True,
        "sidebar_placement_active": True,
        "header_interstitial_placement_active": True,
    }
    assert store.publisher_delivery_preflight(
        first["publisher_id"], "wrong-secret"
    ) == {
        "delivery_secret_configured": True,
        "publisher_active": False,
        "sidebar_placement_active": False,
        "header_interstitial_placement_active": False,
    }


def test_preflight_route_returns_flags_only(store, monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    account = store.register("route-publisher@example.com", "SecurePass123!")
    secret = "publisher-secret-with-at-least-32-characters"
    provisioned = store.bootstrap_basketball_publisher(
        account["earn_user_id"], secret
    )
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_earn_account_routes(app, store)

    response = app.test_client().get(
        "/api/earn/ads/publisher/preflight",
        query_string={"publisher_id": provisioned["publisher_id"]},
        headers={"X-Publisher-Key": secret},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "delivery_secret_configured": True,
        "publisher_active": True,
        "sidebar_placement_active": True,
        "header_interstitial_placement_active": True,
    }


def test_empty_stored_publisher_secret_fails_closed(store, monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    user_id, publisher_id, _, _ = _active_campaign(store)
    with store._tx() as con:
        con.execute(
            "UPDATE earn_publishers SET postback_secret = NULL WHERE publisher_id = ?",
            (publisher_id,),
        )
    with pytest.raises(EarnError, match="publisher_auth_required"):
        store.verified_serve(
            "basketball_sidebar", publisher_id,
            "viewer_hash_1234567890", "GR", "",
        )


def test_creative_policy_rejects_private_script_and_unsafe_images(store):
    account = store.register("policy@example.com", "SecurePass123!")
    campaign = store.create_campaign(
        account["earn_user_id"], "Policy campaign",
        total_budget="10.000000",
    )
    bad = store.add_creative(
        campaign["campaign_id"], account["earn_user_id"],
        "<script>alert(1)</script>", "http://127.0.0.1/banner.svg",
        "javascript:alert(1)",
    )
    assert bad["status"] == "rejected"
    row = store.list_creatives(
        campaign["campaign_id"], account["earn_user_id"],
    )[0]
    assert row["reject_reason"] == "script_payload"


def test_wallet_placements_are_never_served(store, monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    result = store.verified_serve(
        "wallet_home", "irrelevant", "viewer_hash_1234567890", "GR",
    )
    assert result == {"ad": None, "reason": "excluded_placement"}


def test_house_fallback_never_charges_and_paused_paid_is_hidden(store, monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    user_id, publisher_id, campaign_id, _ = _active_campaign(store)
    store.create_ad(
        "Basketball house", "https://cdn.example.com/house.png",
        "https://basketball.example/", placement="basketball",
    )
    store.pause_campaign(campaign_id, user_id)
    before = store.thc_balance(user_id)
    served = store.verified_serve(
        "basketball_sidebar", publisher_id,
        "viewer_hash_1234567890", "GR", "publisher-secret",
    )
    assert served["is_house"] is True
    assert "proof" not in served
    assert store.thc_balance(user_id) == before


def test_no_immediate_paid_campaign_repeat_when_alternative_exists(store, monkeypatch):
    monkeypatch.setenv("EARN_DELIVERY_SECRET", "delivery-secret")
    user_id, publisher_id, first_id, token = _active_campaign(store)
    second = store.create_campaign(
        user_id, "Basketball paid two", campaign_type="cpc",
        bid_amount="1.000000", total_budget="10.000000",
        placement="basketball_sidebar",
    )
    store.add_creative(
        second["campaign_id"], user_id, "Second offer",
        "https://cdn.example.com/second.png", "https://shop.example.com/second",
    )
    _fund_walletless(store, user_id, token, second["campaign_id"], "10.000000")
    first = store.verified_serve(
        "basketball_sidebar", publisher_id,
        "repeat_viewer_hash_12345", "GR", "publisher-secret",
    )
    second_served = store.verified_serve(
        "basketball_sidebar", publisher_id,
        "repeat_viewer_hash_12345", "GR", "publisher-secret",
    )
    assert {first["ad"]["campaign_id"], second_served["ad"]["campaign_id"]} == {
        first_id, second["campaign_id"],
    }
