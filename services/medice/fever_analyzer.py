from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

FEVER_THRESHOLD       = 38.0   # degrees C
HIGH_FEVER_THRESHOLD  = 39.0
# After 6 consecutive sub-threshold readings (~30 min at 5-min intervals) fever ends
COOL_READINGS_TO_END  = 6
# Hours between antipyretic reminders
ANTIPYRETIC_INTERVAL_H = 4


class FeverAnalyzer:
    """Stateful per-patient fever tracking (runs in-process)."""

    def __init__(self):
        self._active_fevers: Dict[str, str]      = {}   # patient_id -> fever_event_id
        self._cool_count:    Dict[str, int]      = {}   # consecutive sub-38 readings
        self._last_antipyretic: Dict[str, datetime] = {}

    # ------------------------------------------------------------------
    def analyze(self, patient_id: str, temp: float, ts: datetime) -> dict:
        """
        Returns action dict consumed by the API to decide what to do next.
        """
        is_fever = temp >= FEVER_THRESHOLD
        result = {
            "is_fever":                is_fever,
            "is_new_fever":            False,
            "is_fever_ending":         False,
            "send_fever_alert":        False,
            "send_antipyretic_reminder": False,
            "fever_level":             self._classify(temp),
            "active_fever_id":         self._active_fevers.get(patient_id),
        }

        if is_fever:
            self._cool_count[patient_id] = 0
            if patient_id not in self._active_fevers:
                result["is_new_fever"]     = True
                result["send_fever_alert"] = True
                logger.info("New fever for patient %s: %.1f C", patient_id, temp)
            if self._should_remind_antipyretic(patient_id, temp, ts):
                result["send_antipyretic_reminder"] = True
                self._last_antipyretic[patient_id] = ts
        else:
            n = self._cool_count.get(patient_id, 0) + 1
            self._cool_count[patient_id] = n
            if patient_id in self._active_fevers and n >= COOL_READINGS_TO_END:
                result["is_fever_ending"] = True
                logger.info("Fever ending for patient %s", patient_id)

        return result

    # ------------------------------------------------------------------
    def register_fever_started(self, patient_id: str, fever_event_id: str):
        self._active_fevers[patient_id] = fever_event_id

    def register_fever_ended(self, patient_id: str):
        self._active_fevers.pop(patient_id, None)
        self._cool_count.pop(patient_id, None)
        self._last_antipyretic.pop(patient_id, None)

    def register_antipyretic_given(self, patient_id: str, ts: datetime):
        self._last_antipyretic[patient_id] = ts

    @property
    def active_fever_patients(self) -> list:
        return list(self._active_fevers.keys())

    # ------------------------------------------------------------------
    def _classify(self, temp: float) -> str:
        if temp >= HIGH_FEVER_THRESHOLD:
            return "high_fever"
        if temp >= FEVER_THRESHOLD:
            return "fever"
        return "normal"

    def _should_remind_antipyretic(self, patient_id: str, temp: float, ts: datetime) -> bool:
        if temp < FEVER_THRESHOLD:
            return False
        last = self._last_antipyretic.get(patient_id)
        if last is None:
            return True
        return (ts - last).total_seconds() / 3600 >= ANTIPYRETIC_INTERVAL_H
