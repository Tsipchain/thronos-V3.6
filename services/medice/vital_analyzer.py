"""Redis-backed analyzer for temperature + SpO2 + BPM across Railway replicas."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional
import aioredis

# Thresholds
FEVER_THRESHOLD        = 38.0
HIGH_FEVER_THRESHOLD   = 39.0
SPO2_LOW               = 94.0
SPO2_CRITICAL          = 90.0
BPM_LOW_CHILD          = 60
BPM_HIGH_CHILD         = 130
COOL_READINGS_TO_END   = 6
ANTIPYRETIC_INTERVAL_H = 4

# Redis key prefixes
_ACTIVE      = "medice:fever:active:"
_COOL        = "medice:fever:cool:"
_ANTIPYRETIC = "medice:fever:antipyretic:"
_SPO2_MIN    = "medice:spo2:min:"
_BPM_SUM     = "medice:bpm:sum:"
_BPM_CNT     = "medice:bpm:cnt:"


class VitalAnalyzer:
    def __init__(self, redis: aioredis.Redis):
        self.r = redis

    # ── Temperature analysis ────────────────────────────────────────────────
    async def analyze_temp(self, patient_id: str, temp: float, ts: datetime) -> dict:
        pid = str(patient_id)
        is_fever      = temp >= FEVER_THRESHOLD
        is_high_fever = temp >= HIGH_FEVER_THRESHOLD
        fever_level   = "high_fever" if is_high_fever else ("fever" if is_fever else "normal")

        active_fever_id: Optional[str] = await self.r.get(_ACTIVE + pid)
        is_new_fever = False
        is_fever_ending = False
        send_fever_alert = False
        send_antipyretic = False

        if is_fever:
            await self.r.delete(_COOL + pid)
            if not active_fever_id:
                is_new_fever = True
                send_fever_alert = True

            # Antipyretic reminder every 4h
            last_anti_raw = await self.r.get(_ANTIPYRETIC + pid)
            if last_anti_raw:
                last_anti = datetime.fromisoformat(last_anti_raw.decode())
                if (ts - last_anti) >= timedelta(hours=ANTIPYRETIC_INTERVAL_H):
                    send_antipyretic = True
            else:
                send_antipyretic = bool(active_fever_id)
        else:
            cool_count = await self.r.incr(_COOL + pid)
            await self.r.expire(_COOL + pid, 3600)
            if active_fever_id and cool_count >= COOL_READINGS_TO_END:
                is_fever_ending = True
                await self.r.delete(_ACTIVE + pid)
                await self.r.delete(_COOL + pid)
                await self.r.delete(_ANTIPYRETIC + pid)
                await self.r.delete(_SPO2_MIN + pid)
                await self.r.delete(_BPM_SUM + pid)
                await self.r.delete(_BPM_CNT + pid)

        return dict(
            is_fever=is_fever,
            is_new_fever=is_new_fever,
            is_fever_ending=is_fever_ending,
            send_fever_alert=send_fever_alert,
            send_antipyretic_reminder=send_antipyretic,
            fever_level=fever_level,
            active_fever_id=active_fever_id.decode() if active_fever_id else None,
        )

    # ── SpO2 + BPM analysis ─────────────────────────────────────────────────
    async def analyze_vitals(self, patient_id: str,
                             spo2: Optional[float], spo2_valid: bool,
                             bpm: Optional[int],  bpm_valid: bool) -> dict:
        pid = str(patient_id)
        spo2_alert = False
        spo2_level = "normal"
        hr_alert   = False
        hr_level   = "normal"

        if spo2_valid and spo2 is not None:
            if spo2 < SPO2_CRITICAL:
                spo2_alert = True
                spo2_level = "critical"
            elif spo2 < SPO2_LOW:
                spo2_alert = True
                spo2_level = "low"

            # Track minimum SpO2 during active fever
            cur_min_raw = await self.r.get(_SPO2_MIN + pid)
            cur_min = float(cur_min_raw) if cur_min_raw else 999.0
            if spo2 < cur_min:
                await self.r.set(_SPO2_MIN + pid, str(spo2), ex=86400)

        if bpm_valid and bpm is not None:
            if bpm < BPM_LOW_CHILD:
                hr_alert = True
                hr_level = "bradycardia"
            elif bpm > BPM_HIGH_CHILD:
                hr_alert = True
                hr_level = "tachycardia"

            # Track average BPM during active fever
            await self.r.incrbyfloat(_BPM_SUM + pid, bpm)
            await self.r.incr(_BPM_CNT + pid)
            await self.r.expire(_BPM_SUM + pid, 86400)
            await self.r.expire(_BPM_CNT + pid, 86400)

        return dict(
            spo2_alert=spo2_alert,
            spo2_level=spo2_level,
            hr_alert=hr_alert,
            hr_level=hr_level,
            send_spo2_alert=spo2_alert,
        )

    async def register_fever_started(self, patient_id: str, event_id: str):
        await self.r.set(_ACTIVE + str(patient_id), event_id, ex=86400 * 3)

    async def register_antipyretic_given(self, patient_id: str, ts: datetime):
        await self.r.set(_ANTIPYRETIC + str(patient_id),
                         ts.isoformat(), ex=ANTIPYRETIC_INTERVAL_H * 3600 + 300)

    async def get_fever_vitals(self, patient_id: str) -> dict:
        """Return min SpO2 and avg BPM accumulated during current fever."""
        pid = str(patient_id)
        min_spo2_raw = await self.r.get(_SPO2_MIN + pid)
        bpm_sum_raw  = await self.r.get(_BPM_SUM + pid)
        bpm_cnt_raw  = await self.r.get(_BPM_CNT + pid)
        min_spo2 = float(min_spo2_raw) if min_spo2_raw else None
        avg_bpm  = None
        if bpm_sum_raw and bpm_cnt_raw:
            cnt = int(bpm_cnt_raw)
            avg_bpm = float(bpm_sum_raw) / cnt if cnt else None
        return {"min_spo2": min_spo2, "avg_bpm": avg_bpm}
