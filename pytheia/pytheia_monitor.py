#!/usr/bin/env python3
"""
Pytheia Monitor — Service Inventory & Periodic Health Scanner
=============================================================
Reads thronos_registry.yaml and performs periodic health checks
on all registered nodes and services. Generates incident cards
when failures are detected.

Usage:
    python pytheia/pytheia_monitor.py                       # run once
    python pytheia/pytheia_monitor.py --daemon              # continuous mode
    python pytheia/pytheia_monitor.py --daemon --interval 300  # every 5 min
"""

import argparse
import json
import os
import sys
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------
try:
    import yaml
except ImportError:
    try:
        from ruamel.yaml import YAML as _YAML
        class _YamlCompat:
            @staticmethod
            def safe_load(stream):
                y = _YAML(typ="safe")
                return y.load(stream)
        yaml = _YamlCompat()
    except ImportError:
        print("ERROR: Install PyYAML (pip install pyyaml)")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(ROOT, "thronos_registry.yaml")
INCIDENTS_DIR = os.path.join(ROOT, "pytheia", "incidents")
LOG_PATH = os.path.join(ROOT, "pytheia", "pytheia_monitor.log")

DEFAULT_TIMEOUT = 10  # seconds
DEFAULT_INTERVAL = 300  # 5 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, mode="a"),
    ],
)
logger = logging.getLogger("pytheia-monitor")

# ---------------------------------------------------------------------------
# Track consecutive failures for alerting
# ---------------------------------------------------------------------------
_failure_counters: Dict[str, int] = {}


def load_registry() -> dict:
    """Load the master ecosystem registry."""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def health_check(url: str, path: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Perform a single health check on a URL + path."""
    full_url = url.rstrip("/") + path
    start = time.monotonic()
    result = {
        "url": full_url,
        "status": "unknown",
        "status_code": 0,
        "response_time_ms": 0,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        req = urllib.request.Request(full_url, method="GET")
        req.add_header("User-Agent", "Pytheia-Monitor/2026.2")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["status_code"] = resp.status
            result["response_time_ms"] = round((time.monotonic() - start) * 1000)
            if 200 <= resp.status < 300:
                result["status"] = "healthy"
            else:
                result["status"] = "degraded"
    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["response_time_ms"] = round((time.monotonic() - start) * 1000)
        result["status"] = "error"
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        result["response_time_ms"] = round((time.monotonic() - start) * 1000)
        result["status"] = "down"
        result["error"] = str(e.reason)
    except Exception as e:
        result["response_time_ms"] = round((time.monotonic() - start) * 1000)
        result["status"] = "down"
        result["error"] = str(e)
    return result


def create_incident_card(
    node_id: str,
    node_name: str,
    check_result: dict,
    consecutive_failures: int,
) -> dict:
    """Create an incident card for a failing node/service."""
    card = {
        "incident_id": f"INC-{node_id}-{int(time.time())}",
        "created": datetime.now(timezone.utc).isoformat(),
        "severity": "SEV-2" if consecutive_failures < 5 else "SEV-1",
        "node_id": node_id,
        "node_name": node_name,
        "status": check_result["status"],
        "status_code": check_result["status_code"],
        "url": check_result["url"],
        "error": check_result["error"],
        "response_time_ms": check_result["response_time_ms"],
        "consecutive_failures": consecutive_failures,
        "resolution": None,
        "resolved_at": None,
    }

    # Persist to disk
    os.makedirs(INCIDENTS_DIR, exist_ok=True)
    filepath = os.path.join(INCIDENTS_DIR, f"{card['incident_id']}.json")
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=2)

    return card


def scan_all_nodes(registry: dict) -> List[dict]:
    """Health-check every registered node."""
    results = []
    alert_threshold = (
        registry.get("health", {})
        .get("thresholds", {})
        .get("consecutive_failures_alert", 3)
    )

    for node in registry.get("nodes", []):
        node_id = node["id"]
        url = node.get("url", "")
        health_path = node.get("health", "/api/health")

        if not url:
            logger.warning(f"Node {node_id} has no URL — skipping")
            continue

        result = health_check(url, health_path)
        result["node_id"] = node_id
        result["node_name"] = node.get("name", node_id)
        result["tier"] = node.get("tier", "medium")
        result["platform"] = node.get("platform", "unknown")
        results.append(result)

        # Track failures
        if result["status"] in ("down", "error"):
            _failure_counters[node_id] = _failure_counters.get(node_id, 0) + 1
            count = _failure_counters[node_id]
            logger.error(
                f"FAIL [{count}x] {node_id} ({url}{health_path}): "
                f"{result['error']}"
            )
            if count >= alert_threshold:
                card = create_incident_card(
                    node_id, result["node_name"], result, count
                )
                logger.critical(
                    f"INCIDENT CREATED: {card['incident_id']} "
                    f"(SEV: {card['severity']}, failures: {count})"
                )
        else:
            if _failure_counters.get(node_id, 0) > 0:
                logger.info(f"RECOVERED: {node_id} is healthy again")
            _failure_counters[node_id] = 0
            logger.info(
                f"OK {node_id}: {result['status_code']} "
                f"in {result['response_time_ms']}ms"
            )

    return results


def print_service_inventory(registry: dict) -> None:
    """Print a summary of all registered services."""
    print("\n" + "=" * 70)
    print("  PYTHEIA — THRONOS SERVICE INVENTORY")
    print("=" * 70)

    print(f"\n  Registry version: {registry.get('meta', {}).get('version', '?')}")
    print(f"  Owner: {registry.get('meta', {}).get('owner', '?')}")

    # Nodes
    nodes = registry.get("nodes", [])
    print(f"\n  NODES ({len(nodes)}):")
    for n in nodes:
        print(f"    [{n.get('tier','?').upper():>8}] {n['id']:<20} {n.get('url','')}")

    # Services
    services = registry.get("services", [])
    print(f"\n  SERVICES ({len(services)}):")
    for s in services:
        print(f"    [{s.get('tier','?').upper():>8}] {s['id']:<25} ({s.get('category','')})")

    # Apps
    apps = registry.get("apps", [])
    print(f"\n  APPS ({len(apps)}):")
    for a in apps:
        print(f"    [{a.get('tier','?').upper():>8}] {a['id']:<25} ({a.get('category','')})")

    # Games
    games = registry.get("games", [])
    print(f"\n  GAMES ({len(games)}):")
    for g in games:
        print(f"    [{g.get('tier','?').upper():>8}] {g['id']:<25} ({g.get('category','')})")

    # Protocols
    protocols = registry.get("protocols", [])
    print(f"\n  PROTOCOLS ({len(protocols)}):")
    for p in protocols:
        print(f"    [{p.get('tier','?').upper():>8}] {p['id']:<25} ({p.get('category','')})")

    print("\n" + "=" * 70)


def print_checklist() -> None:
    """Print the application checklist."""
    checklist = [
        ("Wallet (HD, QR, Send/Receive)", "wallet-service"),
        ("Music Player / Label (Decent Music)", "decent-music"),
        ("Tips (Artist Direct THR)", "decent-music"),
        ("GPS / Driver Telemetry (T2E)", "driver-telemetry"),
        ("IoT Miners (Smart Parking)", "iot-mining"),
        ("VerifyID (Hosting + Mail Vision)", "verify-id"),
        ("Crypto Hunters (P2E Game)", "crypto-hunters"),
        ("BTC Bridge (Pledge/Watcher)", "btc-bridge"),
        ("AI Core (LLM Inference)", "ai-chat"),
        ("Pytheia (Autonomous Agent)", "pytheia"),
        ("AMM / DEX (Liquidity Pools)", "defi-amm"),
        ("Fiat Gateway (Stripe)", "fiat-gateway"),
        ("Stratum Mining (SHA256)", "stratum-mining"),
        ("EVM Smart Contracts", "evm-contracts"),
        ("Learn-to-Earn (L2E)", "learn-to-earn"),
        ("Explorer", "explorer"),
        ("Chrome Extension", "chrome-extension"),
        ("WhisperNote (Audio-Fi)", "whisper-note"),
        ("RadioNode (RF)", "radio-node"),
        ("PhantomFace (Steganography)", "phantom-face"),
    ]

    print("\n" + "-" * 50)
    print("  APPLICATION CHECKLIST")
    print("-" * 50)
    for name, svc_id in checklist:
        print(f"  [x] {name:<45} ({svc_id})")
    print("-" * 50 + "\n")


def run_scan(registry: dict) -> None:
    """Run a single scan cycle."""
    logger.info("Starting Pytheia health scan...")
    results = scan_all_nodes(registry)

    healthy = sum(1 for r in results if r["status"] == "healthy")
    total = len(results)
    logger.info(f"Scan complete: {healthy}/{total} nodes healthy")

    # Write latest results
    results_path = os.path.join(ROOT, "pytheia", "latest_scan.json")
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "scan_time": datetime.now(timezone.utc).isoformat(),
                "healthy": healthy,
                "total": total,
                "results": results,
            },
            fh,
            indent=2,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pytheia Monitor — Health Scanner")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Scan interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--inventory", action="store_true", help="Print service inventory and exit"
    )
    parser.add_argument(
        "--checklist", action="store_true", help="Print application checklist and exit"
    )
    args = parser.parse_args()

    if not os.path.exists(REGISTRY_PATH):
        logger.error(f"Registry not found: {REGISTRY_PATH}")
        sys.exit(1)

    registry = load_registry()

    if args.inventory:
        print_service_inventory(registry)
        return

    if args.checklist:
        print_checklist()
        return

    # Always print inventory on startup
    print_service_inventory(registry)
    print_checklist()

    if args.daemon:
        logger.info(f"Pytheia daemon mode — scanning every {args.interval}s")
        while True:
            try:
                registry = load_registry()  # reload each cycle
                run_scan(registry)
            except KeyboardInterrupt:
                logger.info("Pytheia monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Scan error: {e}")
            time.sleep(args.interval)
    else:
        run_scan(registry)


if __name__ == "__main__":
    main()
