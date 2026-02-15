#!/usr/bin/env python3
"""
PYTHEIA Worker (Node3) - Inline System Health Monitor

This worker runs as a background process or APScheduler job within the same
Railway service. It monitors system health, collects telemetry, generates
PYTHEIA_ADVICE, and posts to /api/governance/pytheia/advice when thresholds
are met.

Key Features:
- Health checks for /chat, /architect, /api/ai/models, /api/bridge/status, /tokens, /nft
- Server-side error counter collection
- Auto-generate PYTHEIA_ADVICE JSON
- Auto-post to governance API
- Rate limiting to prevent DAO spam
- Status change detection to minimize noise

Usage:
  As standalone: python3 pytheia_worker.py
  As scheduled job: Import and schedule via APScheduler in server.py
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
from llm_registry import discover_openai_models, discover_anthropic_models, discover_gemini_models


def _default_admin_control() -> Dict[str, Any]:
    return {
        "codex_mode": "monitor",
        "governance_approved": False,
        "repo_write_enabled": False,
        "directive": "",
        "attachment_refs": [],
        "page_paths": [],
        "updated_at": None,
    }


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _state_parent_dir(path: str) -> str:
    return os.path.dirname(path) or "."


def _build_log_handlers() -> List[logging.Handler]:
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        os.makedirs("logs", exist_ok=True)
        handlers.append(logging.FileHandler("logs/pytheia_worker.log", mode="a"))
    except Exception:
        # Keep worker import-safe even on restricted/readonly filesystems.
        pass
    return handlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - PYTHEIA - %(levelname)s - %(message)s',
    handlers=_build_log_handlers(),
)
logger = logging.getLogger(__name__)

# Configuration
def _resolve_base_url() -> str:
    explicit = (os.getenv("PYTHEIA_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")

    render_url = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    if render_url:
        return render_url.rstrip("/")

    port = (os.getenv("PORT") or "").strip()
    if port:
        return f"http://127.0.0.1:{port}"

    return "http://localhost:5000"


BASE_URL = _resolve_base_url()
CHECK_INTERVAL = int(os.getenv("PYTHEIA_CHECK_INTERVAL", "300"))  # 5 minutes default
STATE_FILE = os.getenv("PYTHEIA_STATE_FILE", "data/pytheia_state.json")
MODEL_SNAPSHOT_FILE = os.path.join(os.getenv("DATA_DIR", "data"), "model_catalog_snapshot.json")
REPO_URL = "https://github.com/Tsipchain/thronos-V3.6"


def _provider_scan_interval_seconds() -> int:
    raw = (os.getenv("PYTHEIA_PROVIDER_SCAN_INTERVAL_SECONDS") or "2592000").strip()
    try:
        value = int(raw)
    except Exception:
        value = 2592000
    return max(3600, value)


PROVIDER_SCAN_INTERVAL_SECONDS = _provider_scan_interval_seconds()

def _parse_csv_env(name: str) -> List[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    out: List[str] = []
    for part in raw.split(","):
        v = part.strip()
        if v and v not in out:
            out.append(v)
    return out


def _external_health_targets() -> List[Dict[str, str]]:
    """
    Parse PYTHEIA_EXTERNAL_HEALTH_TARGETS JSON.

    Example:
    [{"name":"trader-sentinel","base_url":"https://trader-sentinel.example.com","path":"/health"}]
    """
    raw = (os.getenv("PYTHEIA_EXTERNAL_HEALTH_TARGETS") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        logger.warning("Invalid PYTHEIA_EXTERNAL_HEALTH_TARGETS JSON; ignoring")
        return []
    if not isinstance(data, list):
        return []

    out: List[Dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        base_url = str(item.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            continue
        name = str(item.get("name") or base_url).strip()
        path = "/" + str(item.get("path") or "/health").strip().lstrip("/")
        out.append({"name": name, "base_url": base_url, "path": path})
    return out

# Health check endpoints
HEALTH_ENDPOINTS = [
    {"path": "/chat", "name": "Chat Page", "expected_status": 200},
    {"path": "/architect", "name": "Architect Page", "expected_status": 200},
    {"path": "/api/ai/models", "name": "AI Models API", "expected_status": 200},
    {"path": "/api/ai/telemetry", "name": "AI Telemetry API", "expected_status": 200},
    {"path": "/api/music/telemetry/stats", "name": "Music Telemetry Stats", "expected_status": 200},
    {"path": "/api/bridge/status", "name": "Bridge Status API", "expected_status": 200},
    {"path": "/tokens", "name": "Tokens Page", "expected_status": 200},
    {"path": "/nft", "name": "NFT Page", "expected_status": 200},
    {"path": "/governance", "name": "Governance Page", "expected_status": 200},
    {"path": "/wallet_viewer", "name": "Wallet Viewer", "expected_status": 200},
]

# Error thresholds
THRESHOLDS = {
    "consecutive_failures": 3,  # Trigger alert after 3 consecutive failures
    "degraded_mode_duration": 600,  # 10 minutes
    "error_rate_threshold": 0.15,  # 15% error rate
    "min_post_interval": 3600,  # Don't post more than once per hour
}


class PYTHEIAWorker:
    """PYTHEIA Worker for continuous system monitoring."""

    def __init__(self):
        self.state = self.load_state()
        self.admin_control = self._normalize_admin_control(self.state.get("admin_control"))
        self.admin_instruction_history = self._normalize_instruction_history(self.state.get("admin_instruction_history"))
        self.base_url = BASE_URL
        self.governance_api = f"{self.base_url}/api/governance/pytheia/advice"
        self.last_post_time = self.state.get("last_post_time", 0)
        self.last_status = self.state.get("last_status", {})
        self.consecutive_failures = self.state.get("consecutive_failures", {})
        self.last_model_snapshot = self.state.get("last_model_snapshot", {})
        self.last_health_report = self.state.get("last_health_report", {})
        self.last_advice = self.state.get("last_advice", {})
        self.last_provider_scan_ts = float(self.state.get("last_provider_scan_ts", 0) or 0)
        self.provider_scan_interval_s = PROVIDER_SCAN_INTERVAL_SECONDS
        self.next_provider_scan_ts = float(self.state.get("next_provider_scan_ts", 0) or 0)
        if self.next_provider_scan_ts <= 0:
            self.next_provider_scan_ts = time.time() + self.provider_scan_interval_s

    @staticmethod
    def _normalize_instruction_history(history: Any) -> List[Dict[str, Any]]:
        if not isinstance(history, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in history[-20:]:
            if not isinstance(item, dict):
                continue
            out.append({
                "instruction": str(item.get("instruction") or "").strip(),
                "attachment_refs": item.get("attachment_refs") if isinstance(item.get("attachment_refs"), list) else [],
                "page_paths": item.get("page_paths") if isinstance(item.get("page_paths"), list) else [],
                "submitted_by": str(item.get("submitted_by") or "admin").strip() or "admin",
                "submitted_at": str(item.get("submitted_at") or "").strip() or datetime.utcnow().isoformat(timespec="seconds") + "Z",
            })
        return out

    @staticmethod
    def _normalize_admin_control(control: Any) -> Dict[str, Any]:
        base = _default_admin_control()
        if not isinstance(control, dict):
            return base
        for key in ("codex_mode", "directive", "updated_at"):
            if control.get(key) is not None:
                base[key] = str(control.get(key)).strip()
        for key in ("governance_approved", "repo_write_enabled"):
            base[key] = _coerce_bool(control.get(key))
        if base["codex_mode"] not in {"monitor", "assist", "active"}:
            base["codex_mode"] = "monitor"
        for key in ("attachment_refs", "page_paths"):
            vals = control.get(key)
            if isinstance(vals, list):
                base[key] = [str(v).strip() for v in vals if str(v).strip()]
        if base["repo_write_enabled"] and not base["governance_approved"]:
            base["repo_write_enabled"] = False
        return base

    def refresh_admin_control(self) -> None:
        latest = self.load_state()
        self.admin_control = self._normalize_admin_control(latest.get("admin_control"))
        self.admin_instruction_history = self._normalize_instruction_history(latest.get("admin_instruction_history"))

    def _effective_endpoints(self) -> List[Dict[str, Any]]:
        effective = list(HEALTH_ENDPOINTS)
        existing_paths = {ep.get("path") for ep in effective}
        for path in self.admin_control.get("page_paths") or []:
            clean = "/" + str(path).strip().lstrip("/")
            if not clean or clean in existing_paths:
                continue
            effective.append({"path": clean, "name": f"Custom: {clean}", "expected_status": 200})
            existing_paths.add(clean)
        return effective

    def _external_endpoints(self) -> List[Dict[str, Any]]:
        endpoints: List[Dict[str, Any]] = []
        for t in _external_health_targets():
            endpoints.append({
                "name": f"External: {t['name']}",
                "path": t["path"],
                "base_url": t["base_url"],
                "expected_status": 200,
            })
        return endpoints

    def load_state(self) -> Dict:
        """Load persistent state from file."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
        return {}

    def save_state(self):
        """Save persistent state to file."""
        try:
            os.makedirs(_state_parent_dir(STATE_FILE), exist_ok=True)
            current = self.load_state()
            if not isinstance(current, dict):
                current = {}
            current.update({
                "last_post_time": self.last_post_time,
                "last_status": self.last_status,
                "consecutive_failures": self.consecutive_failures,
                "last_model_snapshot": self.last_model_snapshot,
                "last_health_report": self.last_health_report,
                "last_advice": self.last_advice,
                "last_provider_scan_ts": self.last_provider_scan_ts,
                "next_provider_scan_ts": self.next_provider_scan_ts,
                "admin_control": self.admin_control,
                "admin_instruction_history": self.admin_instruction_history,
                "last_update": datetime.utcnow().isoformat()
            })
            with open(STATE_FILE, 'w') as f:
                json.dump(current, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def scan_provider_models(self) -> Dict[str, Any]:
        openai_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
        anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

        providers = {
            "openai": {"models": discover_openai_models(openai_key)},
            "anthropic": {"models": discover_anthropic_models(anthropic_key)},
            "gemini": {"models": discover_gemini_models(gemini_key)},
        }
        for provider_name, payload in providers.items():
            models = payload.get("models") or []
            ok = any(bool(m.get("enabled")) for m in models if isinstance(m, dict))
            payload["status"] = "ok" if ok else "degraded"

        snapshot = {
            "last_scan_ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "providers": providers,
        }

        try:
            os.makedirs(os.path.dirname(MODEL_SNAPSHOT_FILE), exist_ok=True)
            with open(MODEL_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"Failed to write model snapshot file: {exc}")
        return snapshot

    def fetch_ai_model_snapshot(self) -> Dict[str, Any]:
        """Collect dynamic AI model/provider availability snapshot from APIs."""
        out: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "models": [],
            "enabled_model_ids": [],
            "providers": {},
            "engine": None,
            "mode": None,
            "errors": [],
        }

        for path in ("/api/ai_models", "/api/ai/models"):
            try:
                r = requests.get(f"{self.base_url}{path}", timeout=10)
                if r.status_code != 200:
                    out["errors"].append(f"{path}:HTTP {r.status_code}")
                    continue
                data = r.json() if "application/json" in (r.headers.get("content-type") or "") else {}
                if isinstance(data, dict) and data.get("models"):
                    out["models"] = data.get("models") or []
                    out["engine"] = data.get("engine")
                    out["mode"] = data.get("mode")
                    break
            except Exception as exc:
                out["errors"].append(f"{path}:{exc}")

        try:
            hr = requests.get(f"{self.base_url}/api/ai/health", timeout=10)
            if hr.status_code == 200:
                hdata = hr.json() if "application/json" in (hr.headers.get("content-type") or "") else {}
                if isinstance(hdata, dict):
                    out["providers"] = hdata.get("providers") or hdata.get("provider_status") or {}
                    out["enabled_model_ids"] = hdata.get("enabled_model_ids") or []
                    out["engine"] = out["engine"] or hdata.get("engine")
                    out["mode"] = out["mode"] or hdata.get("mode")
            else:
                out["errors"].append(f"/api/ai/health:HTTP {hr.status_code}")
        except Exception as exc:
            out["errors"].append(f"/api/ai/health:{exc}")

        return out

    @staticmethod
    def _snapshot_changed(prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        prev_enabled = sorted(prev.get("enabled_model_ids") or [])
        curr_enabled = sorted(curr.get("enabled_model_ids") or [])
        prev_models = sorted([m.get("id") for m in (prev.get("models") or []) if isinstance(m, dict)])
        curr_models = sorted([m.get("id") for m in (curr.get("models") or []) if isinstance(m, dict)])
        prev_providers = sorted(list((prev.get("providers") or {}).keys()))
        curr_providers = sorted(list((curr.get("providers") or {}).keys()))
        return (prev_enabled != curr_enabled) or (prev_models != curr_models) or (prev_providers != curr_providers)

    def check_endpoint(self, endpoint: Dict) -> Dict[str, Any]:
        """
        Check a single endpoint health.

        Returns:
            {"name": str, "status": "ok"|"degraded"|"down", "status_code": int,
             "response_time_ms": float, "error": str|None}
        """
        base_url = str(endpoint.get("base_url") or self.base_url).rstrip("/")
        url = f"{base_url}{endpoint['path']}"
        start_time = time.time()
        result = {
            "name": endpoint["name"],
            "path": endpoint["path"],
            "base_url": base_url,
            "status": "unknown",
            "status_code": None,
            "response_time_ms": None,
            "error": None
        }

        try:
            response = requests.get(url, timeout=10, allow_redirects=True)
            response_time = (time.time() - start_time) * 1000
            result["response_time_ms"] = round(response_time, 2)
            result["status_code"] = response.status_code

            if response.status_code == endpoint["expected_status"]:
                # Additional check for degraded mode in API responses
                if "/api/" in endpoint["path"]:
                    try:
                        data = response.json()
                        if data.get("ok") == False or data.get("fallback_active") == True:
                            result["status"] = "degraded"
                            result["error"] = data.get("error_message", "Degraded mode active")
                        else:
                            result["status"] = "ok"
                    except:
                        result["status"] = "ok"  # HTML pages
                else:
                    result["status"] = "ok"
            else:
                result["status"] = "down"
                result["error"] = f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            result["status"] = "down"
            result["error"] = "Timeout after 10s"
        except requests.exceptions.ConnectionError:
            result["status"] = "down"
            result["error"] = "Connection refused"
        except Exception as e:
            result["status"] = "down"
            result["error"] = str(e)

        return result

    def run_health_checks(self) -> Dict[str, Any]:
        """
        Run all health checks and return aggregated results.

        Returns:
            {"timestamp": str, "overall_status": str, "checks": [...],
             "summary": {...}}
        """
        logger.info("Running health checks...")
        checks = []
        ok_count = 0
        degraded_count = 0
        down_count = 0

        endpoints = self._effective_endpoints() + self._external_endpoints()
        for endpoint in endpoints:
            result = self.check_endpoint(endpoint)
            checks.append(result)

            if result["status"] == "ok":
                ok_count += 1
                self.consecutive_failures[endpoint["name"]] = 0
            elif result["status"] == "degraded":
                degraded_count += 1
                self.consecutive_failures[endpoint["name"]] = self.consecutive_failures.get(endpoint["name"], 0) + 1
            else:  # down
                down_count += 1
                self.consecutive_failures[endpoint["name"]] = self.consecutive_failures.get(endpoint["name"], 0) + 1

            logger.info(f"  {endpoint['name']}: {result['status']} ({result.get('status_code', 'N/A')})")

        # Determine overall status
        total = max(1, len(endpoints))
        if down_count >= total * 0.5:
            overall_status = "critical"
        elif down_count > 0 or degraded_count >= total * 0.3:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        ai_snapshot = self.fetch_ai_model_snapshot()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": overall_status,
            "checks": checks,
            "summary": {
                "total": len(endpoints),
                "ok": ok_count,
                "degraded": degraded_count,
                "down": down_count
            },
            "ai_models": ai_snapshot,
            "ai_catalog_changed": self._snapshot_changed(self.last_model_snapshot, ai_snapshot),
            "effective_paths": [ep.get("path") for ep in endpoints],
            "repo_targets": _parse_csv_env("PYTHEIA_REPO_TARGETS"),
            "apk_simulation": {
                "enabled": _coerce_bool(os.getenv("PYTHEIA_APK_SIMULATION", "0")),
                "sdks": _parse_csv_env("PYTHEIA_APK_SDKS"),
                "module": (os.getenv("PYTHEIA_APK_MODULE") or "app").strip() or "app",
            },
            "provider_refresh": {
                "interval_seconds": self.provider_scan_interval_s,
                "last_scan_ts": self.last_provider_scan_ts,
                "next_scan_ts": self.next_provider_scan_ts,
            },
        }

    @staticmethod
    def _build_apk_simulation_plan(apk_cfg: Dict[str, Any]) -> Dict[str, Any]:
        enabled = bool(apk_cfg.get("enabled"))
        sdks = apk_cfg.get("sdks") if isinstance(apk_cfg.get("sdks"), list) else []
        module = str(apk_cfg.get("module") or "app").strip() or "app"
        if not enabled:
            return {"enabled": False, "steps": []}
        if not sdks:
            sdks = ["34"]
        steps = [
            f"Setup Android SDK / Gradle toolchain for module '{module}'",
            f"Build debug APK for SDK targets: {', '.join(sdks)}",
            "Run instrumentation simulation and smoke tests",
            "Publish APK artifact and health report",
        ]
        return {"enabled": True, "module": module, "sdks": sdks, "steps": steps}

    def should_post_advice(self, health_report: Dict) -> bool:
        """
        Determine if PYTHEIA_ADVICE should be posted based on thresholds.

        Criteria:
        - Overall status changed from last check
        - Consecutive failures exceeded threshold
        - Minimum time since last post elapsed
        """
        current_time = time.time()
        current_status = health_report["overall_status"]
        last_status = self.last_status.get("overall_status")

        # Rate limiting: Don't post too frequently
        if (current_time - self.last_post_time) < THRESHOLDS["min_post_interval"]:
            logger.debug("Rate limit: Too soon since last post")
            return False

        # Status changed
        if current_status != last_status:
            logger.info(f"Status change detected: {last_status} -> {current_status}")
            return True

        # Check consecutive failures for critical endpoints
        for name, count in self.consecutive_failures.items():
            if count >= THRESHOLDS["consecutive_failures"]:
                logger.warning(f"Consecutive failure threshold exceeded for {name}: {count}")
                return True

        # Degraded mode persisting
        if current_status in ["degraded", "critical"]:
            degraded_duration = self.state.get("degraded_since", current_time)
            if (current_time - degraded_duration) > THRESHOLDS["degraded_mode_duration"]:
                logger.warning("Degraded mode persisting beyond threshold")
                return True

        if health_report.get("ai_catalog_changed"):
            logger.info("AI model/provider catalog changed - recommend PYTHEIA advice update")
            return True

        return False

    def generate_pytheia_advice(self, health_report: Dict) -> Dict:
        """
        Generate PYTHEIA_ADVICE JSON from health report.

        Returns schema-compliant PYTHEIA Advice v1.0.0 document.
        """
        current_status = health_report["overall_status"]
        severity_map = {
            "critical": "BLOCKER",
            "degraded": "MAJOR",
            "healthy": "INFO"
        }
        severity = severity_map.get(current_status, "MINOR")

        # Build priorities from failed checks
        priorities = []
        priority_id = 1
        for check in health_report["checks"]:
            if check["status"] != "ok":
                priorities.append({
                    "id": f"P{priority_id}",
                    "title": f"{check['name']} - {check['status'].upper()}",
                    "severity": "BLOCKER" if check["status"] == "down" else "MAJOR",
                    "status": "open",
                    "files": [check["path"]],
                    "description": f"{check['name']} endpoint is {check['status']}. Error: {check.get('error', 'N/A')}. Status code: {check.get('status_code', 'N/A')}.",
                    "impact": f"Users cannot access {check['name']}. Service degradation detected."
                })
                priority_id += 1

        if not priorities:
            # No issues, create info priority
            priorities.append({
                "id": "P1",
                "title": "All systems operational",
                "severity": "INFO",
                "status": "pass",
                "files": [],
                "description": "All monitored endpoints responding normally.",
                "impact": "None. System healthy."
            })

        # Get current commit
        try:
            commit_hash = os.popen("git rev-parse HEAD").read().strip()[:7]
        except:
            commit_hash = "unknown"

        # Build advice document
        advice = {
            "schema_version": "PYTHEIA Advice v1.0.0",
            "timestamp": health_report["timestamp"],
            "auditor": "PYTHEIA AI Node (Inline Worker)",
            "repo": REPO_URL,
            "commit": commit_hash,
            "title": f"System Health Report - Status: {current_status.upper()}",
            "severity": severity,
            "priorities": priorities,
            "options": [
                {
                    "id": "A",
                    "title": "Auto-recovery attempt",
                    "scope": "Restart affected services, clear caches, verify configuration",
                    "effort": "5-10 minutes",
                    "risk": "Low",
                    "cost_thr": 0,
                    "vote_recommendation": "APPROVE" if current_status == "degraded" else "STRONGLY_APPROVE"
                },
                {
                    "id": "B",
                    "title": "Manual investigation required",
                    "scope": "Engineer review logs, diagnose root cause, apply targeted fix",
                    "effort": "30-60 minutes",
                    "risk": "Medium",
                    "cost_thr": 0,
                    "vote_recommendation": "NEUTRAL"
                }
            ],
            "patch_plan": {
                "phases": [
                    {
                        "phase": 1,
                        "title": "Verify health check results",
                        "files": [c["path"] for c in health_report["checks"] if c["status"] != "ok"],
                        "changes": "Re-run health checks manually to confirm issues persist"
                    },
                    {
                        "phase": 2,
                        "title": "Review application logs",
                        "files": ["logs/server.log", "logs/pytheia_worker.log"],
                        "changes": "Check for error messages, stack traces, or warnings related to failing endpoints"
                    },
                    {
                        "phase": 3,
                        "title": "Apply recovery actions",
                        "files": [],
                        "changes": "Restart services if needed, clear caches, verify environment variables"
                    }
                ],
                "tests": [
                    "Re-run all health checks after recovery",
                    "Verify affected endpoints return expected status codes",
                    "Confirm degraded mode clears if applicable",
                    "Monitor for 15 minutes to ensure stability"
                ],
                "rollback": "No code changes made. Recovery actions are non-destructive."
            },
            "governance_url": f"{self.base_url}/governance",
            "requires_approval": False,
            "auto_executable": current_status == "healthy",
            "ai_models_snapshot": {
                "changed": bool(health_report.get("ai_catalog_changed")),
                "enabled_model_ids": (health_report.get("ai_models") or {}).get("enabled_model_ids", []),
                "providers": list(((health_report.get("ai_models") or {}).get("providers") or {}).keys()),
            },
            "admin_control": self.admin_control,
            "instruction_history": self.admin_instruction_history[-5:],
            "dynamic_scan_paths": health_report.get("effective_paths") or [],
            "repo_targets": health_report.get("repo_targets") or [],
            "apk_builder_simulation": self._build_apk_simulation_plan(health_report.get("apk_simulation") or {}),
            "provider_refresh": health_report.get("provider_refresh") or {},
        }

        return advice

    def post_pytheia_advice(self, advice: Dict) -> bool:
        """
        Post PYTHEIA_ADVICE to governance API.

        Returns:
            True if posted successfully, False otherwise
        """
        try:
            logger.info(f"Posting PYTHEIA_ADVICE to {self.governance_api}...")
            response = requests.post(
                self.governance_api,
                json=advice,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    logger.info(f"✓ PYTHEIA_ADVICE posted successfully: {data.get('post_id')}")
                    self.last_post_time = time.time()
                    self.save_state()
                    return True
                else:
                    logger.error(f"API returned non-success status: {data}")
                    return False
            else:
                logger.error(f"Failed to post PYTHEIA_ADVICE: HTTP {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False

        except Exception as e:
            logger.warning(f"PYTHEIA advice post skipped (unreachable governance API): {e}")
            return False

    def run_cycle(self):
        """Run one monitoring cycle."""
        logger.info("="*60)
        logger.info("PYTHEIA Worker Cycle Starting")
        logger.info("="*60)

        # Run health checks
        self.refresh_admin_control()
        health_report = self.run_health_checks()
        logger.info(f"Overall Status: {health_report['overall_status'].upper()}")
        logger.info(f"Summary: {health_report['summary']}")

        now_ts = time.time()
        if now_ts >= self.next_provider_scan_ts:
            provider_snapshot = self.scan_provider_models()
            if self._snapshot_changed(self.last_model_snapshot, {"models": [m for p in provider_snapshot.get("providers", {}).values() for m in (p.get("models") or [])], "providers": provider_snapshot.get("providers", {})}):
                logger.info("Provider catalog changed (scanner)")
            self.last_provider_scan_ts = now_ts
            while self.next_provider_scan_ts <= now_ts:
                self.next_provider_scan_ts += self.provider_scan_interval_s
            logger.info("Next provider model refresh scheduled at %s", datetime.utcfromtimestamp(self.next_provider_scan_ts).isoformat() + "Z")

        # Update state
        self.last_status = {
            "overall_status": health_report["overall_status"],
            "timestamp": health_report["timestamp"]
        }
        self.last_model_snapshot = health_report.get("ai_models") or {}
        self.last_health_report = health_report

        # Determine if we should post advice
        if self.should_post_advice(health_report):
            logger.info("Threshold met - generating PYTHEIA_ADVICE...")
            advice = self.generate_pytheia_advice(health_report)
            self.last_advice = advice

            # Save advice locally
            advice_file = f"governance/pytheia_advice_{int(time.time())}.json"
            try:
                os.makedirs(os.path.dirname(advice_file), exist_ok=True)
                with open(advice_file, 'w') as f:
                    json.dump(advice, f, indent=2)
                logger.info(f"PYTHEIA_ADVICE saved to {advice_file}")
            except Exception as e:
                logger.error(f"Failed to save advice file: {e}")

            # Post to API
            self.post_pytheia_advice(advice)
        else:
            logger.info("No significant changes - skipping PYTHEIA_ADVICE post")

        # Save state
        self.save_state()

        logger.info("Cycle complete\n")

    def run_forever(self):
        """Run worker in continuous loop."""
        logger.info("PYTHEIA Worker starting in continuous mode")
        logger.info(f"Check interval: {CHECK_INTERVAL}s")
        logger.info(f"Base URL: {self.base_url}")

        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.exception(f"Cycle error: {e}")

            logger.info(f"Sleeping for {CHECK_INTERVAL}s...")
            time.sleep(CHECK_INTERVAL)


def main():
    """Main entry point."""
    # Create logs directory
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # Start worker
    worker = PYTHEIAWorker()
    worker.run_forever()


if __name__ == "__main__":
    main()
