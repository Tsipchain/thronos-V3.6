#!/usr/bin/env python3
"""
generate_bootstrap.py
=====================
Reads thronos_registry.yaml (the canonical Master Ecosystem Registry)
and produces portal/bootstrap.json consumed by the Thronos portal,
wallet widget, and any front-end service-discovery client.

Usage:
    python scripts/generate_bootstrap.py                     # default paths
    python scripts/generate_bootstrap.py --registry path.yaml --out path.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# YAML loader – try ruamel first (preserves comments), fall back to PyYAML,
# then to a minimal safe subset parser if neither is installed.
# ---------------------------------------------------------------------------
try:
    from ruamel.yaml import YAML
    def load_yaml(path: str) -> dict:
        yaml = YAML(typ="safe")
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.load(fh)
except ImportError:
    try:
        import yaml  # type: ignore[import-untyped]
        def load_yaml(path: str) -> dict:
            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    except ImportError:
        print("ERROR: Install PyYAML or ruamel.yaml  (pip install pyyaml)")
        sys.exit(1)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REGISTRY = os.path.join(ROOT, "thronos_registry.yaml")
DEFAULT_OUTPUT = os.path.join(ROOT, "portal", "bootstrap.json")


def build_bootstrap(registry: dict) -> dict:
    """Transform the full registry into the lean bootstrap.json format."""

    meta = registry.get("meta", {})

    # --- Nodes ---------------------------------------------------------
    nodes = {}
    for n in registry.get("nodes", []):
        nodes[n["id"]] = {
            "name": n["name"],
            "role": n["role"],
            "url": n.get("url", ""),
            "health": n.get("health", "/api/health"),
            "platform": n.get("platform", "unknown"),
            "tier": n.get("tier", "medium"),
        }

    # --- Services ------------------------------------------------------
    services = {}
    for s in registry.get("services", []):
        services[s["id"]] = {
            "name": s["name"],
            "node": s.get("node", ""),
            "tier": s.get("tier", "medium"),
            "category": s.get("category", ""),
            "endpoints": s.get("endpoints", []),
        }

    # --- Apps ----------------------------------------------------------
    apps = {}
    for a in registry.get("apps", []):
        apps[a["id"]] = {
            "name": a["name"],
            "node": a.get("node", ""),
            "tier": a.get("tier", "medium"),
            "category": a.get("category", ""),
            "endpoints": a.get("endpoints", []),
        }

    # --- Games ---------------------------------------------------------
    games = {}
    for g in registry.get("games", []):
        games[g["id"]] = {
            "name": g["name"],
            "node": g.get("node", ""),
            "tier": g.get("tier", "medium"),
            "category": g.get("category", ""),
            "endpoints": g.get("endpoints", []),
        }

    # --- Protocols -----------------------------------------------------
    protocols = {}
    for p in registry.get("protocols", []):
        protocols[p["id"]] = {
            "name": p["name"],
            "tier": p.get("tier", "medium"),
            "category": p.get("category", ""),
        }

    # --- Landings ------------------------------------------------------
    landings = []
    for ln in registry.get("landings", []):
        landings.append({
            "id": ln["id"],
            "name": ln["name"],
            "path": ln.get("path", "/"),
        })

    # --- Domains -------------------------------------------------------
    domains = []
    for d in registry.get("domains", []):
        domains.append({
            "domain": d["domain"],
            "target": d.get("target", ""),
            "type": d.get("type", "cname"),
        })

    return {
        "_generated": datetime.now(timezone.utc).isoformat(),
        "_source": "thronos_registry.yaml",
        "meta": meta,
        "nodes": nodes,
        "services": services,
        "apps": apps,
        "games": games,
        "protocols": protocols,
        "landings": landings,
        "domains": domains,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate bootstrap.json from thronos_registry.yaml"
    )
    parser.add_argument(
        "--registry", default=DEFAULT_REGISTRY, help="Path to registry YAML"
    )
    parser.add_argument(
        "--out", default=DEFAULT_OUTPUT, help="Output bootstrap.json path"
    )
    args = parser.parse_args()

    if not os.path.exists(args.registry):
        print(f"ERROR: Registry file not found: {args.registry}")
        sys.exit(1)

    registry = load_yaml(args.registry)
    bootstrap = build_bootstrap(registry)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(bootstrap, fh, indent=2, ensure_ascii=False)

    svc_count = len(bootstrap.get("services", {}))
    app_count = len(bootstrap.get("apps", {}))
    game_count = len(bootstrap.get("games", {}))
    print(f"✓ bootstrap.json written → {args.out}")
    print(f"  {svc_count} services, {app_count} apps, {game_count} games")


if __name__ == "__main__":
    main()
