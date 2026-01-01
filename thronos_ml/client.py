"""Minimal Python client for the AI Interaction Ledger APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass
class ThronosClient:
    api_key: str
    node_url: str

    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def log_interaction(self, **payload: Any) -> Dict[str, Any]:
        url = f"{self.node_url}/api/v1/ai/log"
        resp = requests.post(url, headers=self._headers(), data=json.dumps(payload), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def log_score(self, **payload: Any) -> Dict[str, Any]:
        url = f"{self.node_url}/api/v1/ai/score"
        resp = requests.post(url, headers=self._headers(), data=json.dumps(payload), timeout=10)
        resp.raise_for_status()
        return resp.json()

