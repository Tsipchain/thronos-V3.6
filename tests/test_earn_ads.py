"""Tests for the Earn ad banner system."""
import json
import os
import pytest
import tempfile
import time

os.environ.setdefault("EARN_DB_PATH", ":memory:")

from services.earn_account import EarnAccountStore


_TEST_KEY = "test-identity-key-for-ads-1234567890abcdef"


@pytest.fixture()
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = EarnAccountStore(path, _TEST_KEY)
    yield s
    os.unlink(path)


class TestEarnAds:
    def test_create_and_list_ads(self, store):
        result = store.create_ad(
            title="Thronos Promo",
            image_url="https://example.com/banner.png",
            target_url="https://thronoschain.org",
            placement="earn",
            priority=10,
        )
        assert result["ad_id"].startswith("ad_")
        assert result["title"] == "Thronos Promo"

        ads = store.list_ads("earn")
        assert len(ads) == 1
        assert ads[0]["title"] == "Thronos Promo"
        assert ads[0]["impressions"] == 0

    def test_list_ads_filters_by_placement(self, store):
        store.create_ad("Earn Ad", "https://img/1.png", "https://a.com", "earn")
        store.create_ad("Basketball Ad", "https://img/2.png", "https://b.com", "basketball")

        earn_ads = store.list_ads("earn")
        assert len(earn_ads) == 1
        assert earn_ads[0]["title"] == "Earn Ad"

        bball_ads = store.list_ads("basketball")
        assert len(bball_ads) == 1
        assert bball_ads[0]["title"] == "Basketball Ad"

    def test_impression_and_click_tracking(self, store):
        result = store.create_ad("Test", "https://img.png", "https://t.com")
        ad_id = result["ad_id"]

        store.record_ad_impression(ad_id)
        store.record_ad_impression(ad_id)
        store.record_ad_click(ad_id)

        ads = store.list_ads("earn")
        assert ads[0]["impressions"] == 2
        assert ads[0]["clicks"] == 1

    def test_delete_ad_hides_from_listing(self, store):
        result = store.create_ad("To Delete", "https://img.png", "https://t.com")
        assert store.delete_ad(result["ad_id"])
        assert len(store.list_ads("earn")) == 0

    def test_expired_ads_not_listed(self, store):
        past = int(time.time()) - 3600
        store.create_ad("Expired", "https://img.png", "https://t.com", expires_at=past)
        assert len(store.list_ads("earn")) == 0

    def test_priority_ordering(self, store):
        store.create_ad("Low", "https://img.png", "https://a.com", priority=1)
        store.create_ad("High", "https://img.png", "https://b.com", priority=100)

        ads = store.list_ads("earn")
        assert ads[0]["title"] == "High"
        assert ads[1]["title"] == "Low"

    def test_ads_api_endpoints(self, store):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        os.environ["EARN_MGMT_TOKEN"] = "test-mgmt-token-12345"

        from services.earn_account import register_earn_account_routes
        register_earn_account_routes(app, store)

        with app.test_client() as c:
            # Create ad via API
            r = c.post(
                "/api/earn/ads/create",
                json={"title": "API Ad", "image_url": "https://img.png", "target_url": "https://t.com"},
                headers={"X-Admin-Key": "test-mgmt-token-12345"},
            )
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"]
            ad_id = data["ad_id"]

            # List ads
            r = c.get("/api/earn/ads?placement=earn")
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"]
            assert len(data["ads"]) == 1

            # Track impression
            r = c.post("/api/earn/ads/impression", json={"ad_id": ad_id})
            assert r.status_code == 200

            # Track click
            r = c.post("/api/earn/ads/click", json={"ad_id": ad_id})
            assert r.status_code == 200

            # Verify counts
            r = c.get("/api/earn/ads?placement=earn")
            ads = r.get_json()["ads"]
            assert ads[0]["impressions"] == 1
            assert ads[0]["clicks"] == 1

            # Delete ad
            r = c.post(
                "/api/earn/ads/delete",
                json={"ad_id": ad_id},
                headers={"X-Admin-Key": "test-mgmt-token-12345"},
            )
            assert r.status_code == 200
            assert r.get_json()["deleted"]

            # Verify deleted
            r = c.get("/api/earn/ads?placement=earn")
            assert len(r.get_json()["ads"]) == 0

    def test_create_ad_requires_admin_key(self, store):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        os.environ["EARN_MGMT_TOKEN"] = "test-mgmt-token-12345"

        from services.earn_account import register_earn_account_routes
        register_earn_account_routes(app, store)

        with app.test_client() as c:
            r = c.post(
                "/api/earn/ads/create",
                json={"title": "X", "image_url": "https://i.png", "target_url": "https://t.com"},
            )
            assert r.status_code == 403

            r = c.post(
                "/api/earn/ads/create",
                json={"title": "X", "image_url": "https://i.png", "target_url": "https://t.com"},
                headers={"X-Admin-Key": "wrong-key"},
            )
            assert r.status_code == 403
