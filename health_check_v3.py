# health_check.py
# Health check and monitoring endpoints for Thronos

import os
import time
from typing import Dict, Any

from flask import Blueprint, jsonify

try:
    import psutil  # type: ignore[import]
except ImportError:  # Fallback if psutil is not available
    psutil = None  # type: ignore[assignment]

health_bp = Blueprint("health", __name__)


def get_system_stats() -> Dict[str, Any]:
    """Get system resource statistics.

    If psutil is not installed, return a degraded but valid payload instead of
    raising at import time so that the /api/v1/health endpoint still works.
    """

    if psutil is None:
        return {"warning": "psutil not installed, system stats unavailable"}

    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "cpu_usage_percent": cpu_percent,
            "memory": {
                "total_mb": memory.total / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
                "used_percent": memory.percent,
            },
            "disk": {
                "total_gb": disk.total / (1024 * 1024 * 1024),
                "used_gb": disk.used / (1024 * 1024 * 1024),
                "free_gb": disk.free / (1024 * 1024 * 1024),
                "used_percent": disk.percent,
            },
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"Failed to get system stats: {str(e)}"}


def check_data_files() -> Dict[str, bool]:
    """Check if critical data files exist."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.getenv("DATA_DIR", os.path.join(base_dir, "data"))

    files_to_check = [
        "ledger.json",
        "phantom_tx_chain.json",
        "pledge_chain.json",
        "last_block.json",
    ]

    status: Dict[str, bool] = {}
    for filename in files_to_check:
        filepath = os.path.join(data_dir, filename)
        status[filename] = os.path.exists(filepath)

    return status


@health_bp.route("/api/v1/health", methods=["GET"])
def health_check():
    """Comprehensive health check endpoint.

    Returns JSON with health status and system information.
    """

    try:
        health_data: Dict[str, Any] = {
            "status": "healthy",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "uptime_seconds": time.time() - health_bp.start_time
            if hasattr(health_bp, "start_time")
            else 0,
        }

        # System stats
        health_data["system"] = get_system_stats()

        # Data files status
        health_data["data_files"] = check_data_files()

        # Check if any critical files are missing
        critical_missing = [
            name
            for name, exists in health_data["data_files"].items()
            if not exists
        ]

        if critical_missing:
            health_data["status"] = "degraded"
            health_data["warnings"] = [
                f"Missing critical file: {name}" for name in critical_missing
            ]

        return jsonify(health_data), 200

    except Exception as e:  # noqa: BLE001
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": time.strftime(
                        "%Y-%m-%d %H:%M:%S UTC", time.gmtime()
                    ),
                }
            ),
            500,
        )


@health_bp.route("/api/v1/stats/summary", methods=["GET"])
def stats_summary():
    """Quick statistics summary endpoint.

    Returns JSON with key blockchain statistics.
    """

    try:
        from server import CHAIN_FILE, HEIGHT_OFFSET, LEDGER_FILE, PLEDGE_CHAIN, load_json

        ledger = load_json(LEDGER_FILE, {})
        chain = load_json(CHAIN_FILE, [])
        pledges = load_json(PLEDGE_CHAIN, [])

        blocks = [b for b in chain if isinstance(b, dict) and b.get("reward") is not None]

        summary = {
            "total_blocks": HEIGHT_OFFSET + len(blocks),
            "total_pledges": len(pledges),
            "total_supply": round(sum(float(v) for v in ledger.values()), 6),
            "total_addresses": len(ledger),
            "latest_block_time": blocks[-1].get("timestamp") if blocks else None,
            "chain_health": "healthy",
        }

        return jsonify(summary), 200

    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Failed to get stats summary: {str(e)}"}), 500


# Initialize start time
health_bp.start_time = time.time()
