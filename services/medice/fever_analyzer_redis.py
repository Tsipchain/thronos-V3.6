import os
import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

FEVER_THRESHOLD       = 38.0
HIGH_FEVER_THRESHOLD  = 39.0
COOL_READINGS_TO_END  = 6      # ~30 min at 5-min intervals
ANTIPYRETIC_INTERVAL_H = 4

# Key prefixes - all instances share the same Redis namespace
_ACTIVE      = "medice:fever:active:"       # patient_id -> fever_event_id
_COOL        = "medice:fever:cool:"         # patient_id -> int (counter)
_ANTIPYRETIC = "medice:fever:antipyretic:"  # patient_id -> ISO timestamp


class RedisFeverAnalyzer:
    """
    Redis-backed fever state machine.
    Safe to run across multiple FastAPI instances (Railway replicas).
    """

    def __init__(self):
        self._r: Optional[aioredis.Redis] = None

    async def connect(self):
        self._r = await aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        await self._r.ping()
        logger.info("RedisFeverAnalyzer connected: %s", REDIS_URL)

    async def close(self):
        if self._r:
            await self._r.aclose()

    # ------------------------------------------------------------------
    # Core analysis (called on every incoming reading)
    # ------------------------------------------------------------------

    async def analyze(self, patient_id: str, temp: float, ts: datetime) -> dict:
        is_fever       = temp >= FEVER_THRESHOLD
        active_fever_id = await self._r.get(f"{_ACTIVE}{patient_id}")

        result = {
            "is_fever":                  is_fever,
            "is_new_fever":              False,
            "is_fever_ending":           False,
            "send_fever_alert":          False,
            "send_antipyretic_reminder": False,
            "fever_level":               self._classify(temp),
            "active_fever_id":           active_fever_id,
        }

        if is_fever:
            # Reset cool-down counter atomically
            await self._r.delete(f"{_COOL}{patient_id}")

            if not active_fever_id:
                result["is_new_fever"]     = True
                result["send_fever_alert"] = True
                logger.info("New fever patient=%s temp=%.1f", patient_id, temp)

            if await self._should_remind_antipyretic(patient_id, temp, ts):
                result["send_antipyretic_reminder"] = True
                await self._r.set(
                    f"{_ANTIPYRETIC}{patient_id}",
                    ts.isoformat(),
                    ex=86400 * 7,
                )
        else:
            # Increment consecutive-normal counter
            pipe = self._r.pipeline()
            pipe.incr(f"{_COOL}{patient_id}")
            pipe.expire(f"{_COOL}{patient_id}", 3600)   # auto-clear after 1h of no readings
            cool, _ = await pipe.execute()

            if active_fever_id and cool >= COOL_READINGS_TO_END:
                result["is_fever_ending"] = True
                logger.info("Fever ending patient=%s", patient_id)

        return result

    # ------------------------------------------------------------------
    # Lifecycle hooks called by the API after DB writes
    # ------------------------------------------------------------------

    async def register_fever_started(self, patient_id: str, event_id: str):
        await self._r.set(f"{_ACTIVE}{patient_id}", event_id, ex=86400 * 7)

    async def register_fever_ended(self, patient_id: str):
        await self._r.delete(
            f"{_ACTIVE}{patient_id}",
            f"{_COOL}{patient_id}",
            f"{_ANTIPYRETIC}{patient_id}",
        )

    async def register_antipyretic_given(self, patient_id: str, ts: datetime):
        await self._r.set(f"{_ANTIPYRETIC}{patient_id}", ts.isoformat(), ex=86400 * 2)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def active_fever_count(self) -> int:
        keys = await self._r.keys(f"{_ACTIVE}*")
        return len(keys)

    async def is_fever_active(self, patient_id: str) -> bool:
        return bool(await self._r.exists(f"{_ACTIVE}{patient_id}"))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _classify(self, temp: float) -> str:
        if temp >= HIGH_FEVER_THRESHOLD:
            return "high_fever"
        if temp >= FEVER_THRESHOLD:
            return "fever"
        return "normal"

    async def _should_remind_antipyretic(
        self, patient_id: str, temp: float, ts: datetime
    ) -> bool:
        if temp < FEVER_THRESHOLD:
            return False
        raw = await self._r.get(f"{_ANTIPYRETIC}{patient_id}")
        if not raw:
            return True
        last = datetime.fromisoformat(raw)
        return (ts - last).total_seconds() / 3600 >= ANTIPYRETIC_INTERVAL_H
