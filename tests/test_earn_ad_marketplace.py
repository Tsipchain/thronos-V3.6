"""Tests for the Earn advertising marketplace."""
import os
import pytest
import tempfile
import time

os.environ.setdefault("EARN_DB_PATH", ":memory:")

from decimal import Decimal
from services.earn_account import EarnAccountStore, EarnError


_TEST_KEY = "test-identity-key-for-marketplace-abcdef0123"


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
        assert result["name"] == "My First Ad"
        assert result["status"] == "pending_review"

    def test_create_campaign_cpc(self, store, advertiser):
        result = store.create_campaign(
            advertiser_id=advertiser["earn_user_id"],
            name="CPC Campaign",
            campaign_type="cpc",
            bid_amount="0.500000",
        )
        assert result["campaign_id"].startswith("camp_")

    def test_create_campaign_invalid_type(self, store, advertiser):
        with pytest.raises(EarnError, match="invalid_campaign_type"):
            store.create_campaign(
                advertiser_id=advertiser["earn_user_id"],
                name="Bad",
                campaign_type="invalid",
            )

    def test_create_campaign_zero_bid(self, store, advertiser):
        with pytest.raises(EarnError, match="bid_must_be_positive"):
            store.create_campaign(
                advertiser_id=advertiser["earn_user_id"],
                name="Free",
                bid_amount="0",
            )

    def test_create_campaign_bad_advertiser(self, store):
        with pytest.raises(EarnError, match="advertiser_not_found"):
            store.create_campaign(
                advertiser_id="nonexistent",
                name="Orphan",
            )

    def test_get_campaign(self, store, advertiser, campaign):
        camp = store.get_campaign(campaign["campaign_id"])
        assert camp is not None
        assert camp["name"] == "Test Campaign"
        assert camp["campaign_type"] == "cpm"
        assert camp["status"] == "pending_review"
        assert camp["impressions"] == 0
        assert camp["clicks"] == 0

    def test_get_campaign_not_found(self, store):
        assert store.get_campaign("nonexistent") is None

    def test_list_advertiser_campaigns(self, store, advertiser):
        store.create_campaign(advertiser["earn_user_id"], "Camp A")
        store.create_campaign(advertiser["earn_user_id"], "Camp B")
        camps = store.list_advertiser_campaigns(advertiser["earn_user_id"])
        assert len(camps) == 2
        names = {c["name"] for c in camps}
        assert names == {"Camp A", "Camp B"}

    def test_update_campaign_name(self, store, advertiser, campaign):
        result = store.update_campaign(
            campaign["campaign_id"],
            advertiser["earn_user_id"],
            name="Updated Name",
        )
        assert result["updated"]
        camp = store.get_campaign(campaign["campaign_id"])
        assert camp["name"] == "Updated Name"

    def test_update_campaign_bid(self, store, advertiser, campaign):
        store.update_campaign(
            campaign["campaign_id"],
            advertiser["earn_user_id"],
            bid_amount="10.000000",
        )
        camp = store.get_campaign(campaign["campaign_id"])
        assert Decimal(camp["bid_amount"]) == Decimal("10.000000")

    def test_update_campaign_nothing(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="nothing_to_update"):
            store.update_campaign(
                campaign["campaign_id"],
                advertiser["earn_user_id"],
            )

    def test_update_campaign_wrong_owner(self, store, advertiser, campaign):
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.update_campaign(
                campaign["campaign_id"],
                other["earn_user_id"],
                name="Hijacked",
            )

    def test_pause_and_resume(self, store, advertiser, campaign):
        store.moderate_campaign(campaign["campaign_id"], "approve")
        camp = store.get_campaign(campaign["campaign_id"])
        assert camp["status"] == "approved"
        # Approved campaigns need to be set active to be paused.
        # Use moderate to set approved then update to active by direct means
        # Actually resume expects paused, pause expects active. Let's manually
        # simulate the lifecycle: approved -> active (via serve) -> paused -> resumed
        # For testing, set status to active directly.
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
            campaign["campaign_id"],
            advertiser["earn_user_id"],
            title="Banner 1",
            image_url="https://img.example.com/banner.png",
            target_url="https://thronoschain.org",
        )
        assert result["creative_id"].startswith("crtv_")
        assert result["status"] == "pending_review"

    def test_add_creative_wrong_owner(self, store, advertiser, campaign):
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.add_creative(
                campaign["campaign_id"],
                other["earn_user_id"],
                "X", "https://i.png", "https://t.com",
            )

    def test_list_creatives(self, store, advertiser, campaign):
        store.add_creative(
            campaign["campaign_id"], advertiser["earn_user_id"],
            "Ad A", "https://i.png", "https://a.com",
        )
        store.add_creative(
            campaign["campaign_id"], advertiser["earn_user_id"],
            "Ad B", "https://i.png", "https://b.com",
        )
        creatives = store.list_creatives(
            campaign["campaign_id"], advertiser["earn_user_id"],
        )
        assert len(creatives) == 2
        titles = {c["title"] for c in creatives}
        assert titles == {"Ad A", "Ad B"}

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
        camp = store.get_campaign(campaign["campaign_id"])
        assert camp["status"] == "approved"

    def test_reject_campaign(self, store, advertiser, campaign):
        result = store.moderate_campaign(
            campaign["campaign_id"], "reject", "inappropriate content",
        )
        assert result["status"] == "rejected"
        camp = store.get_campaign(campaign["campaign_id"])
        assert camp["reject_reason"] == "inappropriate content"

    def test_moderate_campaign_invalid_action(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="invalid_moderation_action"):
            store.moderate_campaign(campaign["campaign_id"], "ban")

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


class TestEscrow:
    def test_deposit(self, store, advertiser, campaign):
        result = store.escrow_deposit(
            campaign["campaign_id"], advertiser["earn_user_id"], "100.000000",
        )
        assert result["escrow_id"].startswith("esc_")
        assert Decimal(result["balance_after"]) == Decimal("100.000000")

    def test_balance(self, store, advertiser, campaign):
        store.escrow_deposit(
            campaign["campaign_id"], advertiser["earn_user_id"], "50.000000",
        )
        balance = store.escrow_balance(campaign["campaign_id"])
        assert Decimal(balance) == Decimal("50.000000")

    def test_multiple_deposits(self, store, advertiser, campaign):
        store.escrow_deposit(
            campaign["campaign_id"], advertiser["earn_user_id"], "30.000000",
        )
        store.escrow_deposit(
            campaign["campaign_id"], advertiser["earn_user_id"], "20.000000",
        )
        balance = store.escrow_balance(campaign["campaign_id"])
        assert Decimal(balance) == Decimal("50.000000")

    def test_refund_full(self, store, advertiser, campaign):
        store.escrow_deposit(
            campaign["campaign_id"], advertiser["earn_user_id"], "100.000000",
        )
        result = store.escrow_refund(
            campaign["campaign_id"], advertiser["earn_user_id"],
        )
        assert Decimal(result["balance_after"]) == Decimal("0.000000")

    def test_refund_partial(self, store, advertiser, campaign):
        store.escrow_deposit(
            campaign["campaign_id"], advertiser["earn_user_id"], "100.000000",
        )
        result = store.escrow_refund(
            campaign["campaign_id"], advertiser["earn_user_id"], "40.000000",
        )
        assert Decimal(result["balance_after"]) == Decimal("60.000000")

    def test_refund_exceeds_balance(self, store, advertiser, campaign):
        store.escrow_deposit(
            campaign["campaign_id"], advertiser["earn_user_id"], "10.000000",
        )
        with pytest.raises(EarnError, match="insufficient_escrow_balance"):
            store.escrow_refund(
                campaign["campaign_id"], advertiser["earn_user_id"], "50.000000",
            )

    def test_refund_no_balance(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="no_escrow_balance"):
            store.escrow_refund(
                campaign["campaign_id"], advertiser["earn_user_id"],
            )

    def test_deposit_wrong_owner(self, store, advertiser, campaign):
        other = store.register("other@test.com", "SecurePass456!")
        with pytest.raises(EarnError, match="campaign_not_found"):
            store.escrow_deposit(
                campaign["campaign_id"], other["earn_user_id"], "10.000000",
            )

    def test_deposit_zero_fails(self, store, advertiser, campaign):
        with pytest.raises(EarnError, match="deposit_must_be_positive"):
            store.escrow_deposit(
                campaign["campaign_id"], advertiser["earn_user_id"], "0",
            )


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
            "Banner", "https://img.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        return camp, crtv

    def test_serve_returns_active_ads(self, store, advertiser):
        camp, crtv = self._setup_active_campaign(store, advertiser)
        ads = store.serve_campaign_ads(placement="earn")
        assert len(ads) == 1
        assert ads[0]["campaign_id"] == camp["campaign_id"]
        assert ads[0]["creative_id"] == crtv["creative_id"]
        assert ads[0]["title"] == "Banner"

    def test_serve_filters_placement(self, store, advertiser):
        camp, _ = self._setup_active_campaign(store, advertiser)
        ads = store.serve_campaign_ads(placement="basketball")
        assert len(ads) == 0

    def test_serve_filters_country(self, store, advertiser):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "GR Only",
            country_targets="GR,CY",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        crtv = store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Greek Ad", "https://i.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        ads_gr = store.serve_campaign_ads(country="GR")
        assert len(ads_gr) == 1
        ads_us = store.serve_campaign_ads(country="US")
        assert len(ads_us) == 0

    def test_serve_respects_total_budget(self, store, advertiser):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Budget Camp",
            total_budget="0.001000",
            bid_amount="2.000000",
        )
        store.moderate_campaign(camp["campaign_id"], "approve")
        with store._tx() as con:
            con.execute(
                "UPDATE earn_ad_campaigns SET status='active', spent='0.001000' WHERE campaign_id=?",
                (camp["campaign_id"],),
            )
        crtv = store.add_creative(
            camp["campaign_id"], advertiser["earn_user_id"],
            "Banner", "https://i.png", "https://t.com",
        )
        store.moderate_creative(crtv["creative_id"], "approve")
        ads = store.serve_campaign_ads()
        assert len(ads) == 0

    def test_serve_unapproved_creative_hidden(self, store, advertiser):
        camp = store.create_campaign(advertiser["earn_user_id"], "Camp")
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
        for bid, name in [("1.000000", "Low"), ("10.000000", "High")]:
            camp = store.create_campaign(
                advertiser["earn_user_id"], name, bid_amount=bid,
            )
            store.moderate_campaign(camp["campaign_id"], "approve")
            with store._tx() as con:
                con.execute(
                    "UPDATE earn_ad_campaigns SET status='active' WHERE campaign_id=?",
                    (camp["campaign_id"],),
                )
            crtv = store.add_creative(
                camp["campaign_id"], advertiser["earn_user_id"],
                name, "https://i.png", "https://t.com",
            )
            store.moderate_creative(crtv["creative_id"], "approve")
        ads = store.serve_campaign_ads()
        assert ads[0]["title"] == "High"


class TestEventRecording:
    def _make_active_campaign(self, store, advertiser, **kwargs):
        camp = store.create_campaign(
            advertiser["earn_user_id"], "Event Camp", **kwargs,
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
        store.escrow_deposit(
            camp["campaign_id"], advertiser["earn_user_id"], "100.000000",
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
        store.escrow_deposit(
            camp["campaign_id"], advertiser["earn_user_id"], "100.000000",
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
        assert report["ctr"] > 0
        assert Decimal(report["spent"]) > 0
        assert len(report["events_by_country"]) >= 1

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
        assert daily[0]["impressions"] >= 1


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

    def test_escrow_deposit_and_balance_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Funded"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        r = c.post(
            "/api/earn/ads/escrow/deposit",
            json={"campaign_id": cid, "amount": "50.000000"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert Decimal(r.get_json()["balance_after"]) == Decimal("50.000000")
        r = c.get(
            f"/api/earn/ads/escrow/balance/{cid}",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert Decimal(r.get_json()["balance"]) == Decimal("50.000000")

    def test_escrow_refund_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.post(
            "/api/earn/ads/campaign/create",
            json={"name": "Refundable"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        cid = r.get_json()["campaign_id"]
        c.post(
            "/api/earn/ads/escrow/deposit",
            json={"campaign_id": cid, "amount": "100.000000"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        r = c.post(
            "/api/earn/ads/escrow/refund",
            json={"campaign_id": cid, "amount": "30.000000"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert Decimal(r.get_json()["balance_after"]) == Decimal("70.000000")

    def test_serve_api(self, store):
        c, uid, tok = self._auth_client(store)
        r = c.get("/api/earn/ads/serve?placement=earn")
        assert r.status_code == 200
        assert r.get_json()["ok"]

    def test_serve_event_api(self, store):
        c, uid, tok = self._auth_client(store)
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
        c.post(
            "/api/earn/ads/escrow/deposit",
            json={"campaign_id": cid, "amount": "100.000000"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        r = c.post(
            "/api/earn/ads/serve/event",
            json={
                "campaign_id": cid,
                "creative_id": crtv_id,
                "event_type": "impression",
                "country": "GR",
            },
        )
        assert r.status_code == 200
        assert r.get_json()["ok"]

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
