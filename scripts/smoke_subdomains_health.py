#!/usr/bin/env python3
"""Smoke-check Thronos public service health endpoints.

Checks the requested services:
- api.thronoschain.org
- ro.api.thronoschain.org
- verifyid.thronoschain.org
- verifyid-api.thronoschain.org
- ai.thronoschain.org
- explorer.thronoschain.org
- sentinel.thronoschain.org
- btc-api.thronoschain.org
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Iterable

import requests

TIMEOUT = 15
RETRIES = 2
STRICT = False


@dataclass
class Target:
    name: str
    base_url: str
    paths: list[str]
    require_cors: bool = True


TARGETS: list[Target] = [
    Target("api", "https://api.thronoschain.org", ["/health", "/api/health"]),
    Target("ro.api", "https://ro.api.thronoschain.org", ["/health", "/api/health"]),
    Target("verifyid", "https://verifyid.thronoschain.org", ["/health", "/health.json", "/api/health"], require_cors=False),
    Target("verifyid-api", "https://verifyid-api.thronoschain.org", ["/health"]),
    Target("ai", "https://ai.thronoschain.org", ["/health", "/api/health"]),
    Target("explorer", "https://explorer.thronoschain.org", ["/health", "/health.json", "/api/health"], require_cors=False),
    Target("sentinel", "https://sentinel.thronoschain.org", ["/health", "/api/health"]),
    Target("btc-api", "https://btc-api.thronoschain.org", ["/health", "/api/health"]),
]


def _is_json_health_payload(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("ok") is True:
        return True
    status = str(payload.get("status") or "").strip().lower()
    return status in {"healthy", "ok", "syncing", "up"}


def _try_target(target: Target) -> dict:
    errors: list[str] = []
    for path in target.paths:
        url = target.base_url.rstrip("/") + path
        resp = None
        for attempt in range(RETRIES):
            try:
                resp = requests.get(url, timeout=TIMEOUT)
                break
            except Exception as exc:
                if attempt == RETRIES - 1:
                    errors.append(f"{path}: request_error={exc}")
                time.sleep(0.2)
        if resp is None:
            continue

        if 200 <= resp.status_code < 300:
            payload = None
            try:
                payload = resp.json()
            except Exception:
                payload = {"raw": resp.text[:160]}

            cors = resp.headers.get("Access-Control-Allow-Origin")
            if STRICT and target.require_cors and cors != "*":
                errors.append(f"{path}: cors_missing_or_not_star ({cors!r})")
                continue

            if not _is_json_health_payload(payload):
                errors.append(f"{path}: payload_missing_ok_true")
                continue

            return {
                "ok": True,
                "name": target.name,
                "url": url,
                "status": resp.status_code,
                "cors": cors,
                "payload": payload,
            }

        errors.append(f"{path}: http_{resp.status_code}")

    return {
        "ok": False,
        "name": target.name,
        "base_url": target.base_url,
        "errors": errors,
    }


def run(targets: Iterable[Target]) -> int:
    started = int(time.time())
    results = [_try_target(t) for t in targets]
    ok = sum(1 for r in results if r["ok"])
    total = len(results)

    output = {
        "ok": ok == total,
        "checked_at": started,
        "summary": {"passed": ok, "failed": total - ok, "total": total},
        "results": results,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if ok == total else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Thronos subdomain health smoke test")
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--retries", type=int, default=RETRIES)
    parser.add_argument("--strict", action="store_true", help="Require strict CORS and payload contract")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    STRICT = bool(args.strict)
    TIMEOUT = max(3, int(args.timeout or TIMEOUT))
    RETRIES = max(1, int(args.retries or RETRIES))
    sys.exit(run(TARGETS))
