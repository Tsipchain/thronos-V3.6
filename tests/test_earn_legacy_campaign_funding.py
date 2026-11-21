"""Legacy approved campaign may fund its existing ID, never duplicate or overdraft.

The quote is read-only; only authenticated walletless escrow intent+execute
reserves cleared THC, after explicit operator confirmation in the UI.
"""
import hashlib
import os
import tempfile

import pytest
from flask import Flask

from services.earn_account import EarnAccountStore, EarnError, register_earn_account_routes


@pytest.fixture()
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    instance = EarnAccountStore(path, "legacy-campaign-funding-tests-secret")
    yield instance
    os.unlink(path)


@pytest.fixture()
def approved_legacy(store):
    user = store.register("old-advertiser@example.com", "SecurePass123!")
    uid = user["earn_user_id"]
    _, token = store.login("old-advertiser@example.com", "SecurePass123!")
    camp = store.create_campaign(
        uid, "Basketball existing campaign", "cpm", "1.000000",
        total_budget="100.000000", placement="earn",
    )
    creative = store.add_creative(
        camp["campaign_id"], uid, "Basketball promo",
        "https://cdn.example.com/banner.png",
        "https://tranfermarktbasket.com/",
    )
    assert creative["status"] == "approved"
    # Historical approved record predating strict funding gates.
    with store._tx() as con:
        con.execute(
            "UPDATE earn_ad_campaigns SET status='approved', policy_status='approved' WHERE campaign_id=?",
            (camp["campaign_id"],),
        )
    return uid, token, camp["campaign_id"]


def _credit(store, uid):
    entry, _ = store.record_thc_credit(
        earn_user_id=uid, amount="100.000000",
        source="test", source_ref="synthetic-legacy-funding",
        note="synthetic tests only",
    )
    store.transition_thc(entry["entry_id"], "confirmed")


def test_legacy_approved_without_escrow_requires_exact_thc_funding(store, approved_legacy):
    uid, token, cid = approved_legacy
    before = store.thc_balance(uid)
    quote = store.campaign_funding_quote(cid, uid)
    assert quote["currency"] == "THC"
    assert quote["funding_due"] == "100.000000"
    assert quote["escrow_balance"] == "0.000000"
    assert quote["reserved_thc"] == "0.000000"
    assert quote["fundable"] is True
    assert store.thc_balance(uid) == before
    _credit(store, uid)
    thash = hashlib.sha256(token.encode()).hexdigest()
    intent = store.escrow_create_intent_walletless(uid, cid, "deposit", quote["funding_due"], thash)
    result = store.escrow_execute_walletless(
        intent["intent_id"], uid, intent["nonce"], intent["csrf_token"], thash,
    )
    assert result["campaign_status"] == "active"
    assert result["balance_after"] == "100.000000"
    after = store.campaign_funding_quote(cid, uid)
    assert after["funding_due"] == "0.000000"
    assert after["fundable"] is False
    assert after["reason"] == "fully_funded"
    assert store.thc_balance(uid)["reserved"] == "100.000000"
    with pytest.raises(EarnError, match="invalid_or_expired_intent"):
        store.escrow_execute_walletless(
            intent["intent_id"], uid, intent["nonce"], intent["csrf_token"], thash,
        )


def test_existing_active_unfunded_campaign_is_quotable_without_recreating(store, approved_legacy):
    uid, _, cid = approved_legacy
    with store._tx() as con:
        con.execute("UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?", (cid,))
    quote = store.campaign_funding_quote(cid, uid)
    assert quote["campaign_id"] == cid
    assert quote["status"] == "active"
    assert quote["fundable"] is True
    assert quote["funding_due"] == "100.000000"


def test_escrow_reservation_mismatch_never_suggests_another_charge(store, approved_legacy):
    uid, _, cid = approved_legacy
    with store._tx() as con:
        con.execute(
            """INSERT INTO earn_ad_escrow
            (escrow_id,campaign_id,advertiser_id,action,amount,balance_after,note,
             idempotency_key,intent_id,payload_hash,settlement_status,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("esc_legacy_only", cid, uid, "deposit", "100.000000",
             "100.000000", "legacy record without reservation",
             "legacy-escrow-only", "legacy", "synthetic", "settled", 1000),
        )
    quote = store.campaign_funding_quote(cid, uid)
    assert quote["fundable"] is False
    assert quote["reason"] == "escrow_reservation_mismatch"


def test_quote_does_not_disclose_another_advertisers_campaign(store, approved_legacy):
    uid, _, cid = approved_legacy
    other = store.register("other-advertiser@example.com", "SecurePass123!")
    with pytest.raises(EarnError, match="campaign_not_found"):
        store.campaign_funding_quote(cid, other["earn_user_id"])


def test_funding_quote_http_requires_valid_earn_session(store, approved_legacy):
    uid, token, cid = approved_legacy
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_earn_account_routes(app, store)
    client = app.test_client()
    path = "/api/earn/ads/campaign/" + cid + "/funding-quote"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    assert response.get_json()["funding_due"] == "100.000000"
    assert response.get_json()["currency"] == "THC"
