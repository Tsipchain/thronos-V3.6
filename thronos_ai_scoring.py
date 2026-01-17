"""Lightweight scoring helper that wraps scikit-learn models.

The scorer is intentionally defensive: if the scikit-learn dependency or a
trained pickle file is missing, it falls back to a deterministic heuristic so
the backend can continue serving traffic.
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    from sklearn.linear_model import LogisticRegression  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    LogisticRegression = None  # type: ignore


MODEL_DIR = os.getenv("AI_MODEL_DIR", os.path.join(os.getenv("DATA_DIR", os.path.dirname(__file__)), "models"))


def _safe_load_model(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _extract_features(prompt: str) -> Tuple[float, float, float]:
    """Simple handcrafted features used when no ML model is present."""

    prompt = (prompt or "").lower()
    length = len(prompt)
    has_code = 1.0 if any(tok in prompt for tok in ["def ", "class ", "function", "code"]) else 0.0
    has_security = 1.0 if any(tok in prompt for tok in ["exploit", "hack", "bypass"]) else 0.0
    return float(length), has_code, has_security


@dataclass
class RoutingDecision:
    provider: str
    confidence: float
    label: str


class ThronosAIScorer:
    """Loads pickled scikit-learn models and returns routing/score outputs."""

    def __init__(self, model_dir: Optional[str] = None) -> None:
        self.model_dir = model_dir or MODEL_DIR
        self.routing_model = _safe_load_model(os.path.join(self.model_dir, "routing.pkl"))
        self.quality_model = _safe_load_model(os.path.join(self.model_dir, "quality.pkl"))

    def _predict_provider(self, features: Iterable[float]) -> RoutingDecision:
        if self.routing_model is None or LogisticRegression is None:
            length, has_code, has_security = features
            if has_security:
                return RoutingDecision(provider="anthropic", confidence=0.55, label="safety")
            if has_code:
                return RoutingDecision(provider="openai", confidence=0.6, label="coding")
            if length < 120:
                return RoutingDecision(provider="gemini", confidence=0.52, label="shortform")
            return RoutingDecision(provider="openai", confidence=0.51, label="general")

        try:
            proba = self.routing_model.predict_proba([features])[0]
            classes = list(self.routing_model.classes_)
            idx = int(proba.argmax())
            return RoutingDecision(provider=str(classes[idx]), confidence=float(proba[idx]), label="ml-routing")
        except Exception:
            length, has_code, _ = features
            fallback_provider = "openai" if has_code or length > 150 else "gemini"
            return RoutingDecision(provider=fallback_provider, confidence=0.5, label="fallback")

    def route_provider(self, prompt: str) -> RoutingDecision:
        features = _extract_features(prompt)
        return self._predict_provider(features)

    def score_interaction(self, prompt: str, response: str) -> Dict[str, Any]:
        """Return quality/safety scores using the loaded models (or heuristics)."""

        features = _extract_features(prompt)
        decision = self._predict_provider(features)

        if self.quality_model is None or LogisticRegression is None:
            quality = 0.6 if len(response) > 20 else 0.4
            safety = 0.4 if "exploit" in response.lower() else 0.7
            label = "heuristic"
        else:
            try:
                quality = float(self.quality_model.predict_proba([features])[0][1])
                safety = 1.0 - quality * 0.2
                label = "ml"
            except Exception:
                quality = 0.5
                safety = 0.5
                label = "degraded"

        return {
            "routing": decision.provider,
            "routing_confidence": decision.confidence,
            "routing_label": decision.label,
            "quality_score": quality,
            "safety_score": safety,
            "domain_label": label,
        }


def score_payload(prompt: str, response: str) -> Dict[str, Any]:
    """Convenience wrapper for callers that do not want to manage an instance."""

    scorer = ThronosAIScorer()
    return scorer.score_interaction(prompt, response)

