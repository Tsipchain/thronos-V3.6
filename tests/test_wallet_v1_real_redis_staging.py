"""Opt-in real-Redis concurrency acceptance for Wallet V1 V2 nonces.

Run only against an isolated staging Redis:
WALLET_REAL_REDIS_URL=redis://127.0.0.1:<port>/15 pytest -q <this file>
"""

import os
import time
from concurrent.futures import ProcessPoolExecutor

import pytest


REAL_REDIS_URL = os.getenv("WALLET_REAL_REDIS_URL", "").strip()


def _consume_from_independent_worker(redis_url, address, nonce, timestamp):
    import redis
    import server

    server.REDIS_CLIENT = redis.Redis.from_url(redis_url)
    return server._consume_wallet_v1_signed_request_nonce(address, nonce, timestamp)


@pytest.mark.skipif(not REAL_REDIS_URL, reason="isolated real Redis not configured")
def test_real_redis_shared_multi_process_nonce_is_exactly_once():
    address = "THR" + "6" * 40
    nonce = f"real-redis-staging-{time.time_ns()}"
    timestamp = int(time.time())
    with ProcessPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(
                _consume_from_independent_worker,
                REAL_REDIS_URL,
                address,
                nonce,
                timestamp,
            )
            for _ in range(16)
        ]
        results = [future.result(timeout=30) for future in futures]

    assert sum(ok for ok, _error in results) == 1
    assert sum(
        error == "nonce_replay_detected" for ok, error in results if not ok
    ) == 15
