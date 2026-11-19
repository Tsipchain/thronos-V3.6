"""Fail-closed Gym reward settlement planning boundary.

This module binds verified Gym eligibility to an independently verified,
versioned quote and an authoritative funded reservation.  It deliberately has
no ledger, wallet, conversion, payout, signing, or broadcast dependency.  Its
terminal state is operator review; it cannot credit a user.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from services.earn_gym_eligibility_inbox import GymEligibilityInbox


class GymSettlementError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedGymRewardQuote:
    quote_id: str
    event_id: str
    earn_user_ref: str
    tenant_id: str
    source_asset: str
    source_amount: str
    reward_asset: str
    reward_amount: str
    pricing_version: str
    authority_ref: str
    expires_at: int


@dataclass(frozen=True)
class VerifiedGymFundingReservation:
    reservation_id: str
    event_id: str
    earn_user_ref: str
    tenant_id: str
    asset: str
    reserved_amount: str
    purpose: str
    authority_ref: str
    expires_at: int


class GymRewardQuoteVerifier(Protocol):
    def verify(
        self, eligibility: dict[str, Any], candidate: dict[str, Any],
    ) -> VerifiedGymRewardQuote:
        """Return authoritative evidence or raise on any verification failure."""


class GymFundingReservationVerifier(Protocol):
    def verify(
        self,
        eligibility: dict[str, Any],
        quote: VerifiedGymRewardQuote,
        candidate: dict[str, Any],
    ) -> VerifiedGymFundingReservation:
        """Return authoritative reserve evidence or raise on failure."""


def _amount(value: str, *, name: str, scale: int = 6) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GymSettlementError(f"invalid_{name}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise GymSettlementError(f"invalid_{name}")
    if parsed.as_tuple().exponent < -scale:
        raise GymSettlementError(f"invalid_{name}_precision")
    return parsed


class GymFundedSettlementPlanner:
    """Durable plans ending at operator review, never at user credit."""

    def __init__(
        self,
        db_path: str | Path,
        inbox: GymEligibilityInbox,
        quote_verifier: GymRewardQuoteVerifier,
        funding_verifier: GymFundingReservationVerifier,
    ) -> None:
        if inbox is None or quote_verifier is None or funding_verifier is None:
            raise GymSettlementError("gym_settlement_not_configured")
        self._db_path = str(db_path)
        self._inbox = inbox
        self._quote_verifier = quote_verifier
        self._funding_verifier = funding_verifier
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _tx(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._tx() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS earn_gym_settlement_plans (
                    event_id          TEXT PRIMARY KEY,
                    earn_user_ref     TEXT NOT NULL,
                    tenant_id         TEXT NOT NULL,
                    challenge_id      TEXT NOT NULL,
                    source_amount     TEXT NOT NULL,
                    quote_id          TEXT NOT NULL UNIQUE,
                    reward_asset      TEXT NOT NULL CHECK(reward_asset='THC'),
                    reward_amount     TEXT NOT NULL,
                    pricing_version   TEXT NOT NULL,
                    quote_authority   TEXT NOT NULL,
                    quote_expires_at  INTEGER NOT NULL,
                    reservation_id    TEXT NOT NULL UNIQUE,
                    reserved_amount   TEXT NOT NULL,
                    funding_authority TEXT NOT NULL,
                    reserve_expires_at INTEGER NOT NULL,
                    state             TEXT NOT NULL
                        CHECK(state='operator_review_required'),
                    plan_sha256       TEXT NOT NULL,
                    created_at        INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS earn_gym_settlement_audit (
                    audit_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id      TEXT NOT NULL,
                    action        TEXT NOT NULL,
                    plan_sha256   TEXT NOT NULL,
                    recorded_at   INTEGER NOT NULL,
                    UNIQUE(event_id, action, plan_sha256)
                );
                """
            )

    @staticmethod
    def _public(row: sqlite3.Row, *, idempotent: bool) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "earn_user_ref": row["earn_user_ref"],
            "tenant_id": row["tenant_id"],
            "challenge_id": row["challenge_id"],
            "source_asset": "T2E_ELIGIBILITY_ONLY",
            "source_amount": row["source_amount"],
            "quote_id": row["quote_id"],
            "reward_asset": row["reward_asset"],
            "reward_amount": row["reward_amount"],
            "pricing_version": row["pricing_version"],
            "reservation_id": row["reservation_id"],
            "state": row["state"],
            "idempotent": idempotent,
            "credit_authorized": False,
            "payout_enabled": False,
        }

    @staticmethod
    def _validate_quote(
        eligibility: dict[str, Any], quote: VerifiedGymRewardQuote, now: int,
    ) -> Decimal:
        if not isinstance(quote, VerifiedGymRewardQuote):
            raise GymSettlementError("unverified_gym_reward_quote")
        if (
            quote.event_id != eligibility["event_id"]
            or quote.earn_user_ref != eligibility["earn_user_ref"]
            or quote.tenant_id != eligibility["tenant_id"]
            or quote.source_asset != "T2E_ELIGIBILITY_ONLY"
            or quote.source_amount != eligibility["reward_t2e"]
            or quote.reward_asset != "THC"
        ):
            raise GymSettlementError("gym_quote_binding_mismatch")
        if not quote.quote_id or not quote.pricing_version or not quote.authority_ref:
            raise GymSettlementError("incomplete_gym_reward_quote")
        if quote.expires_at <= now:
            raise GymSettlementError("gym_reward_quote_expired")
        _amount(quote.source_amount, name="gym_source_amount")
        return _amount(quote.reward_amount, name="gym_reward_amount")

    @staticmethod
    def _validate_funding(
        eligibility: dict[str, Any],
        quote: VerifiedGymRewardQuote,
        funding: VerifiedGymFundingReservation,
        reward_amount: Decimal,
        now: int,
    ) -> None:
        if not isinstance(funding, VerifiedGymFundingReservation):
            raise GymSettlementError("unverified_gym_funding_reservation")
        if (
            funding.event_id != eligibility["event_id"]
            or funding.earn_user_ref != eligibility["earn_user_ref"]
            or funding.tenant_id != eligibility["tenant_id"]
            or funding.asset != "THC"
            or funding.purpose != "gym_reward_settlement"
        ):
            raise GymSettlementError("gym_funding_binding_mismatch")
        if not funding.reservation_id or not funding.authority_ref:
            raise GymSettlementError("incomplete_gym_funding_reservation")
        if funding.expires_at <= now:
            raise GymSettlementError("gym_funding_reservation_expired")
        if _amount(
            funding.reserved_amount, name="gym_reserved_amount",
        ) < reward_amount:
            raise GymSettlementError("insufficient_gym_funding_reservation")

    def prepare(
        self,
        event_id: str,
        *,
        expected_earn_user_ref: str,
        quote_candidate: dict[str, Any],
        funding_candidate: dict[str, Any],
        now: int | None = None,
    ) -> dict[str, Any]:
        eligibility = self._inbox.by_event(event_id)
        if eligibility is None:
            raise GymSettlementError("gym_eligibility_not_found")
        if eligibility["earn_user_ref"] != expected_earn_user_ref:
            raise GymSettlementError("wrong_earn_account")
        if eligibility["state"] != "verified_eligibility_only":
            raise GymSettlementError("gym_eligibility_not_verified")
        current = int(time.time()) if now is None else int(now)
        try:
            quote = self._quote_verifier.verify(eligibility, quote_candidate)
            reward_amount = self._validate_quote(eligibility, quote, current)
            funding = self._funding_verifier.verify(
                eligibility, quote, funding_candidate,
            )
            self._validate_funding(
                eligibility, quote, funding, reward_amount, current,
            )
        except GymSettlementError:
            raise
        except Exception as exc:
            raise GymSettlementError("gym_settlement_evidence_unavailable") from exc

        canonical = {
            "eligibility": {
                key: eligibility[key]
                for key in (
                    "event_id", "earn_user_ref", "tenant_id", "challenge_id",
                    "reward_t2e", "completed_at", "source", "state",
                )
            },
            "quote": asdict(quote),
            "funding": asdict(funding),
            "state": "operator_review_required",
        }
        plan_hash = hashlib.sha256(json.dumps(
            canonical, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        with self._tx() as connection:
            existing = connection.execute(
                "SELECT * FROM earn_gym_settlement_plans WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if existing:
                if existing["plan_sha256"] != plan_hash:
                    raise GymSettlementError("gym_settlement_plan_conflict")
                return self._public(existing, idempotent=True)
            try:
                connection.execute(
                    """INSERT INTO earn_gym_settlement_plans
                       (event_id,earn_user_ref,tenant_id,challenge_id,
                        source_amount,quote_id,reward_asset,reward_amount,
                        pricing_version,quote_authority,quote_expires_at,
                        reservation_id,reserved_amount,funding_authority,
                        reserve_expires_at,state,plan_sha256,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                               'operator_review_required',?,?)""",
                    (
                        event_id, eligibility["earn_user_ref"],
                        eligibility["tenant_id"], eligibility["challenge_id"],
                        eligibility["reward_t2e"], quote.quote_id,
                        quote.reward_asset, quote.reward_amount,
                        quote.pricing_version, quote.authority_ref,
                        quote.expires_at, funding.reservation_id,
                        funding.reserved_amount, funding.authority_ref,
                        funding.expires_at, plan_hash, current,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise GymSettlementError("gym_settlement_evidence_reused") from exc
            connection.execute(
                """INSERT INTO earn_gym_settlement_audit
                   (event_id,action,plan_sha256,recorded_at)
                   VALUES (?,'prepared_for_operator_review',?,?)""",
                (event_id, plan_hash, current),
            )
            stored = connection.execute(
                "SELECT * FROM earn_gym_settlement_plans WHERE event_id=?",
                (event_id,),
            ).fetchone()
            return self._public(stored, idempotent=False)

    def recovery_status(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT event_id,state,created_at
                   FROM earn_gym_settlement_plans ORDER BY created_at,event_id"""
            ).fetchall()
            return {
                "operator_review_required": len(rows),
                "plans": [dict(row) for row in rows],
                "credit_authorized": False,
                "payout_enabled": False,
            }
        finally:
            connection.close()
