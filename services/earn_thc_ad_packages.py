"""
THC Ad Campaign Packages — fixed-price campaign bundles for the Earn ad marketplace.

Defines three THC packages (100 / 1,000 / 10,000) with view limits, duration,
and allowed placement positions. Campaign lifecycle:

  draft → active → paused → active → exhausted | expired | cancelled

Constraints:
  - Views decrement only on a verified, unique view event (not on load/prefetch).
  - Clicks counted only on real user click events.
  - Campaigns auto-stop when remaining views reach 0 or duration expires.
  - Ads shown only in allowed positions: earn, clubs, news.
  - Wallet PWA/APK ad-free except Earn section.
  - THC charging requires an existing safe escrow flow (EarnAccountStore.escrow_*).
  - No direct THC deduction here — purchase creates an escrow intent that the
    caller must execute through the wallet-signed escrow flow.

BLOCKER: This module does NOT call earn_account.py directly. Integration with
EarnAccountStore.escrow_create_intent / escrow_execute requires changes to
earn_account.py (adding package-aware campaign creation) or server.py (adding
API routes). Those changes are left as blockers for discussion.

Design constraints:
  - No secrets in source.
  - No simulated success or fabricated transactions.
  - No money movement without idempotency and receipt.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class PackageTier(Enum):
    STARTER = "starter"
    GROWTH = "growth"
    PREMIUM = "premium"


ALLOWED_PLACEMENTS = frozenset({"earn", "clubs", "news"})

FORBIDDEN_SURFACES = frozenset({
    "wallet_home",
    "wallet_send",
    "wallet_receive",
    "wallet_stake",
    "wallet_settings",
    "pwa_home",
    "apk_home",
})


@dataclass(frozen=True)
class PackageDefinition:
    tier: PackageTier
    thc_cost: Decimal
    max_views: int
    max_duration_days: int
    allowed_placements: frozenset[str] = field(default_factory=lambda: ALLOWED_PLACEMENTS)


PACKAGES: dict[PackageTier, PackageDefinition] = {
    PackageTier.STARTER: PackageDefinition(
        tier=PackageTier.STARTER,
        thc_cost=Decimal("100"),
        max_views=10_000,
        max_duration_days=7,
    ),
    PackageTier.GROWTH: PackageDefinition(
        tier=PackageTier.GROWTH,
        thc_cost=Decimal("1000"),
        max_views=100_000,
        max_duration_days=30,
    ),
    PackageTier.PREMIUM: PackageDefinition(
        tier=PackageTier.PREMIUM,
        thc_cost=Decimal("10000"),
        max_views=1_000_000,
        max_duration_days=90,
    ),
}


class CampaignState(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


TERMINAL_STATES = frozenset({
    CampaignState.EXHAUSTED,
    CampaignState.EXPIRED,
    CampaignState.CANCELLED,
})


class PackageCampaignError(Exception):
    pass


@dataclass
class PackageCampaign:
    campaign_id: str
    advertiser_id: str
    package_tier: PackageTier
    thc_cost: Decimal
    state: CampaignState
    remaining_views: int
    max_views: int
    total_impressions: int
    total_clicks: int
    unique_viewers: set[str]
    placement: str
    expires_at: int
    created_at: int
    escrow_intent_id: str | None = None
    escrow_receipt_id: str | None = None

    def is_servable(self) -> bool:
        if self.state != CampaignState.ACTIVE:
            return False
        if self.remaining_views <= 0:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "advertiser_id": self.advertiser_id,
            "package_tier": self.package_tier.value,
            "thc_cost": str(self.thc_cost),
            "state": self.state.value,
            "remaining_views": self.remaining_views,
            "max_views": self.max_views,
            "total_impressions": self.total_impressions,
            "total_clicks": self.total_clicks,
            "unique_viewer_count": len(self.unique_viewers),
            "placement": self.placement,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "escrow_intent_id": self.escrow_intent_id,
            "escrow_receipt_id": self.escrow_receipt_id,
        }


class PackageCampaignStore:
    """In-memory store for package campaigns. Production would use SQLite via EarnAccountStore."""

    def __init__(self) -> None:
        self._campaigns: dict[str, PackageCampaign] = {}

    def create_campaign(
        self,
        *,
        advertiser_id: str,
        tier: str,
        placement: str,
        duration_days: int | None = None,
    ) -> PackageCampaign:
        try:
            pkg_tier = PackageTier(tier)
        except ValueError:
            raise PackageCampaignError(
                f"invalid_tier:{tier}:must_be_starter|growth|premium"
            )

        pkg = PACKAGES[pkg_tier]

        if placement not in ALLOWED_PLACEMENTS:
            raise PackageCampaignError(
                f"forbidden_placement:{placement}:allowed={','.join(sorted(ALLOWED_PLACEMENTS))}"
            )

        if duration_days is not None:
            if duration_days < 1 or duration_days > pkg.max_duration_days:
                raise PackageCampaignError(
                    f"invalid_duration:{duration_days}:max={pkg.max_duration_days}"
                )
        else:
            duration_days = pkg.max_duration_days

        now = int(time.time())
        campaign = PackageCampaign(
            campaign_id=f"pkgc_{uuid.uuid4().hex[:16]}",
            advertiser_id=advertiser_id,
            package_tier=pkg_tier,
            thc_cost=pkg.thc_cost,
            state=CampaignState.DRAFT,
            remaining_views=pkg.max_views,
            max_views=pkg.max_views,
            total_impressions=0,
            total_clicks=0,
            unique_viewers=set(),
            placement=placement,
            expires_at=now + duration_days * 86400,
            created_at=now,
        )
        self._campaigns[campaign.campaign_id] = campaign
        return campaign

    def get_campaign(self, campaign_id: str) -> PackageCampaign | None:
        return self._campaigns.get(campaign_id)

    def activate_campaign(
        self, campaign_id: str, *, escrow_receipt_id: str,
    ) -> PackageCampaign:
        c = self._campaigns.get(campaign_id)
        if not c:
            raise PackageCampaignError("campaign_not_found")
        if c.state != CampaignState.DRAFT:
            raise PackageCampaignError(
                f"cannot_activate:state={c.state.value}:expected=draft"
            )
        if not escrow_receipt_id:
            raise PackageCampaignError("escrow_receipt_required")
        c.state = CampaignState.ACTIVE
        c.escrow_receipt_id = escrow_receipt_id
        return c

    def pause_campaign(self, campaign_id: str, advertiser_id: str) -> PackageCampaign:
        c = self._campaigns.get(campaign_id)
        if not c or c.advertiser_id != advertiser_id:
            raise PackageCampaignError("campaign_not_found")
        if c.state != CampaignState.ACTIVE:
            raise PackageCampaignError("only_active_campaigns_can_pause")
        c.state = CampaignState.PAUSED
        return c

    def resume_campaign(self, campaign_id: str, advertiser_id: str) -> PackageCampaign:
        c = self._campaigns.get(campaign_id)
        if not c or c.advertiser_id != advertiser_id:
            raise PackageCampaignError("campaign_not_found")
        if c.state != CampaignState.PAUSED:
            raise PackageCampaignError("only_paused_campaigns_can_resume")
        if c.remaining_views <= 0:
            c.state = CampaignState.EXHAUSTED
            raise PackageCampaignError("campaign_exhausted_cannot_resume")
        if time.time() > c.expires_at:
            c.state = CampaignState.EXPIRED
            raise PackageCampaignError("campaign_expired_cannot_resume")
        c.state = CampaignState.ACTIVE
        return c

    def cancel_campaign(self, campaign_id: str, advertiser_id: str) -> PackageCampaign:
        c = self._campaigns.get(campaign_id)
        if not c or c.advertiser_id != advertiser_id:
            raise PackageCampaignError("campaign_not_found")
        if c.state in TERMINAL_STATES:
            raise PackageCampaignError(f"already_terminal:{c.state.value}")
        c.state = CampaignState.CANCELLED
        return c

    def record_view(
        self, campaign_id: str, *, viewer_id: str,
    ) -> dict[str, Any]:
        c = self._campaigns.get(campaign_id)
        if not c:
            raise PackageCampaignError("campaign_not_found")

        self._check_auto_stop(c)
        if not c.is_servable():
            raise PackageCampaignError(f"campaign_not_servable:state={c.state.value}")

        is_unique = viewer_id not in c.unique_viewers
        c.unique_viewers.add(viewer_id)
        c.total_impressions += 1

        if is_unique:
            c.remaining_views -= 1

        self._check_auto_stop(c)

        return {
            "campaign_id": campaign_id,
            "is_unique": is_unique,
            "remaining_views": c.remaining_views,
            "state": c.state.value,
        }

    def record_click(
        self, campaign_id: str, *, viewer_id: str,
    ) -> dict[str, Any]:
        c = self._campaigns.get(campaign_id)
        if not c:
            raise PackageCampaignError("campaign_not_found")
        if c.state not in (CampaignState.ACTIVE, CampaignState.PAUSED):
            raise PackageCampaignError(f"campaign_not_clickable:state={c.state.value}")

        c.total_clicks += 1
        return {
            "campaign_id": campaign_id,
            "total_clicks": c.total_clicks,
        }

    def serve_ads(self, *, placement: str) -> list[dict[str, Any]]:
        if placement in FORBIDDEN_SURFACES:
            return []

        results = []
        now = time.time()
        for c in self._campaigns.values():
            if c.state != CampaignState.ACTIVE:
                continue
            if c.placement != placement:
                continue
            if c.remaining_views <= 0:
                c.state = CampaignState.EXHAUSTED
                continue
            if now > c.expires_at:
                c.state = CampaignState.EXPIRED
                continue
            results.append(c.to_dict())
        return results

    def _check_auto_stop(self, c: PackageCampaign) -> None:
        if c.state not in (CampaignState.ACTIVE, CampaignState.PAUSED):
            return
        if c.remaining_views <= 0:
            c.state = CampaignState.EXHAUSTED
        elif time.time() > c.expires_at:
            c.state = CampaignState.EXPIRED
