"""
Tests for THC Ad Campaign Packages.

Covers:
  1. Package creation with valid/invalid tiers
  2. Placement validation (allowed: earn, clubs, news; forbidden: wallet surfaces)
  3. Duration validation per tier
  4. Campaign lifecycle: draft → active → paused → resume → exhausted/expired/cancelled
  5. Purchase / double-submission prevention (escrow receipt required)
  6. View counting: only unique views decrement remaining
  7. Click counting: only on user gesture
  8. Package exhaustion: auto-stop when remaining_views reaches 0
  9. Duration expiry: auto-stop when expires_at passes
  10. Forbidden ad positions: wallet PWA/APK surfaces return no ads
"""
import time
import pytest
from decimal import Decimal
from unittest import mock

from services.earn_thc_ad_packages import (
    ALLOWED_PLACEMENTS,
    FORBIDDEN_SURFACES,
    PACKAGES,
    CampaignState,
    PackageCampaignError,
    PackageCampaignStore,
    PackageDefinition,
    PackageTier,
)


@pytest.fixture()
def store():
    return PackageCampaignStore()


@pytest.fixture()
def draft_campaign(store):
    return store.create_campaign(
        advertiser_id="adv_001",
        tier="starter",
        placement="earn",
    )


@pytest.fixture()
def active_campaign(store, draft_campaign):
    return store.activate_campaign(
        draft_campaign.campaign_id,
        escrow_receipt_id="esc_receipt_001",
    )


# ── 1. Package creation ───────────────────────────────────────────────

class TestPackageCreation:
    def test_create_starter(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
        )
        assert c.package_tier == PackageTier.STARTER
        assert c.thc_cost == Decimal("100")
        assert c.max_views == 10_000
        assert c.remaining_views == 10_000
        assert c.state == CampaignState.DRAFT

    def test_create_growth(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="growth", placement="clubs",
        )
        assert c.thc_cost == Decimal("1000")
        assert c.max_views == 100_000

    def test_create_premium(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="premium", placement="news",
        )
        assert c.thc_cost == Decimal("10000")
        assert c.max_views == 1_000_000

    def test_invalid_tier_rejected(self, store):
        with pytest.raises(PackageCampaignError, match="invalid_tier"):
            store.create_campaign(
                advertiser_id="adv_001", tier="mega", placement="earn",
            )

    def test_campaign_id_format(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
        )
        assert c.campaign_id.startswith("pkgc_")

    def test_three_packages_defined(self):
        assert len(PACKAGES) == 3
        for tier in PackageTier:
            assert tier in PACKAGES
            pkg = PACKAGES[tier]
            assert isinstance(pkg, PackageDefinition)
            assert pkg.thc_cost > 0
            assert pkg.max_views > 0
            assert pkg.max_duration_days > 0


# ── 2. Placement validation ───────────────────────────────────────────

class TestPlacementValidation:
    def test_earn_allowed(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
        )
        assert c.placement == "earn"

    def test_clubs_allowed(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="clubs",
        )
        assert c.placement == "clubs"

    def test_news_allowed(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="news",
        )
        assert c.placement == "news"

    def test_wallet_home_forbidden(self, store):
        with pytest.raises(PackageCampaignError, match="forbidden_placement"):
            store.create_campaign(
                advertiser_id="adv_001", tier="starter", placement="wallet_home",
            )

    def test_pwa_home_forbidden(self, store):
        with pytest.raises(PackageCampaignError, match="forbidden_placement"):
            store.create_campaign(
                advertiser_id="adv_001", tier="starter", placement="pwa_home",
            )

    def test_random_placement_forbidden(self, store):
        with pytest.raises(PackageCampaignError, match="forbidden_placement"):
            store.create_campaign(
                advertiser_id="adv_001", tier="starter", placement="homepage",
            )

    def test_allowed_placements_exactly_three(self):
        assert ALLOWED_PLACEMENTS == {"earn", "clubs", "news"}

    def test_forbidden_surfaces_include_wallet(self):
        for surface in ["wallet_home", "wallet_send", "wallet_receive",
                        "wallet_stake", "wallet_settings"]:
            assert surface in FORBIDDEN_SURFACES


# ── 3. Duration validation ────────────────────────────────────────────

class TestDurationValidation:
    def test_starter_default_duration(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
        )
        expected = int(time.time()) + 7 * 86400
        assert abs(c.expires_at - expected) < 2

    def test_growth_default_30_days(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="growth", placement="earn",
        )
        expected = int(time.time()) + 30 * 86400
        assert abs(c.expires_at - expected) < 2

    def test_premium_default_90_days(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="premium", placement="earn",
        )
        expected = int(time.time()) + 90 * 86400
        assert abs(c.expires_at - expected) < 2

    def test_custom_duration(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
            duration_days=3,
        )
        expected = int(time.time()) + 3 * 86400
        assert abs(c.expires_at - expected) < 2

    def test_duration_exceeds_max_rejected(self, store):
        with pytest.raises(PackageCampaignError, match="invalid_duration"):
            store.create_campaign(
                advertiser_id="adv_001", tier="starter", placement="earn",
                duration_days=30,
            )

    def test_zero_duration_rejected(self, store):
        with pytest.raises(PackageCampaignError, match="invalid_duration"):
            store.create_campaign(
                advertiser_id="adv_001", tier="starter", placement="earn",
                duration_days=0,
            )


# ── 4. Campaign lifecycle ────────────────────────────────────────────

class TestCampaignLifecycle:
    def test_draft_to_active(self, store, draft_campaign):
        c = store.activate_campaign(
            draft_campaign.campaign_id,
            escrow_receipt_id="esc_001",
        )
        assert c.state == CampaignState.ACTIVE
        assert c.escrow_receipt_id == "esc_001"

    def test_active_to_paused(self, store, active_campaign):
        c = store.pause_campaign(
            active_campaign.campaign_id, "adv_001",
        )
        assert c.state == CampaignState.PAUSED

    def test_paused_to_active(self, store, active_campaign):
        store.pause_campaign(active_campaign.campaign_id, "adv_001")
        c = store.resume_campaign(active_campaign.campaign_id, "adv_001")
        assert c.state == CampaignState.ACTIVE

    def test_cancel_from_draft(self, store, draft_campaign):
        c = store.cancel_campaign(draft_campaign.campaign_id, "adv_001")
        assert c.state == CampaignState.CANCELLED

    def test_cancel_from_active(self, store, active_campaign):
        c = store.cancel_campaign(active_campaign.campaign_id, "adv_001")
        assert c.state == CampaignState.CANCELLED

    def test_cannot_cancel_terminal(self, store, active_campaign):
        store.cancel_campaign(active_campaign.campaign_id, "adv_001")
        with pytest.raises(PackageCampaignError, match="already_terminal"):
            store.cancel_campaign(active_campaign.campaign_id, "adv_001")

    def test_wrong_owner_cannot_pause(self, store, active_campaign):
        with pytest.raises(PackageCampaignError, match="campaign_not_found"):
            store.pause_campaign(active_campaign.campaign_id, "adv_999")

    def test_wrong_owner_cannot_cancel(self, store, active_campaign):
        with pytest.raises(PackageCampaignError, match="campaign_not_found"):
            store.cancel_campaign(active_campaign.campaign_id, "adv_999")


# ── 5. Purchase / double-submission ──────────────────────────────────

class TestPurchaseGates:
    def test_activate_requires_escrow_receipt(self, store, draft_campaign):
        with pytest.raises(PackageCampaignError, match="escrow_receipt_required"):
            store.activate_campaign(
                draft_campaign.campaign_id, escrow_receipt_id="",
            )

    def test_activate_non_draft_rejected(self, store, active_campaign):
        with pytest.raises(PackageCampaignError, match="cannot_activate"):
            store.activate_campaign(
                active_campaign.campaign_id,
                escrow_receipt_id="esc_duplicate",
            )

    def test_activate_nonexistent_rejected(self, store):
        with pytest.raises(PackageCampaignError, match="campaign_not_found"):
            store.activate_campaign(
                "pkgc_nonexistent", escrow_receipt_id="esc_001",
            )

    def test_double_activate_rejected(self, store, draft_campaign):
        store.activate_campaign(
            draft_campaign.campaign_id, escrow_receipt_id="esc_001",
        )
        with pytest.raises(PackageCampaignError, match="cannot_activate"):
            store.activate_campaign(
                draft_campaign.campaign_id, escrow_receipt_id="esc_002",
            )


# ── 6. View counting ─────────────────────────────────────────────────

class TestViewCounting:
    def test_unique_view_decrements_remaining(self, store, active_campaign):
        result = store.record_view(
            active_campaign.campaign_id, viewer_id="user_001",
        )
        assert result["is_unique"] is True
        assert result["remaining_views"] == active_campaign.max_views - 1

    def test_repeat_view_does_not_decrement(self, store, active_campaign):
        store.record_view(active_campaign.campaign_id, viewer_id="user_001")
        result = store.record_view(
            active_campaign.campaign_id, viewer_id="user_001",
        )
        assert result["is_unique"] is False
        assert result["remaining_views"] == active_campaign.max_views - 1

    def test_different_viewers_both_decrement(self, store, active_campaign):
        store.record_view(active_campaign.campaign_id, viewer_id="user_001")
        result = store.record_view(
            active_campaign.campaign_id, viewer_id="user_002",
        )
        assert result["is_unique"] is True
        assert result["remaining_views"] == active_campaign.max_views - 2

    def test_impressions_always_increment(self, store, active_campaign):
        store.record_view(active_campaign.campaign_id, viewer_id="user_001")
        store.record_view(active_campaign.campaign_id, viewer_id="user_001")
        c = store.get_campaign(active_campaign.campaign_id)
        assert c.total_impressions == 2

    def test_view_on_non_active_rejected(self, store, draft_campaign):
        with pytest.raises(PackageCampaignError, match="campaign_not_servable"):
            store.record_view(draft_campaign.campaign_id, viewer_id="user_001")

    def test_view_on_nonexistent_rejected(self, store):
        with pytest.raises(PackageCampaignError, match="campaign_not_found"):
            store.record_view("pkgc_none", viewer_id="user_001")


# ── 7. Click counting ────────────────────────────────────────────────

class TestClickCounting:
    def test_click_increments_counter(self, store, active_campaign):
        result = store.record_click(
            active_campaign.campaign_id, viewer_id="user_001",
        )
        assert result["total_clicks"] == 1

    def test_multiple_clicks_counted(self, store, active_campaign):
        store.record_click(active_campaign.campaign_id, viewer_id="user_001")
        result = store.record_click(
            active_campaign.campaign_id, viewer_id="user_001",
        )
        assert result["total_clicks"] == 2

    def test_click_on_terminal_rejected(self, store, active_campaign):
        store.cancel_campaign(active_campaign.campaign_id, "adv_001")
        with pytest.raises(PackageCampaignError, match="campaign_not_clickable"):
            store.record_click(active_campaign.campaign_id, viewer_id="user_001")


# ── 8. Package exhaustion ────────────────────────────────────────────

class TestPackageExhaustion:
    def test_exhaustion_auto_stops(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
        )
        store.activate_campaign(c.campaign_id, escrow_receipt_id="esc_001")
        c_obj = store.get_campaign(c.campaign_id)
        c_obj.remaining_views = 1

        result = store.record_view(c.campaign_id, viewer_id="last_viewer")
        assert result["remaining_views"] == 0
        assert result["state"] == "exhausted"

        c_after = store.get_campaign(c.campaign_id)
        assert c_after.state == CampaignState.EXHAUSTED

    def test_exhausted_cannot_serve(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
        )
        store.activate_campaign(c.campaign_id, escrow_receipt_id="esc_001")
        c_obj = store.get_campaign(c.campaign_id)
        c_obj.remaining_views = 0
        c_obj.state = CampaignState.EXHAUSTED

        with pytest.raises(PackageCampaignError, match="campaign_not_servable"):
            store.record_view(c.campaign_id, viewer_id="user_001")

    def test_exhausted_not_in_serve_results(self, store):
        c = store.create_campaign(
            advertiser_id="adv_001", tier="starter", placement="earn",
        )
        store.activate_campaign(c.campaign_id, escrow_receipt_id="esc_001")
        c_obj = store.get_campaign(c.campaign_id)
        c_obj.remaining_views = 0

        ads = store.serve_ads(placement="earn")
        assert len(ads) == 0

    def test_exhausted_cannot_resume(self, store, active_campaign):
        store.pause_campaign(active_campaign.campaign_id, "adv_001")
        c = store.get_campaign(active_campaign.campaign_id)
        c.remaining_views = 0
        with pytest.raises(PackageCampaignError, match="campaign_exhausted"):
            store.resume_campaign(active_campaign.campaign_id, "adv_001")


# ── 9. Duration expiry ───────────────────────────────────────────────

class TestDurationExpiry:
    def test_expired_auto_stops_on_view(self, store, active_campaign):
        c = store.get_campaign(active_campaign.campaign_id)
        c.expires_at = int(time.time()) - 1

        with pytest.raises(PackageCampaignError, match="campaign_not_servable"):
            store.record_view(active_campaign.campaign_id, viewer_id="user_001")
        assert c.state == CampaignState.EXPIRED

    def test_expired_not_in_serve_results(self, store, active_campaign):
        c = store.get_campaign(active_campaign.campaign_id)
        c.expires_at = int(time.time()) - 1

        ads = store.serve_ads(placement="earn")
        assert len(ads) == 0

    def test_expired_cannot_resume(self, store, active_campaign):
        store.pause_campaign(active_campaign.campaign_id, "adv_001")
        c = store.get_campaign(active_campaign.campaign_id)
        c.expires_at = int(time.time()) - 1
        with pytest.raises(PackageCampaignError, match="campaign_expired"):
            store.resume_campaign(active_campaign.campaign_id, "adv_001")


# ── 10. Forbidden ad positions ───────────────────────────────────────

class TestForbiddenPositions:
    def test_wallet_home_returns_nothing(self, store, active_campaign):
        ads = store.serve_ads(placement="wallet_home")
        assert ads == []

    def test_wallet_send_returns_nothing(self, store, active_campaign):
        ads = store.serve_ads(placement="wallet_send")
        assert ads == []

    def test_pwa_home_returns_nothing(self, store, active_campaign):
        ads = store.serve_ads(placement="pwa_home")
        assert ads == []

    def test_apk_home_returns_nothing(self, store, active_campaign):
        ads = store.serve_ads(placement="apk_home")
        assert ads == []

    def test_earn_returns_active_campaign(self, store, active_campaign):
        ads = store.serve_ads(placement="earn")
        assert len(ads) == 1
        assert ads[0]["campaign_id"] == active_campaign.campaign_id


# ── 11. Serialization ────────────────────────────────────────────────

class TestSerialization:
    def test_to_dict_fields(self, store, active_campaign):
        d = active_campaign.to_dict()
        assert d["campaign_id"].startswith("pkgc_")
        assert d["package_tier"] == "starter"
        assert d["thc_cost"] == "100"
        assert d["state"] == "active"
        assert d["remaining_views"] == 10_000
        assert d["max_views"] == 10_000
        assert d["total_impressions"] == 0
        assert d["total_clicks"] == 0
        assert d["unique_viewer_count"] == 0
        assert d["placement"] == "earn"
        assert d["escrow_receipt_id"] == "esc_receipt_001"
